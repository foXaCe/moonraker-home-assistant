"""Tests for the Moonraker repairs."""

from unittest.mock import AsyncMock, patch

from custom_components.moonraker.const import DOMAIN
from homeassistant.helpers import issue_registry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.repairs import create_invalid_api_key_issue

from .const import MOCK_CONFIG


async def test_create_invalid_api_key_issue_registers(hass):
    """Creating the issue registers it in the issue registry."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="rep")
    entry.add_to_hass(hass)

    await create_invalid_api_key_issue(hass, entry)

    registry = issue_registry.async_get(hass)
    issue = registry.async_get_issue(DOMAIN, f"invalid_api_key_{entry.entry_id}")
    assert issue is not None
    assert issue.is_fixable is True
    assert issue.severity == issue_registry.IssueSeverity.ERROR


async def test_repair_fix_flow_starts_reauth(hass):
    """The repair flow offers reauthentication."""
    from custom_components.moonraker.repairs import MoonrakerInvalidApiKeyRepairFlow

    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="rep2")
    entry.add_to_hass(hass)

    flow = MoonrakerInvalidApiKeyRepairFlow()
    flow.hass = hass
    flow.handler = DOMAIN
    flow.data = {"entry_id": entry.entry_id}

    with patch.object(hass.config_entries.flow, "async_init", new=AsyncMock()) as init:
        result = await flow.async_step_init()
        assert result["type"] == "form"
        assert result["step_id"] == "confirm"
        result = await flow.async_step_confirm({"reauth": True})

    assert result["type"] == "create_entry"
    init.assert_awaited_once()


async def test_repair_fix_flow_skip_reauth(hass):
    """Confirming without reauth does not start the reauth flow."""
    from custom_components.moonraker.repairs import MoonrakerInvalidApiKeyRepairFlow

    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="rep3")
    entry.add_to_hass(hass)

    flow = MoonrakerInvalidApiKeyRepairFlow()
    flow.hass = hass
    flow.handler = DOMAIN
    flow.data = {"entry_id": entry.entry_id}

    with patch.object(hass.config_entries.flow, "async_init", new=AsyncMock()) as init:
        result = await flow.async_step_confirm({})

    assert result["type"] == "create_entry"
    init.assert_not_awaited()


async def test_async_create_fix_flow_returns_flow(hass):
    """async_create_fix_flow returns a repair flow instance."""
    from custom_components.moonraker.repairs import (
        MoonrakerInvalidApiKeyRepairFlow,
        async_create_fix_flow,
    )

    flow = await async_create_fix_flow(hass, "invalid_api_key_x", {})
    assert isinstance(flow, MoonrakerInvalidApiKeyRepairFlow)
