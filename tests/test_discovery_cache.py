"""Tests for the persisted discovery snapshot."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.const import DOMAIN
from custom_components.moonraker.discovery_cache import (
    PrinterSnapshot,
    async_load_snapshot,
    async_remove_snapshot,
    async_save_snapshot,
)

from .const import MOCK_CONFIG

SNAPSHOT = PrinterSnapshot(
    objects_list={"objects": ["fan", "heater_bed"]},
    configfile_settings={"fan": {}},
    discovery_status={"fan": {"rpm": 1200}},
    discovery_objects={"fan": ["rpm"]},
)


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip the websocket handshake."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


async def test_snapshot_round_trip(hass):
    """A stored snapshot comes back unchanged."""
    await async_save_snapshot(hass, "printer-a", SNAPSHOT)

    assert await async_load_snapshot(hass, "printer-a") == SNAPSHOT
    assert await async_load_snapshot(hass, "printer-b") is None


async def test_snapshots_of_other_printers_are_kept(hass):
    """Saving one printer never disturbs another."""
    await async_save_snapshot(hass, "printer-a", SNAPSHOT)
    other = PrinterSnapshot({"objects": ["mcu"]}, {}, {}, {})
    await async_save_snapshot(hass, "printer-b", other)

    assert await async_load_snapshot(hass, "printer-a") == SNAPSHOT
    assert await async_load_snapshot(hass, "printer-b") == other


async def test_removing_a_snapshot(hass):
    """Removing a printer drops only its snapshot."""
    await async_save_snapshot(hass, "printer-a", SNAPSHOT)
    await async_save_snapshot(hass, "printer-b", SNAPSHOT)

    await async_remove_snapshot(hass, "printer-a")
    await async_remove_snapshot(hass, "unknown-printer")

    assert await async_load_snapshot(hass, "printer-a") is None
    assert await async_load_snapshot(hass, "printer-b") == SNAPSHOT


@pytest.mark.parametrize(
    "stored",
    [
        None,
        "not-a-mapping",
        {},
        {"objects_list": "wrong type"},
        {"objects_list": {"no objects key": []}},
    ],
)
def test_unusable_stored_shapes_are_rejected(stored):
    """A snapshot that cannot be trusted is treated as absent."""
    assert PrinterSnapshot.from_dict(stored) is None


def test_missing_optional_fields_default_to_empty():
    """Only the object list is mandatory."""
    snapshot = PrinterSnapshot.from_dict({"objects_list": {"objects": ["fan"]}})

    assert snapshot is not None
    assert snapshot.configfile_settings == {}
    assert snapshot.discovery_status == {}


def test_fields_we_never_asked_about_are_ignored():
    """Moonraker answers with everything the connection subscribed to.

    Discovery only asked about rpm here, so a speed that appears — or moves —
    says nothing about the printer's shape and must not trigger a reload.
    """
    asked = {"fan": ["rpm"]}
    idle = PrinterSnapshot({"objects": ["fan"]}, {}, {"fan": {"rpm": 10}}, asked)
    spinning = PrinterSnapshot(
        {"objects": ["fan"]}, {}, {"fan": {"speed": 0.5, "rpm": 10}}, asked
    )

    assert idle.matches(spinning)


def test_a_requested_field_going_null_is_a_change():
    """A fan that stops reporting rpm loses its sensor."""
    asked = {"fan": ["rpm"]}
    reporting = PrinterSnapshot({"objects": ["fan"]}, {}, {"fan": {"rpm": 10}}, asked)
    silent = PrinterSnapshot({"objects": ["fan"]}, {}, {"fan": {"rpm": None}}, asked)

    assert not reporting.matches(silent)


def test_measurements_do_not_count_as_a_change():
    """A different temperature is not a different printer."""
    warm = PrinterSnapshot(
        {"objects": ["fan"]}, {"fan": {}}, {"fan": {"rpm": 1200}}, {}
    )
    cold = PrinterSnapshot({"objects": ["fan"]}, {"fan": {}}, {"fan": {"rpm": 0}}, {})

    assert warm.matches(cold)


def test_a_field_becoming_null_counts_as_a_change():
    """A driver that stops reporting loses its sensor, so it is a change."""
    asked = {"tmc2240 x": ["temperature"]}
    reporting = PrinterSnapshot(
        {"objects": ["tmc2240 x"]}, {}, {"tmc2240 x": {"temperature": 40}}, asked
    )
    silent = PrinterSnapshot(
        {"objects": ["tmc2240 x"]}, {}, {"tmc2240 x": {"temperature": None}}, asked
    )

    assert not reporting.matches(silent)


def test_new_object_counts_as_a_change():
    """A printer that gained an object is a different printer."""
    before = PrinterSnapshot({"objects": ["fan"]}, {}, {}, {})
    after = PrinterSnapshot({"objects": ["fan", "mcu"]}, {}, {}, {})

    assert not before.matches(after)


def test_config_change_counts_as_a_change():
    """An edited printer.cfg changes which sections exist."""
    before = PrinterSnapshot({"objects": ["fan"]}, {"output_pin a": {}}, {}, {})
    after = PrinterSnapshot({"objects": ["fan"]}, {"output_pin b": {}}, {}, {})

    assert not before.matches(after)


async def test_setup_with_a_cached_snapshot_still_subscribes(
    hass, get_default_api_response
):
    """A cached start must not skip the websocket subscription.

    The cached path sends fewer opening calls, and unpacking their results wrong
    used to abort setup silently, leaving the integration polling forever.
    """
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="cached", unique_id="cached-uuid"
    )
    config_entry.add_to_hass(hass)
    await async_save_snapshot(hass, "cached-uuid", SNAPSHOT)

    with patch(
        "custom_components.moonraker.coordinator."
        "MoonrakerDataUpdateCoordinator.async_subscribe_objects",
        new_callable=AsyncMock,
    ) as subscribe:
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    subscribe.assert_awaited()

    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_a_changed_printer_reloads_the_entry(hass, get_default_api_response):
    """A snapshot that no longer matches is replaced and the entry reloaded."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="changed", unique_id="changed-uuid"
    )
    config_entry.add_to_hass(hass)
    # Deliberately unlike what the mocked printer reports.
    await async_save_snapshot(hass, "changed-uuid", SNAPSHOT)

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_schedule_reload"
    ) as reload:
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    reload.assert_called_once_with(config_entry.entry_id)

    # The snapshot was refreshed, so the next start agrees with the printer.
    stored = await async_load_snapshot(hass, "changed-uuid")
    assert stored is not None
    assert stored != SNAPSHOT

    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_the_entry_reloads_only_once_per_run(hass, get_default_api_response):
    """A comparison that never settles must not reload forever."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="loop", unique_id="loop-uuid"
    )
    config_entry.add_to_hass(hass)
    await async_save_snapshot(hass, "loop-uuid", SNAPSHOT)
    hass.data[f"{DOMAIN}_snapshot_reloads"] = {config_entry.entry_id}

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_schedule_reload"
    ) as reload:
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    reload.assert_not_called()

    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_first_start_stores_what_it_discovered(hass, get_default_api_response):
    """With no snapshot, setup discovers everything and stores the result."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="first", unique_id="first-uuid"
    )
    config_entry.add_to_hass(hass)

    assert await async_load_snapshot(hass, "first-uuid") is None

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_schedule_reload"
    ) as reload:
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    # Nothing to compare against, so nothing to reload.
    reload.assert_not_called()
    assert await async_load_snapshot(hass, "first-uuid") is not None

    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_removing_the_entry_drops_its_snapshot(hass, get_default_api_response):
    """A printer removed from Home Assistant leaves no snapshot behind."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="gone", unique_id="gone-uuid"
    )
    config_entry.add_to_hass(hass)
    await async_save_snapshot(hass, "gone-uuid", SNAPSHOT)

    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()

    assert await async_load_snapshot(hass, "gone-uuid") is None


def test_non_mapping_status_entries_are_ignored():
    """A status entry that is not a mapping cannot describe fields."""
    odd = PrinterSnapshot({"objects": ["fan"]}, {}, {"fan": "unexpected"}, {})
    empty = PrinterSnapshot({"objects": ["fan"]}, {}, {}, {})

    assert odd.matches(empty)


@pytest.mark.parametrize(
    ("objects_list", "config_query"),
    [
        ("not a mapping", {"status": {"configfile": {"settings": {}}}}),
        ({"no objects key": 1}, {"status": {"configfile": {"settings": {}}}}),
        ({"objects": []}, "not a mapping"),
        ({"objects": []}, {"status": {"configfile": {"settings": "not a mapping"}}}),
    ],
)
async def test_an_unusable_probe_changes_nothing(hass, objects_list, config_query):
    """A probe that cannot be trusted never replaces the stored snapshot."""
    from custom_components.moonraker import _async_probe_printer

    coordinator = MagicMock()
    answers = iter([objects_list, config_query, {"status": {}}])

    async def _fetch(*_args, **_kwargs):
        return next(answers)

    coordinator.async_fetch_data = _fetch

    assert await _async_probe_printer(coordinator, SNAPSHOT) is None


async def test_a_matching_snapshot_changes_nothing(hass, get_default_api_response):
    """A snapshot that still describes the printer is left alone."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="same", unique_id="same-uuid"
    )
    config_entry.add_to_hass(hass)

    # First start discovers and stores.
    with patch("homeassistant.config_entries.ConfigEntries.async_schedule_reload"):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    stored = await async_load_snapshot(hass, "same-uuid")
    assert stored is not None

    await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    # Second start replays it and finds the printer unchanged.
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_schedule_reload"
    ) as reload:
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    reload.assert_not_called()
    assert await async_load_snapshot(hass, "same-uuid") == stored

    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_an_unreachable_probe_keeps_the_snapshot(hass, get_default_api_response):
    """If the check cannot reach the printer, nothing is changed."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="probefail", unique_id="probe-uuid"
    )
    config_entry.add_to_hass(hass)
    await async_save_snapshot(hass, "probe-uuid", SNAPSHOT)

    with (
        patch(
            "custom_components.moonraker._async_probe_printer",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_schedule_reload"
        ) as reload,
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    reload.assert_not_called()
    assert await async_load_snapshot(hass, "probe-uuid") == SNAPSHOT

    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_incomplete_discovery_is_not_stored(hass, get_default_api_response):
    """A snapshot must never freeze a printer that answered only partly."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="partial", unique_id="partial-uuid"
    )
    config_entry.add_to_hass(hass)

    real_check = None

    async def _degrade_then_check(hass_arg, entry, coordinator, cached):
        coordinator.discovery_degraded = True
        return await real_check(hass_arg, entry, coordinator, cached)

    import custom_components.moonraker as integration

    real_check = integration._async_check_discovery_snapshot
    with patch.object(
        integration, "_async_check_discovery_snapshot", _degrade_then_check
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert await async_load_snapshot(hass, "partial-uuid") is None

    await hass.config_entries.async_unload(config_entry.entry_id)
