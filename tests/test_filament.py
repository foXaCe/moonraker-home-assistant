"""Tests for the per-extruder filament sensors."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.const import DOMAIN, FILAMENT_INFO_OBJECT
from custom_components.moonraker.coordinator import MoonrakerDataUpdateCoordinator
from custom_components.moonraker.devices import filament

from .const import MOCK_CONFIG

# What a Snapmaker U1 reports for four loaded spools.
U1_STATUS = {
    FILAMENT_INFO_OBJECT: {
        "filament_color_rgba": ["FF0000FF", "00FF00FF", "0000FFFF", "FFFFFFFF"],
        "filament_vendor": ["Snapmaker", "Snapmaker", "Snapmaker", "Snapmaker"],
        "filament_type": ["PLA", "PETG", "PLA", "ABS"],
        "filament_sub_type": ["Basic", "Basic", "Silk", "Basic"],
        "filament_official": [True, True, False, True],
        "filament_sku": ["SKU1", "SKU2", "SKU3", "SKU4"],
        "filament_edit": [False, False, False, False],
        "filament_soft": [False, False, True, False],
    }
}


def _coordinator(hass, objects, discovery):
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="fil-uuid", entry_id="fil"
    )
    config_entry.add_to_hass(hass)
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )
    coordinator.objects_list = {"objects": objects}
    coordinator.async_discover_objects = AsyncMock(return_value=discovery)
    return coordinator


def _sensor(coordinator, status):
    sensor = MagicMock()
    sensor.coordinator = coordinator
    coordinator.data = {"status": status}
    return sensor


async def test_no_sensor_when_the_printer_lacks_the_object(hass):
    """Printers other than the U1 do not list print_task_config."""
    coordinator = _coordinator(hass, ["fan", "extruder"], {})

    assert await filament.build_filament_sensors(coordinator) == []
    coordinator.async_discover_objects.assert_not_awaited()


async def test_no_sensor_when_no_colour_is_reported(hass):
    """The object can be listed yet answer nothing usable."""
    coordinator = _coordinator(hass, [FILAMENT_INFO_OBJECT], {FILAMENT_INFO_OBJECT: {}})

    assert await filament.build_filament_sensors(coordinator) == []


async def test_one_sensor_per_loaded_extruder(hass):
    """A U1 with four spools gets four sensors, not a hardcoded number."""
    coordinator = _coordinator(hass, [FILAMENT_INFO_OBJECT], U1_STATUS)

    sensors = await filament.build_filament_sensors(coordinator)

    assert [s.key for s in sensors] == [
        "extruder_0_filament",
        "extruder_1_filament",
        "extruder_2_filament",
        "extruder_3_filament",
    ]
    assert [s.name for s in sensors] == [
        "Filament E0",
        "Filament E1",
        "Filament E2",
        "Filament E3",
    ]


async def test_a_two_extruder_printer_gets_two_sensors(hass):
    """The count follows what the printer reports."""
    status = {FILAMENT_INFO_OBJECT: {"filament_color_rgba": ["AABBCCDD", "11223344"]}}
    coordinator = _coordinator(hass, [FILAMENT_INFO_OBJECT], status)

    assert len(await filament.build_filament_sensors(coordinator)) == 2


async def test_the_state_is_the_colour_as_hex(hass):
    """Home Assistant expects a leading '#'."""
    coordinator = _coordinator(hass, [FILAMENT_INFO_OBJECT], U1_STATUS)
    sensors = await filament.build_filament_sensors(coordinator)
    sensor = _sensor(coordinator, U1_STATUS)

    assert sensors[0].value_fn(sensor) == "#FF0000FF"
    assert sensors[2].value_fn(sensor) == "#0000FFFF"


async def test_the_rest_is_exposed_as_attributes(hass):
    """Everything but the colour rides along as attributes."""
    coordinator = _coordinator(hass, [FILAMENT_INFO_OBJECT], U1_STATUS)
    sensors = await filament.build_filament_sensors(coordinator)
    sensor = _sensor(coordinator, U1_STATUS)

    assert sensors[2].extra_state_fn(sensor) == {
        "vendor": "Snapmaker",
        "type": "PLA",
        "sub_type": "Silk",
        "official": False,
        "sku": "SKU3",
        "edit": False,
        "soft": True,
    }
    assert "color_rgba" not in sensors[2].extra_state_fn(sensor)


@pytest.mark.parametrize(
    "status",
    [
        {},
        {FILAMENT_INFO_OBJECT: {}},
        {FILAMENT_INFO_OBJECT: {"filament_color_rgba": []}},
        {FILAMENT_INFO_OBJECT: {"filament_color_rgba": "not a list"}},
        {FILAMENT_INFO_OBJECT: {"filament_color_rgba": [None]}},
    ],
)
async def test_a_spool_that_stops_reporting_reads_unknown(hass, status):
    """An extruder with nothing loaded must not break the sensor."""
    coordinator = _coordinator(hass, [FILAMENT_INFO_OBJECT], U1_STATUS)
    sensors = await filament.build_filament_sensors(coordinator)
    sensor = _sensor(coordinator, status)

    assert sensors[0].value_fn(sensor) is None
    assert sensors[0].extra_state_fn(sensor) == {}


async def test_the_object_is_subscribed_not_polled(hass):
    """Values must arrive with the push updates, not cost a query per refresh."""
    coordinator = _coordinator(hass, [FILAMENT_INFO_OBJECT], U1_STATUS)

    sensors = await filament.build_filament_sensors(coordinator)

    assert all(obj == FILAMENT_INFO_OBJECT for obj, _ in sensors[0].subscriptions or [])
    coordinator.load_sensor_data(sensors)
    assert FILAMENT_INFO_OBJECT in coordinator.query_obj["objects"]


async def test_filament_sensors_reach_home_assistant(hass, get_default_api_response):
    """End to end: a printer reporting filament info gets entities with attributes."""
    response = {**get_default_api_response}
    response["status"] = {**response["status"], **U1_STATUS}
    response["objects"] = [*response["objects"], FILAMENT_INFO_OBJECT]

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="test", unique_id="test"
    )
    config_entry.add_to_hass(hass)

    with (
        patch("moonraker_api.MoonrakerClient.call_method", return_value=response),
        patch("custom_components.moonraker.MoonrakerApiClient.start"),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_filament_e0")
    assert state is not None
    assert state.state == "#FF0000FF"
    assert state.attributes["vendor"] == "Snapmaker"
    assert state.attributes["type"] == "PLA"

    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_broken_attributes_do_not_break_the_entity(hass):
    """An attribute function that trips over bad data yields no attributes."""
    from custom_components.moonraker.devices.base import MoonrakerSensorDescription
    from custom_components.moonraker.sensor import MoonrakerSensor

    def _explode(_sensor):
        raise KeyError("missing")

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="broken", entry_id="broken"
    )
    config_entry.add_to_hass(hass)
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )
    coordinator.data = {}

    entity = MoonrakerSensor(
        coordinator,
        config_entry,
        MoonrakerSensorDescription(
            key="broken",
            name="Broken",
            value_fn=lambda sensor: None,
            extra_state_fn=_explode,
            subscriptions=[],
        ),
    )

    assert entity.extra_state_attributes is None
