"""Base class entity for Moonraker."""

from __future__ import annotations


from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MoonrakerDataUpdateCoordinator


class BaseMoonrakerEntity(CoordinatorEntity[MoonrakerDataUpdateCoordinator]):
    """Base class entity for Moonraker."""

    def __init__(
        self,
        coordinator: MoonrakerDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Init."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self.api_device_name = coordinator.api_device_name

    @property
    def device_info(self) -> DeviceInfo:
        """Entity device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name=self.api_device_name,
            model=DOMAIN,
            manufacturer=DOMAIN,
        )
