"""Diagnostics support for the Moonraker integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import MoonrakerDataUpdateCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data: Any = entry.runtime_data
    coordinator: MoonrakerDataUpdateCoordinator = data.coordinator

    return {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "unique_id": entry.unique_id,
            "data": {
                key: value for key, value in entry.data.items() if key != "api_key"
            },
            "options": entry.options,
        },
        "connection": {
            "connected": coordinator.moonraker.is_connected,
            "last_update_success": coordinator.last_update_success,
            "last_exception": (
                repr(coordinator.last_exception) if coordinator.last_exception else None
            ),
        },
        "printer": {
            "name": coordinator.api_device_name,
            "polled_objects": list(coordinator.query_obj.get("objects", {})),
        },
    }
