"""Test moonraker setup process."""

import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.moonraker.const import PRINTSTATES

from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.moonraker import (
    _async_migrate_entity_unique_ids,
    async_reload_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.moonraker.api import MoonrakerApiClient
from custom_components.moonraker.api.exceptions import (
    ApiAuthError,
    ApiConnectionError,
    MoonrakerApiError,
)
from custom_components.moonraker.coordinator import (
    MoonrakerDataUpdateCoordinator,
    _async_is_tcp_reachable,
)
from custom_components.moonraker.helpers import (
    build_thumbnail_path,
    normalize_gcode_path,
    normalize_moonraker_port,
    strip_gcode_root,
)
from custom_components.moonraker.const import (
    CONF_OPTION_QUIET_UNREACHABLE,
    CONF_PORT,
    DEFAULT_PORT,
    DOMAIN,
    METHODS,
    OBJ,
)

from .const import MOCK_CONFIG, MOCK_CONFIG_WITH_NAME


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with (
        patch("custom_components.moonraker.MoonrakerApiClient.start"),
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "custom_components.moonraker.coordinator._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        yield


def test_normalize_moonraker_port_uses_default_for_empty_values():
    """Empty configured ports should use the Moonraker default port."""
    assert normalize_moonraker_port("") == DEFAULT_PORT
    assert normalize_moonraker_port(None) == DEFAULT_PORT


def test_normalize_moonraker_port_converts_configured_values():
    """Configured ports should be converted to integers for socket probing."""
    assert normalize_moonraker_port("7611") == 7611
    assert normalize_moonraker_port(7611) == 7611


def test_normalize_gcode_path_empty():
    """Return empty parts for empty input."""
    assert normalize_gcode_path("") == ("", None)
    assert normalize_gcode_path(None) == ("", None)


def test_normalize_gcode_path_whitespace():
    """Return empty parts for whitespace-only input."""
    assert normalize_gcode_path("   ") == ("", None)


def test_normalize_gcode_path_with_root_prefix():
    """Strip gcodes root from relative paths."""
    filename, root = normalize_gcode_path("gcodes/subdir/file.gcode")
    assert filename == "subdir/file.gcode"
    assert root == "gcodes"


def test_normalize_gcode_path_with_absolute_path():
    """Extract gcodes root from absolute paths."""
    filename, root = normalize_gcode_path(
        "/home/user/printer_data/gcodes/subdir/file.gcode"
    )
    assert filename == "subdir/file.gcode"
    assert root == "gcodes"


def test_strip_gcode_root_prefix():
    """Strip root prefix from thumbnail paths."""
    assert strip_gcode_root("gcodes/.thumbs/file.png", "gcodes") == ".thumbs/file.png"


def test_strip_gcode_root_none_path():
    """Return empty string when path is None."""
    assert strip_gcode_root(None, "gcodes") == ""


def test_strip_gcode_root_whitespace_path():
    """Return empty string when path is whitespace."""
    assert strip_gcode_root("   ", "gcodes") == ""


def test_strip_gcode_root_absolute():
    """Strip root prefix when embedded in an absolute path."""
    assert (
        strip_gcode_root("/home/user/gcodes/.thumbs/file.png", "gcodes")
        == ".thumbs/file.png"
    )


def test_strip_gcode_root_without_root():
    """Leave paths untouched when no root is provided."""
    assert (
        strip_gcode_root("subfolder/.thumbs/file.png", None)
        == "subfolder/.thumbs/file.png"
    )


def test_strip_gcode_root_without_root_prefix():
    """Strip gcodes prefix even without an explicit root."""
    assert strip_gcode_root("gcodes/.thumbs/file.png", None) == ".thumbs/file.png"


def test_build_thumbnail_path_reuses_existing_dir():
    """Avoid duplicating directory segments."""
    assert (
        build_thumbnail_path("subfolder", "subfolder/.thumbs/file.png", "gcodes")
        == "subfolder/.thumbs/file.png"
    )


def test_build_thumbnail_path_missing_thumbnail():
    """Return None when thumbnail path is missing."""
    assert build_thumbnail_path("subfolder", None, "gcodes") is None


def test_build_thumbnail_path_only_dot_prefix():
    """Return None when thumbnail path is only './'."""
    assert build_thumbnail_path("subfolder", "./", "gcodes") is None


def test_build_thumbnail_path_joins_dir():
    """Join the gcode directory when thumbnails are relative."""
    assert (
        build_thumbnail_path("subfolder", ".thumbs/file.png", "gcodes")
        == "subfolder/.thumbs/file.png"
    )


def test_build_thumbnail_path_empty_dir_after_strip():
    """Return thumbnail path when directory collapses to empty."""
    assert build_thumbnail_path("/", ".thumbs/file.png", "gcodes") == ".thumbs/file.png"


def test_build_thumbnail_path_strips_dot_prefix():
    """Trim leading ./ for URL usage."""
    assert (
        build_thumbnail_path("", "./.thumbs/file.png", "gcodes") == ".thumbs/file.png"
    )


async def test_gcode_detail_skips_empty_normalized_filename(hass):
    """Return defaults when normalized filename is empty."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="test"
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )

    result = await coordinator._async_get_gcode_file_detail("/")

    assert result["thumbnails_path"] is None
    assert result["layer_count"] is None


async def test_gcode_detail_missing_thumbnails_skips_warning(hass, caplog):
    """Missing thumbnail metadata should not emit warnings."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="test"
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )
    gcode_data = {
        "estimated_time": 10,
        "object_height": 5.5,
        "filament_total": 1.2,
        "layer_count": 20,
        "layer_height": 0.2,
        "first_layer_height": 0.3,
        "gcode_start_byte": 100,
        "gcode_end_byte": 200,
    }
    coordinator._async_fetch_data = AsyncMock(return_value=gcode_data)

    with caplog.at_level(logging.WARNING):
        result = await coordinator._async_get_gcode_file_detail("example.gcode")

    coordinator._async_fetch_data.assert_awaited_once_with(
        METHODS.SERVER_FILES_METADATA, {"filename": "example.gcode"}
    )
    assert result["thumbnails_path"] is None
    assert result["estimated_time"] == 10
    assert result["object_height"] == 5.5
    assert result["filament_total"] == 1.2
    assert result["layer_count"] == 20
    assert result["layer_height"] == 0.2
    assert result["first_layer_height"] == 0.3
    assert result["gcode_start_byte"] == 100
    assert result["gcode_end_byte"] == 200
    assert "failed to get thumbnails" not in caplog.text


async def test_gcode_detail_thumbnail_selection_ignores_invalid_entries(hass):
    """Pick the best thumbnail while ignoring invalid entries."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="test"
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )
    gcode_data = {
        "thumbnails": [
            "not-a-dict",
            {"size": 12},
            {"relative_path": ".thumbs/fallback.png", "size": "bad"},
            {"relative_path": ".thumbs/best.png", "size": 999},
        ]
    }
    coordinator._async_fetch_data = AsyncMock(return_value=gcode_data)

    result = await coordinator._async_get_gcode_file_detail("subdir/file.gcode")

    coordinator._async_fetch_data.assert_awaited_once_with(
        METHODS.SERVER_FILES_METADATA, {"filename": "subdir/file.gcode"}
    )
    assert result["thumbnails_path"] == "subdir/.thumbs/best.png"


async def test_gcode_detail_thumbnail_selection_missing_paths(hass):
    """Return without thumbnail when no valid paths are provided."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="test"
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )
    gcode_data = {"thumbnails": ["not-a-dict", {"size": 12}, {"relative_path": ""}]}
    coordinator._async_fetch_data = AsyncMock(return_value=gcode_data)

    result = await coordinator._async_get_gcode_file_detail("file.gcode")

    coordinator._async_fetch_data.assert_awaited_once_with(
        METHODS.SERVER_FILES_METADATA, {"filename": "file.gcode"}
    )
    assert result["thumbnails_path"] is None


