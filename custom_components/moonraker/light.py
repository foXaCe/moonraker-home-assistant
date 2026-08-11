"""Light platform for Moonraker integration."""

from __future__ import annotations


import logging
from typing import Any, cast

from homeassistant.components.light import LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import METHODS
from .coordinator import MoonrakerDataUpdateCoordinator
from .devices import led
from .devices.base import MoonrakerLightSensorDescription
from .entity import BaseMoonrakerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
) -> None:
    """Set up the light platform."""
    coordinator = entry.runtime_data.coordinator

    await async_setup_light(coordinator, entry, async_add_devices)


async def async_setup_light(
    coordinator: MoonrakerDataUpdateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set optional light platform."""

    lights = await led.build_led_lights(coordinator)

    coordinator.load_sensor_data(lights)
    async_add_entities([MoonrakerLED(coordinator, entry, desc) for desc in lights])


_LOGGER = logging.getLogger(__name__)


class MoonrakerLED(BaseMoonrakerEntity, LightEntity):
    """Moonraker LED class."""

    def __init__(
        self,
        coordinator: MoonrakerDataUpdateCoordinator,
        entry: ConfigEntry,
        description: MoonrakerLightSensorDescription,
    ) -> None:
        """Initialize the switch class."""
        super().__init__(coordinator, entry)
        assert description.sensor_name is not None
        self.led_name = " ".join(description.sensor_name.split()[1:])
        self.entity_description = description
        self.sensor_name = description.sensor_name
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_name = cast(str | None, description.name)
        self._attr_has_entity_name = True
        self._attr_icon = description.icon
        self._attr_color_mode = description.color_mode
        self._attr_supported_color_modes = (
            {description.color_mode} if description.color_mode is not None else None
        )
        self._set_attributes_from_coordinator()
        self.coordinator: MoonrakerDataUpdateCoordinator = coordinator

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        current_rgbw = self._attr_rgbw_color or (0, 0, 0, 0)
        curr_r, curr_g, curr_b, curr_w = current_rgbw
        if "rgbw_color" in kwargs:
            r, g, b, w = kwargs["rgbw_color"]
        elif "rgb_color" in kwargs:
            r, g, b = kwargs["rgb_color"]
            w = kwargs.get("white", 0)
        else:
            r, g, b, w = curr_r, curr_g, curr_b, curr_w

        if (
            "brightness" not in kwargs
            and "rgb_color" not in kwargs
            and "rgbw_color" not in kwargs
        ):
            r, g, b, w = 255, 255, 255, 255
        if "brightness" in kwargs:
            target_brightness = kwargs["brightness"]
        else:
            target_brightness = max(r, g, b, w) if max(r, g, b, w) > 0 else 255
        current_max = max(r, g, b, w)
        if current_max > 0:
            scale = target_brightness / 255.0
            norm_factor = 255.0 / current_max
            r = int((r * norm_factor) * scale)
            g = int((g * norm_factor) * scale)
            b = int((b * norm_factor) * scale)
            w = int((w * norm_factor) * scale)
        else:
            r, g, b, w = 0, 0, 0, 0
        await self._set_rgbw(r, g, b, w)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        self._attr_is_on = False
        await self._set_rgbw(0, 0, 0, 0)

    async def _set_rgbw(self, r: int, g: int, b: int, w: int) -> None:
        """Update HA attributes."""
        self._attr_rgb_color = (r, g, b)
        self._attr_rgbw_color = (r, g, b, w)
        self._attr_brightness = max(r, g, b, w)
        self._attr_is_on = self._attr_brightness > 0
        """Set native Value."""
        f_r = round(r / 255.0, 2)
        f_g = round(g / 255.0, 2)
        f_b = round(b / 255.0, 2)
        f_w = round(w / 255.0, 2)
        await self.coordinator.async_send_data(
            METHODS.PRINTER_GCODE_SCRIPT,
            {
                "script": f'SET_LED LED="{self.led_name}" RED={f_r} GREEN={f_g} BLUE={f_b} WHITE={f_w} SYNC=0 TRANSMIT=1'
            },
        )
        self.async_write_ha_state()

    def _set_attributes_from_coordinator(self) -> None:
        try:
            color_data = self.coordinator.data["status"][self.sensor_name][
                "color_data"
            ][0]
            r = int(color_data[0] * 255)
            g = int(color_data[1] * 255)
            b = int(color_data[2] * 255)
            w = int(color_data[3] * 255) if len(color_data) > 3 else 0
            self._set_attributes(r, g, b, w)
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            _LOGGER.debug(
                "Unable to update LED '%s' attributes from coordinator data: %s",
                self.sensor_name,
                exc,
            )

    def _set_attributes(self, r: int, g: int, b: int, w: int) -> None:
        self._attr_is_on = r > 0 or g > 0 or b > 0 or w > 0
        self._attr_brightness = max(r, g, b, w)
        self._attr_rgb_color = (r, g, b)
        self._attr_rgbw_color = (r, g, b, w)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._set_attributes_from_coordinator()
        self.async_write_ha_state()
