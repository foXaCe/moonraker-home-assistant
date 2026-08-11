"""Update platform for Moonraker integration."""

from __future__ import annotations

import logging

from homeassistant.components.update import UpdateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import METHODS
from .coordinator import MoonrakerDataUpdateCoordinator
from .entity import BaseMoonrakerEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the update platform from machine.update.status."""
    coordinator = entry.runtime_data.coordinator

    machine_status = await coordinator.async_fetch_data(METHODS.MACHINE_UPDATE_STATUS)
    if machine_status.get("error"):
        return

    version_info = machine_status.get("version_info") or {}
    entities = []
    for component, info in version_info.items():
        if component == "system":
            entities.append(
                MoonrakerUpdateEntity(
                    coordinator,
                    entry,
                    component="system",
                    title="System",
                    installed_version="installed",
                    latest_version=(
                        f"{info.get('package_count', 0)} package update(s) available"
                    ),
                )
            )
        elif isinstance(info, dict):
            version = info.get("version")
            remote_version = info.get("remote_version")
            if version is not None and remote_version is not None:
                entities.append(
                    MoonrakerUpdateEntity(
                        coordinator,
                        entry,
                        component=component,
                        title=component,
                        installed_version=str(version),
                        latest_version=str(remote_version),
                    )
                )

    if entities:
        async_add_entities(entities)


class MoonrakerUpdateEntity(BaseMoonrakerEntity, UpdateEntity):
    """Representation of a Moonraker managed component update."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: MoonrakerDataUpdateCoordinator,
        entry: ConfigEntry,
        component: str,
        title: str,
        installed_version: str,
        latest_version: str,
    ) -> None:
        """Initialize the update entity."""
        super().__init__(coordinator, entry)
        self._component = component
        self._attr_unique_id = f"{entry.unique_id}_update_{component}"
        self._attr_name = f"{component.title()} update"
        self._attr_has_entity_name = True
        self._attr_title = title
        self._attr_installed_version = installed_version
        self._attr_latest_version = latest_version

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        machine_update = self.coordinator.data.get("machine_update") or {}
        version_info = machine_update.get("version_info") or {}
        info = version_info.get(self._component)
        if not isinstance(info, dict):
            return

        if self._component == "system":
            self._attr_latest_version = (
                f"{info.get('package_count', 0)} package update(s) available"
            )
        else:
            version = info.get("version")
            remote_version = info.get("remote_version")
            if version is not None:
                self._attr_installed_version = str(version)
            if remote_version is not None:
                self._attr_latest_version = str(remote_version)
        self.async_write_ha_state()