async def test_add_query_objects_ignores_keys_after_full_object(hass):
    """Skip adding keys when object is already set to fetch all fields."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="test"
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )

    coordinator.add_query_objects("gcode_macro TEST", None)
    assert coordinator.query_obj[OBJ]["gcode_macro TEST"] is None

    coordinator.add_query_objects("gcode_macro TEST", "variable_1")
    assert coordinator.query_obj[OBJ]["gcode_macro TEST"] is None


async def test_setup_unload_and_reload_entry(hass):
    """Test entry setup and unload."""
    # Create a mock entry so we don't have to go through config flow

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="test"
    )
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)
    assert isinstance(
        config_entry.runtime_data.coordinator, MoonrakerDataUpdateCoordinator
    )

    # Reload the entry and assert that the data from above is still there.
    hass.config_entries._entries[config_entry.entry_id] = config_entry
    assert await async_reload_entry(hass, config_entry) is None
    assert isinstance(
        config_entry.runtime_data.coordinator, MoonrakerDataUpdateCoordinator
    )

    # Unload the entry and verify that the data has been removed
    assert await async_unload_entry(hass, config_entry)
    assert not hasattr(config_entry, "runtime_data")


async def test_setup_unload_and_reload_entry_with_name(hass):
    """Test entry setup with name and unload."""
    # Create a mock entry so we don't have to go through config flow

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_WITH_NAME,
        unique_id="test-uuid",
        entry_id="test",
    )
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)
    assert isinstance(
        config_entry.runtime_data.coordinator, MoonrakerDataUpdateCoordinator
    )

    # Reload the entry and assert that the data from above is still there.
    hass.config_entries._entries[config_entry.entry_id] = config_entry
    assert await async_reload_entry(hass, config_entry) is None
    assert isinstance(
        config_entry.runtime_data.coordinator, MoonrakerDataUpdateCoordinator
    )

    # Unload the entry and verify that the data has been removed
    assert await async_unload_entry(hass, config_entry)
    assert not hasattr(config_entry, "runtime_data")


async def test_async_send_data_exception(hass):
    """Test async_post_exception."""

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="test"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=UpdateFailed,
        ),
        pytest.raises(UpdateFailed),
    ):
        coordinator = config_entry.runtime_data.coordinator
        assert await coordinator.async_send_data(METHODS.PRINTER_EMERGENCY_STOP)

    assert await async_unload_entry(hass, config_entry)


async def test_setup_entry_exception(hass):
    """Test ConfigEntryNotReady when API raises an exception during entry setup."""
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        new_callable=AsyncMock,
        side_effect=Exception,
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        config_entry.add_to_hass(hass)

        with pytest.raises(ConfigEntryNotReady):
            assert await async_setup_entry(hass, config_entry)


async def test_setup_entry_generic_exception_stays_warning_when_option_enabled(
    hass, caplog
):
    """Quiet unreachable mode must not hide non-reachability setup failures."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options={CONF_OPTION_QUIET_UNREACHABLE: True},
        entry_id="setup_error_quiet",
    )
    config_entry.add_to_hass(hass)

    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=Exception,
        ),
        caplog.at_level(logging.DEBUG),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, config_entry)

    assert any(
        record.levelno == logging.WARNING
        and record.message == "Cannot configure moonraker instance"
        for record in caplog.records
    )


