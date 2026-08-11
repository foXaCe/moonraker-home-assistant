"""Tests for the Moonraker diagnostics."""

from unittest.mock import patch

import pytest
from custom_components.moonraker.const import DOMAIN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.diagnostics import async_get_config_entry_diagnostics

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


async def test_diagnostics_redacts_api_key(hass, get_default_api_response):
    """The API key is never included in diagnostics."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="diag", unique_id="test"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    assert "api_key" not in diag["entry"]["data"]
    assert diag["printer"]["name"] == "mainsail"
    assert diag["connection"]["last_update_success"] is True
