"""Button platform for Moonraker integration."""

from __future__ import annotations


from collections.abc import Callable
from typing import Any, cast

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import METHODS
from .coordinator import MoonrakerDataUpdateCoordinator
from .devices import macro
from .devices.base import MoonrakerButtonDescription
from .entity import BaseMoonrakerEntity


BUTTONS: tuple[MoonrakerButtonDescription, ...] = (
    MoonrakerButtonDescription(
        key="emergency_stop",
        translation_key="emergency_stop",
        press_fn=lambda button: button.coordinator.async_send_data(
            METHODS.PRINTER_EMERGENCY_STOP
        ),
        icon="mdi:alert-octagon-outline",
        entity_registry_enabled_default=True,
    ),
    MoonrakerButtonDescription(
        key="pause_print",
        translation_key="pause_print",
        press_fn=lambda button: button.coordinator.async_send_data(
            METHODS.PRINTER_PRINT_PAUSE
        ),
        icon="mdi:pause",
        entity_registry_enabled_default=True,
    ),
    MoonrakerButtonDescription(
        key="resume_print",
        translation_key="resume_print",
        press_fn=lambda button: button.coordinator.async_send_data(
            METHODS.PRINTER_PRINT_RESUME
        ),
        icon="mdi:play",
        entity_registry_enabled_default=True,
    ),
    MoonrakerButtonDescription(
        key="cancel_print",
        translation_key="cancel_print",
        press_fn=lambda button: button.coordinator.async_send_data(
            METHODS.PRINTER_PRINT_CANCEL
        ),
        icon="mdi:stop",
        entity_registry_enabled_default=True,
    ),
    MoonrakerButtonDescription(
        key="server_restart",
        translation_key="server_restart",
        press_fn=lambda button: button.coordinator.async_send_data(
            METHODS.SERVER_RESTART
        ),
        icon="mdi:restart",
    ),
    MoonrakerButtonDescription(
        key="host_restart",
        translation_key="host_restart",
        press_fn=lambda button: button.coordinator.async_send_data(
            METHODS.HOST_RESTART
        ),
        icon="mdi:restart",
    ),
    MoonrakerButtonDescription(
        key="firmware_restart",
        translation_key="firmware_restart",
        press_fn=lambda button: button.coordinator.async_send_data(
            METHODS.PRINTER_FIRMWARE_RESTART
        ),
        icon="mdi:restart",
    ),
    MoonrakerButtonDescription(
        key="host_shutdown",
        translation_key="host_shutdown",
        press_fn=lambda button: button.coordinator.async_send_data(
            METHODS.HOST_SHUTDOWN
        ),
        icon="mdi:restart",
    ),
    MoonrakerButtonDescription(
        key="machine_update_refresh",
        translation_key="machine_update_refresh",
        press_fn=lambda button: button.coordinator.async_send_data(
            METHODS.MACHINE_UPDATE_REFRESH
        ),
        icon="mdi:refresh",
    ),
    MoonrakerButtonDescription(
        key="reset_totals",
        translation_key="reset_totals",
        entity_registry_enabled_default=False,
        press_fn=lambda button: button.coordinator.async_send_data(
            METHODS.SERVER_HISTORY_RESET_TOTALS
        ),
        icon="mdi:history",
    ),
    MoonrakerButtonDescription(
        key="start_print_from_queue",
        translation_key="start_print_from_queue",
        press_fn=lambda button: button.coordinator.async_send_data(
            METHODS.SERVER_JOB_QUEUE_START
        ),
        icon="mdi:playlist-play",
    ),
    MoonrakerButtonDescription(
        key="home_x_axis",
        translation_key="home_x_axis",
        press_fn=lambda button: button.coordinator.async_send_data(
            METHODS.PRINTER_GCODE_SCRIPT, {"script": "G28 X"}
        ),
        icon="mdi:axis-x-arrow",
        entity_registry_enabled_default=True,
    ),
    MoonrakerButtonDescription(
        key="home_y_axis",
        translation_key="home_y_axis",
        press_fn=lambda button: button.coordinator.async_send_data(
            METHODS.PRINTER_GCODE_SCRIPT, {"script": "G28 Y"}
        ),
        icon="mdi:axis-y-arrow",
        entity_registry_enabled_default=True,
    ),
    MoonrakerButtonDescription(
        key="home_z_axis",
        translation_key="home_z_axis",
        press_fn=lambda button: button.coordinator.async_send_data(
            METHODS.PRINTER_GCODE_SCRIPT, {"script": "G28 Z"}
        ),
        icon="mdi:axis-z-arrow",
        entity_registry_enabled_default=True,
    ),
    MoonrakerButtonDescription(
        key="home_all_axes",
        translation_key="home_all_axes",
        press_fn=lambda button: button.coordinator.async_send_data(
            METHODS.PRINTER_GCODE_SCRIPT, {"script": "G28"}
        ),
        icon="mdi:axis-arrow",
        entity_registry_enabled_default=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set sensor platform."""
    coordinator = entry.runtime_data.coordinator
    await async_setup_basic_buttons(coordinator, entry, async_add_entities)
    await async_setup_macros(coordinator, entry, async_add_entities)
    await async_setup_services(coordinator, entry, async_add_entities)


async def async_setup_basic_buttons(
    coordinator: MoonrakerDataUpdateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set optional button platform."""
    async_add_entities([MoonrakerButton(coordinator, entry, desc) for desc in BUTTONS])


async def async_setup_macros(
    coordinator: MoonrakerDataUpdateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set optional button platform."""
    macros = await macro.build_macro_buttons(coordinator)
    async_add_entities([MoonrakerButton(coordinator, entry, desc) for desc in macros])


async def async_setup_services(
    coordinator: MoonrakerDataUpdateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create Start, Stop, and Restart buttons for all allowed services."""
    service_buttons = await macro.build_service_buttons(coordinator)
    async_add_entities(
        [MoonrakerButton(coordinator, entry, desc) for desc in service_buttons]
    )


class MoonrakerButton(BaseMoonrakerEntity, ButtonEntity):
    """MoonrakerSensor Sensor class."""

    def __init__(
        self,
        coordinator: MoonrakerDataUpdateCoordinator,
        entry: ConfigEntry,
        description: MoonrakerButtonDescription,
    ) -> None:
        """Intit."""
        super().__init__(coordinator, entry)
        self.coordinator = coordinator
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        if description.translation_key:
            self._attr_translation_key = description.translation_key
        else:
            self._attr_name = cast(str | None, description.name)
        self._attr_has_entity_name = True
        self.entity_description = description
        self._attr_icon = description.icon
        self.invoke_name = description.key
        assert description.press_fn is not None
        self.press_fn: Callable[[Any], Any] = description.press_fn
        self.macro_object = description.macro_object

    async def async_press(self) -> None:
        """Press the button."""
        await self.press_fn(self)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return macro variables as entity attributes."""
        if not self.macro_object:
            return None
        status = self.coordinator.data.get("status") or {}
        macro_values = status.get(self.macro_object)
        if not isinstance(macro_values, dict) or not macro_values:
            return None
        return dict(macro_values)