async def test_setup_entry_unreachable_logs_warning_by_default(hass, caplog):
    """Unreachable printers keep warning-level visibility unless silenced."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="offline")
    config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ),
        caplog.at_level(logging.DEBUG),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, config_entry)

    assert "Cannot configure moonraker instance" in caplog.text
    assert any(
        record.levelno == logging.WARNING
        and "Cannot configure moonraker instance" in record.message
        for record in caplog.records
    )


async def test_setup_entry_empty_port_uses_default_for_reachability_probe(hass):
    """Empty stored ports remain accepted and are probed as the default port."""
    config = {**MOCK_CONFIG, CONF_PORT: ""}
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=config,
        entry_id="empty_port",
    )
    config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ) as is_reachable,
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, config_entry)

    is_reachable.assert_awaited_once_with("1.2.3.4", DEFAULT_PORT)


async def test_setup_entry_unreachable_logs_debug_when_option_enabled(hass, caplog):
    """Unreachable printers can be configured to avoid warning-level log spam."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options={CONF_OPTION_QUIET_UNREACHABLE: True},
        entry_id="offline_quiet",
    )
    config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ),
        caplog.at_level(logging.DEBUG),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, config_entry)

    assert "Cannot configure moonraker instance" in caplog.text
    assert any(
        record.levelno == logging.DEBUG
        and "Cannot configure moonraker instance" in record.message
        for record in caplog.records
    )
    assert not any(
        record.levelno >= logging.WARNING
        and "Cannot configure moonraker instance" in record.message
        for record in caplog.records
    )


