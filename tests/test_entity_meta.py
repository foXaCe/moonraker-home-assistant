"""Verify entity metadata: icons and translation keys for static entities."""

from unittest.mock import patch

import pytest
from custom_components.moonraker.const import DOMAIN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


ICON_EXPECTATIONS = {
    "sensor.mainsail_printer_state": "mdi:printer-3d",
    "sensor.mainsail_printer_message": "mdi:message-text-outline",
    "sensor.mainsail_current_print_state": "mdi:printer-3d-nozzle",
    "sensor.mainsail_idle_timeout_state": "mdi:timer-sand",
    "sensor.mainsail_filename": "mdi:file",
    "sensor.mainsail_queue_state": "mdi:playlist-play",
    "sensor.mainsail_spool_id": "mdi:tape-measure",
    "update.mainsail_system_update": "mdi:update",
    "camera.mainsail_thumbnail": "mdi:printer-3d-nozzle",
    "camera.mainsail_webcam": "mdi:webcam",
    "binary_sensor.mainsail_update_available": "mdi:update",
}


async def test_static_entities_have_icons(hass, get_data):
    """Static entities expose a dedicated icon."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="meta", unique_id="test"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    for entity_id in (
        "update.mainsail_system_update",
        "binary_sensor.mainsail_update_available",
    ):
        entry = registry.async_get(entity_id)
        if entry is not None and entry.disabled:
            registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    for entity_id, icon in ICON_EXPECTATIONS.items():
        state = hass.states.get(entity_id)
        assert state is not None, f"{entity_id} missing"
        assert state.attributes.get("icon") == icon, f"{entity_id} icon wrong"


async def test_static_sensors_use_translation_key(hass, get_data):
    """Static sensors expose a translation key instead of a hardcoded name."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="meta2", unique_id="test"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    for entity_id in (
        "sensor.mainsail_printer_state",
        "sensor.mainsail_current_print_state",
        "sensor.mainsail_queue_state",
        "number.mainsail_speed_factor",
        "binary_sensor.mainsail_update_available",
        "camera.mainsail_thumbnail",
    ):
        entry = registry.async_get(entity_id)
        assert entry is not None, f"{entity_id} missing"
        assert entry.translation_key, f"{entity_id} has no translation_key"
