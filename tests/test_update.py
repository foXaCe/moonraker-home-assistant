"""Tests for the Moonraker update platform."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from custom_components.moonraker.const import DOMAIN
from custom_components.moonraker.coordinator import MoonrakerDataUpdateCoordinator
from custom_components.moonraker.update import MoonrakerUpdateEntity
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


def _make_update_entity(hass, component, installed_version, latest_version):
    """Build an update entity bound to a coordinator with empty data."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="test-uuid",
        entry_id=f"upd_{component}",
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass,
        client=MagicMock(),
        config_entry=config_entry,
        api_device_name="printer",
    )
    coordinator.data = {}
    entity = MoonrakerUpdateEntity(
        coordinator,
        config_entry,
        component=component,
        title=component.title(),
        installed_version=installed_version,
        latest_version=latest_version,
    )
    entity.hass = hass
    entity.entity_id = f"update.mainsail_{component}_update"
    entity.platform = SimpleNamespace(platform_name=DOMAIN)
    return entity


async def test_update_entities_created_for_components(
    hass, get_default_api_response, get_machine_update_status
):
    """Update entities are created for each reported component."""
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        side_effect=lambda method, *a, **k: (
            {**get_machine_update_status}
            if method == "machine.update.status"
            else {**get_default_api_response}
        ),
    ):
        config_entry = MockConfigEntry(
            domain=DOMAIN, data=MOCK_CONFIG, entry_id="upd", unique_id="test"
        )
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    system = registry.async_get("update.mainsail_system_update")
    crownest = registry.async_get("update.mainsail_crownest_update")
    assert system is not None
    assert crownest is not None
    assert system.disabled
    assert crownest.disabled

    registry.async_update_entity("update.mainsail_crownest_update", disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("update.mainsail_crownest_update")
    assert state is not None
    assert state.state == "on"
    assert state.attributes["installed_version"] == "v4.0.4-6"
    assert state.attributes["latest_version"] == "v4.1.1-1"


async def test_update_entities_skip_unversioned_components(
    hass, get_default_api_response, get_machine_update_status
):
    """Components without version info do not produce an update entity."""
    status = {**get_machine_update_status}
    status["version_info"]["unversioned"] = {"package_count": 2}
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        side_effect=lambda method, *a, **k: (
            {**status}
            if method == "machine.update.status"
            else {**get_default_api_response}
        ),
    ):
        config_entry = MockConfigEntry(
            domain=DOMAIN, data=MOCK_CONFIG, entry_id="upd2", unique_id="test"
        )
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    assert registry.async_get("update.mainsail_unversioned_update") is None


async def test_handle_coordinator_update_system_component(hass):
    """System component updates the package count availability."""
    entity = _make_update_entity(hass, "system", "installed", "old")
    entity.coordinator.data = {
        "machine_update": {"version_info": {"system": {"package_count": 8}}}
    }

    entity._handle_coordinator_update()

    assert entity._attr_installed_version == "installed"
    assert entity._attr_latest_version == "8 package update(s) available"


async def test_handle_coordinator_update_component_versions(hass):
    """Component dicts refresh installed and latest versions."""
    entity = _make_update_entity(hass, "crownest", "old-installed", "old-latest")
    entity.coordinator.data = {
        "machine_update": {
            "version_info": {
                "crownest": {"version": "v4.0.4-6", "remote_version": "v4.1.1-1"}
            }
        }
    }

    entity._handle_coordinator_update()

    assert entity._attr_installed_version == "v4.0.4-6"
    assert entity._attr_latest_version == "v4.1.1-1"


async def test_handle_coordinator_update_partial_component_versions(hass):
    """Missing version fields leave the matching attribute untouched."""
    entity = _make_update_entity(hass, "mainsail", "v2.8.0", "old-latest")
    entity.coordinator.data = {
        "machine_update": {"version_info": {"mainsail": {"remote_version": "v2.9.0"}}}
    }

    entity._handle_coordinator_update()

    assert entity._attr_installed_version == "v2.8.0"
    assert entity._attr_latest_version == "v2.9.0"


async def test_handle_coordinator_update_ignores_non_dict_info(hass):
    """Non-dict component info leaves the entity unchanged."""
    entity = _make_update_entity(hass, "crownest", "installed", "latest")
    entity.coordinator.data = {
        "machine_update": {"version_info": {"crownest": "not-a-dict"}}
    }

    entity._handle_coordinator_update()

    assert entity._attr_installed_version == "installed"
    assert entity._attr_latest_version == "latest"


async def test_handle_coordinator_update_missing_machine_update(hass):
    """Missing machine_update data leaves the entity unchanged."""
    entity = _make_update_entity(hass, "crownest", "installed", "latest")

    entity._handle_coordinator_update()

    assert entity._attr_installed_version == "installed"
    assert entity._attr_latest_version == "latest"