async def test_async_is_tcp_reachable_returns_true_when_connection_opens():
    """A successful TCP connection marks the endpoint as reachable."""
    writer = MagicMock()
    writer.wait_closed = AsyncMock()

    with patch(
        "custom_components.moonraker.coordinator.asyncio.open_connection",
        new_callable=AsyncMock,
        return_value=(MagicMock(), writer),
    ):
        assert await _async_is_tcp_reachable("1.2.3.4", 7125) is True

    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()


async def test_async_is_tcp_reachable_returns_false_when_connection_fails():
    """Connection errors mark the endpoint as unreachable."""
    with patch(
        "custom_components.moonraker.coordinator.asyncio.open_connection",
        new_callable=AsyncMock,
        side_effect=OSError,
    ):
        assert await _async_is_tcp_reachable("1.2.3.4", 7125) is False


async def test_async_fetch_data_unreachable_raises_update_failed(hass):
    """Fetching while disconnected and unreachable raises UpdateFailed."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="test"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    coordinator = config_entry.runtime_data.coordinator

    with (
        patch(
            "custom_components.moonraker.coordinator._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ),
        pytest.raises(UpdateFailed),
    ):
        await coordinator.async_fetch_data(METHODS.PRINTER_INFO)

    assert await async_unload_entry(hass, config_entry)


async def test_async_send_data_unreachable_raises_update_failed(hass):
    """Sending while disconnected and unreachable raises UpdateFailed."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="test"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    coordinator = config_entry.runtime_data.coordinator

    with (
        patch(
            "custom_components.moonraker.coordinator._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ),
        pytest.raises(UpdateFailed),
    ):
        await coordinator.async_send_data(METHODS.PRINTER_EMERGENCY_STOP)

    assert await async_unload_entry(hass, config_entry)


async def test_coordinator_passes_config_entry_to_super(hass):
    """Ensure the coordinator forwards the config entry to the base class."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="config"
    )

    captured: dict[str, dict] = {}
    original_init = DataUpdateCoordinator.__init__

    def wrapped_init(self, hass_param, logger, *args, **kwargs):
        captured["kwargs"] = dict(kwargs)
        captured["args"] = (hass_param, logger, *args)
        return original_init(self, hass_param, logger, *args, **kwargs)

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__",
        new=wrapped_init,
    ):
        coordinator = MoonrakerDataUpdateCoordinator(
            hass,
            client=MagicMock(),
            config_entry=config_entry,
            api_device_name="printer",
        )

    assert captured["kwargs"]["config_entry"] is config_entry
    assert coordinator.config_entry is config_entry


def load_data(endpoint, *args, **kwargs):
    """Load data."""
    if endpoint == "printer.info":
        return {"hostname": "mainsail"}

    raise Exception


async def test_failed_first_refresh(hass):
    """Test ConfigEntryNotReady when API raises an exception during entry setup."""
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        side_effect=load_data,
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        config_entry.add_to_hass(hass)

        with pytest.raises(ConfigEntryNotReady):
            assert await async_setup_entry(hass, config_entry)


async def test_setup_entry_offline_with_unique_id_proceeds(hass):
    """Set up with unavailable entities when the printer is unreachable.

    A previously configured entry should not retry ConfigEntryNotReady forever.
    """
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="offline_tol"
    )
    config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=Exception,
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state.value == "loaded"
    assert config_entry.runtime_data.coordinator is not None
    assert not config_entry.runtime_data.coordinator.last_update_success


async def test_set_custom_gcode_service(hass):
    """Test custom GCode Services."""

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="test"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    device_id = list(hass.data["device_registry"].devices.keys())

    # Test that the function call works in its entirety.
    with patch(
        "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
    ) as mock_sensors:
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": device_id,
                "gcode": "STATUS",
            },
            blocking=True,
        )
        await hass.async_block_till_done()
        mock_sensors.assert_awaited_once_with(
            METHODS.PRINTER_GCODE_SCRIPT.value, script="STATUS"
        )


async def test_send_gcode_list_payload_normalizes_script(hass):
    """Ensure list payloads join into a single script."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="test-uuid",
        entry_id="list_payload",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    device_ids = list(hass.data["device_registry"].devices.keys())
    target_device_id = device_ids[0]

    with patch(
        "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
    ) as mock_call:
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": target_device_id,
                "gcode": ["G28", "M105"],
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_call.assert_awaited_once_with(
        METHODS.PRINTER_GCODE_SCRIPT.value, script="G28\nM105"
    )
    assert await async_unload_entry(hass, config_entry)


async def test_send_gcode_empty_payload_skips_send(hass):
    """Ensure empty payloads do not call Moonraker."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="test-uuid",
        entry_id="empty_payload",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    device_ids = list(hass.data["device_registry"].devices.keys())

    with patch(
        "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
    ) as mock_call:
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": device_ids,
                "gcode": ["   ", ""],
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_call.await_count == 0
    assert await async_unload_entry(hass, config_entry)


async def test_send_gcode_accepts_config_entry_id_and_deduplicates(hass):
    """Ensure config entry IDs are accepted and deduplicated."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="test-uuid",
        entry_id="entry_fallback",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    device_ids = list(hass.data["device_registry"].devices.keys())
    primary_device_id = device_ids[0]

    with patch(
        "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
    ) as mock_call:
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": [primary_device_id, config_entry.entry_id],
                "gcode": "G0",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_call.assert_awaited_once_with(METHODS.PRINTER_GCODE_SCRIPT.value, script="G0")
    assert await async_unload_entry(hass, config_entry)


async def test_send_gcode_identifier_fallback(hass):
    """Ensure identifiers populate entry IDs when config entries are missing."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="test-uuid",
        entry_id="identifier_fallback",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    original_async_get = dev_reg.async_get
    identifier_device_id = "identifier-device"
    identifier_device = SimpleNamespace(
        config_entries=set(),
        primary_config_entry=None,
        identifiers={(DOMAIN, config_entry.entry_id)},
    )

    def async_get_override(device_id):
        if device_id == identifier_device_id:
            return identifier_device
        return original_async_get(device_id)

    with (
        patch.object(dev_reg, "async_get", side_effect=async_get_override),
        patch(
            "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
        ) as mock_call,
    ):
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": [identifier_device_id],
                "gcode": "M105",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_call.assert_awaited_once_with(
        METHODS.PRINTER_GCODE_SCRIPT.value, script="M105"
    )
    assert await async_unload_entry(hass, config_entry)


async def test_send_gcode_skips_device_without_entries(hass):
    """Skip devices that cannot be linked to config entries."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="test-uuid",
        entry_id="orphan_device",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    original_async_get = dev_reg.async_get
    orphan_device_id = "orphan-device"
    orphan_device = SimpleNamespace(
        config_entries=set(),
        primary_config_entry=None,
        identifiers=set(),
    )

    def async_get_override(device_id):
        if device_id == orphan_device_id:
            return orphan_device
        return original_async_get(device_id)

    with (
        patch.object(dev_reg, "async_get", side_effect=async_get_override),
        patch(
            "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
        ) as mock_call,
    ):
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": [orphan_device_id],
                "gcode": "G90",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_call.await_count == 0
    assert await async_unload_entry(hass, config_entry)


async def test_send_gcode_skips_unloaded_entries(hass):
    """Skip devices whose entries are not currently loaded."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="test-uuid",
        entry_id="missing_entry",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    original_async_get = dev_reg.async_get
    missing_device_id = "missing-device"
    missing_device = SimpleNamespace(
        config_entries={"ghost-entry"},
        primary_config_entry=None,
        identifiers=set(),
    )

    def async_get_override(device_id):
        if device_id == missing_device_id:
            return missing_device
        return original_async_get(device_id)

    with (
        patch.object(dev_reg, "async_get", side_effect=async_get_override),
        patch(
            "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
        ) as mock_call,
    ):
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": [missing_device_id],
                "gcode": "G91",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_call.await_count == 0
    assert await async_unload_entry(hass, config_entry)


async def test_send_gcode_unknown_device_is_ignored(hass):
    """Unknown device IDs should be ignored."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="test-uuid",
        entry_id="unknown_device",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    with patch(
        "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
    ) as mock_call:
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": "unknown-device",
                "gcode": "M115",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_call.await_count == 0
    assert await async_unload_entry(hass, config_entry)


@pytest.mark.asyncio
async def test_polling_interval_changes_on_print_state(hass, get_data):
    """Test polling interval changes based on print state transitions."""
    from custom_components.moonraker.const import DOMAIN
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from .const import MOCK_CONFIG

    # Set initial state to standby
    get_data["status"]["print_stats"]["state"] = PRINTSTATES.STANDBY.value

    # Setup coordinator
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="test-uuid",
        entry_id="test_polling",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    coordinator = config_entry.runtime_data.coordinator

    # This covers the polling fallback, i.e. a printer that pushes nothing.
    coordinator._subscribed = False
    coordinator.update_interval = coordinator._target_interval(None)

    # Default should be 30 seconds
    assert coordinator.update_interval == timedelta(seconds=30)

    with patch.object(coordinator, "_schedule_refresh") as mock_refresh:
        # Simulate a state change to printing
        get_data["status"]["print_stats"]["state"] = PRINTSTATES.PRINTING.value
        await coordinator._async_update_data()
        assert coordinator.update_interval == timedelta(seconds=2)
        assert mock_refresh.called

        mock_refresh.reset_mock()

        # Simulate a state change back to standby
        get_data["status"]["print_stats"]["state"] = PRINTSTATES.STANDBY.value
        await coordinator._async_update_data()
        assert coordinator.update_interval == timedelta(seconds=30)
        assert mock_refresh.called

        mock_refresh.reset_mock()

        # Simulate no state change (still standby)
        await coordinator._async_update_data()
        # Should not call _schedule_refresh again
        assert not mock_refresh.called


@pytest.mark.asyncio
async def test_polling_interval_no_change_on_same_state(hass, get_data):
    """Test polling interval does not change or reschedule if state is unchanged."""
    from custom_components.moonraker.const import DOMAIN
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from .const import MOCK_CONFIG

    get_data["status"]["print_stats"]["state"] = PRINTSTATES.STANDBY.value
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="test-uuid",
        entry_id="test_polling2",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    coordinator = config_entry.runtime_data.coordinator

    coordinator._subscribed = False
    coordinator.update_interval = coordinator._target_interval(None)

    with patch.object(coordinator, "_schedule_refresh") as mock_refresh:
        # Call update with the same state
        await coordinator._async_update_data()
        assert not mock_refresh.called
        assert coordinator.update_interval == timedelta(seconds=30)


async def test_setup_entry_assigns_unique_id_from_server_info(hass, get_data):
    """Entry without unique_id gets one assigned from Moonraker server.info."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="uid_test")
    config_entry.add_to_hass(hass)
    assert config_entry.unique_id is None

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.unique_id == "76ae56ef-3391-4f7a-89b4-8cc1cb4d6454"
    entity = er.async_get(hass).async_get("sensor.mainsail_printer_state")
    assert entity is not None
    assert entity.unique_id.startswith("76ae56ef-3391-4f7a-89b4-8cc1cb4d6454_")
    await async_unload_entry(hass, config_entry)


async def test_setup_entry_migrates_legacy_entity_unique_ids(hass, get_data):
    """Legacy entities prefixed with the entry_id are migrated to the uuid prefix."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="legacy")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.unique_id == "76ae56ef-3391-4f7a-89b4-8cc1cb4d6454"

    entity_registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(
        entity_registry, config_entry.entry_id
    ):
        assert not entity.unique_id.startswith("legacy_")
        assert entity.unique_id.startswith("76ae56ef-3391-4f7a-89b4-8cc1cb4d6454_")
    await async_unload_entry(hass, config_entry)


async def test_setup_entry_auth_failure_raises_configentryauthfailed(hass, get_data):
    """Authentication errors during setup surface as ConfigEntryAuthFailed."""
    from moonraker_api import ClientNotAuthenticatedError

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="auth")
    config_entry.add_to_hass(hass)

    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=ClientNotAuthenticatedError,
        ),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await async_setup_entry(hass, config_entry)


async def test_service_is_unregistered_on_last_entry_unload(hass, get_data):
    """The send_gcode service is removed once the last entry unloads."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="srv")
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.services.has_service(DOMAIN, "send_gcode")

    assert await async_unload_entry(hass, config_entry)
    assert not hass.services.has_service(DOMAIN, "send_gcode")


async def test_setup_entry_not_ready_when_no_identifier(hass):
    """Entry setup raises ConfigEntryNotReady when no uuid or hostname is reported."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="test-uuid",
        entry_id="no_identifier",
    )
    config_entry.add_to_hass(hass)

    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            return_value={"state": "ready"},
        ),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, config_entry)


async def test_send_gcode_service_registered_only_once(hass, get_data):
    """Multiple entries register the send_gcode service only once."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test", entry_id="srv_one"
    )
    config_entry.add_to_hass(hass)
    config_entry2 = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test", entry_id="srv_two"
    )
    config_entry2.add_to_hass(hass)

    with patch.object(
        hass.services.__class__, "async_register", wraps=hass.services.async_register
    ) as mock_register:
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state.value == "loaded"
    assert config_entry2.state.value == "loaded"
    send_gcode_calls = [
        call
        for call in mock_register.call_args_list
        if call.args and call.args[:2] == (DOMAIN, "send_gcode")
    ]
    assert len(send_gcode_calls) == 1
    assert hass.services.has_service(DOMAIN, "send_gcode")
    assert await async_unload_entry(hass, config_entry)
    assert await async_unload_entry(hass, config_entry2)


async def test_setup_entry_not_ready_when_first_refresh_fails(
    hass, get_default_api_response
):
    """Entry setup raises ConfigEntryNotReady when the first refresh fails."""

    def side_effect(method, *args, **kwargs):
        if method in (METHODS.PRINTER_INFO.value, METHODS.SERVER_INFO.value):
            return {**get_default_api_response}
        raise Exception

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="test-uuid",
        entry_id="refresh_fail",
    )
    config_entry.add_to_hass(hass)

    with (
        patch("moonraker_api.MoonrakerClient.call_method", side_effect=side_effect),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, config_entry)


async def test_async_migrate_entity_unique_ids(hass):
    """Legacy-prefixed ids migrate while unrelated ids are left untouched."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="new-uuid", entry_id="legacy"
    )
    config_entry.add_to_hass(hass)

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        "sensor", DOMAIN, "legacy_state", config_entry=config_entry
    )
    entity_registry.async_get_or_create(
        "sensor", DOMAIN, "other_prefix_state", config_entry=config_entry
    )

    await _async_migrate_entity_unique_ids(hass, config_entry)

    entity_registry = er.async_get(hass)
    assert (
        entity_registry.async_get_entity_id("sensor", DOMAIN, "new-uuid_state")
        is not None
    )
    assert entity_registry.async_get_entity_id("sensor", DOMAIN, "legacy_state") is None
    assert (
        entity_registry.async_get_entity_id("sensor", DOMAIN, "other_prefix_state")
        is not None
    )


def _make_api_client(is_connected: bool = True) -> MoonrakerApiClient:
    """Build a wrapper client whose underlying MoonrakerClient is mocked."""
    with patch("custom_components.moonraker.api.client.MoonrakerClient") as mock_cls:
        instance = mock_cls.return_value
        instance.is_connected = is_connected
        instance.state = None
        return MoonrakerApiClient("1.2.3.4", None, port=7125, api_key=None)


async def test_async_fetch_data_auth_error_raises_config_entry_auth_failed(hass):
    """A rejected key while fetching surfaces as ConfigEntryAuthFailed."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="fetch_auth"
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass,
        client=_make_api_client(),
        config_entry=config_entry,
        api_device_name="printer",
    )

    with (
        patch(
            "custom_components.moonraker.api.client.MoonrakerApiClient.call_method",
            new_callable=AsyncMock,
            side_effect=ApiAuthError,
        ),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await coordinator.async_fetch_data(METHODS.PRINTER_INFO)


async def test_async_fetch_data_api_error_raises_update_failed(hass):
    """An API error while fetching surfaces as UpdateFailed."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="fetch_api"
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass,
        client=_make_api_client(),
        config_entry=config_entry,
        api_device_name="printer",
    )

    with (
        patch(
            "custom_components.moonraker.api.client.MoonrakerApiClient.call_method",
            new_callable=AsyncMock,
            side_effect=ApiConnectionError,
        ),
        pytest.raises(UpdateFailed),
    ):
        await coordinator.async_fetch_data(METHODS.PRINTER_INFO)


async def test_async_send_data_auth_error_raises_config_entry_auth_failed(hass):
    """A rejected key while sending surfaces as ConfigEntryAuthFailed."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="send_auth"
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass,
        client=_make_api_client(),
        config_entry=config_entry,
        api_device_name="printer",
    )

    with (
        patch(
            "custom_components.moonraker.api.client.MoonrakerApiClient.call_method",
            new_callable=AsyncMock,
            side_effect=ApiAuthError,
        ),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await coordinator.async_send_data(METHODS.PRINTER_EMERGENCY_STOP)


async def test_async_send_data_api_error_raises_update_failed(hass):
    """An API error while sending surfaces as UpdateFailed."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="send_api"
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass,
        client=_make_api_client(),
        config_entry=config_entry,
        api_device_name="printer",
    )

    with (
        patch(
            "custom_components.moonraker.api.client.MoonrakerApiClient.call_method",
            new_callable=AsyncMock,
            side_effect=MoonrakerApiError,
        ),
        pytest.raises(UpdateFailed),
    ):
        await coordinator.async_send_data(METHODS.PRINTER_EMERGENCY_STOP)


async def test_ensure_connected_start_failure_raises_update_failed(hass):
    """A failed reconnect attempt surfaces as UpdateFailed."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="conn_fail"
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass,
        client=_make_api_client(is_connected=False),
        config_entry=config_entry,
        api_device_name="printer",
    )

    with (
        patch(
            "custom_components.moonraker.MoonrakerApiClient.start",
            new_callable=AsyncMock,
            side_effect=ApiConnectionError,
        ),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._ensure_connected()


async def test_ensure_connected_starts_when_disconnected(hass):
    """A disconnected client is restarted to reconnect."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="conn_start"
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass,
        client=_make_api_client(is_connected=False),
        config_entry=config_entry,
        api_device_name="printer",
    )

    with patch(
        "custom_components.moonraker.MoonrakerApiClient.start",
        new_callable=AsyncMock,
    ) as mock_start:
        await coordinator._ensure_connected()

    mock_start.assert_awaited_once()


async def test_ensure_connected_quiet_unreachable_logs_debug(hass, caplog):
    """Quiet unreachable mode keeps the reconnect failure at debug level."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options={CONF_OPTION_QUIET_UNREACHABLE: True},
        unique_id="test-uuid",
        entry_id="quiet_unreachable",
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass,
        client=_make_api_client(is_connected=False),
        config_entry=config_entry,
        api_device_name="printer",
    )

    with (
        patch(
            "custom_components.moonraker.coordinator._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ),
        caplog.at_level(logging.DEBUG),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._ensure_connected()

    assert any(
        record.levelno == logging.DEBUG
        and "connection to moonraker down" in record.message
        for record in caplog.records
    )


async def test_setup_entry_generic_exception_with_unique_id_proceeds(hass, caplog):
    """Set up with unavailable entities on a generic setup failure.

    With an existing unique id the entry should not raise ConfigEntryNotReady.
    """
    import logging

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="gen_tol"
    )
    config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=Exception,
        ),
        caplog.at_level(logging.WARNING),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state.value == "loaded"
    assert "unreachable; setting up with unavailable entities" in caplog.text


async def test_async_fetch_data_offline_ok_returns_empty(hass):
    """async_fetch_data with offline_ok returns {} instead of raising."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="off_ok"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data.coordinator

    with patch(
        "custom_components.moonraker.coordinator._async_is_tcp_reachable",
        new_callable=AsyncMock,
        return_value=False,
    ):
        result = await coordinator.async_fetch_data(
            METHODS.PRINTER_INFO, offline_ok=True
        )
    assert result == {}
