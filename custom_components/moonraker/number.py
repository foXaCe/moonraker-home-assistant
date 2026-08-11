"""Number platform for Moonraker integration."""

from __future__ import annotations


import logging
from typing import Any, cast

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfRatio
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import METHODS
from .coordinator import MoonrakerDataUpdateCoordinator
from .devices import fan, pin, thermal
from .devices.base import MoonrakerNumberSensorDescription
from .entity import BaseMoonrakerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
) -> None:
    """Set up the number platform."""
    coordinator = entry.runtime_data.coordinator

    await async_setup_output_pin(coordinator, entry, async_add_devices)
    await async_setup_temperature_target(coordinator, entry, async_add_devices)
    await async_setup_speed_factor(coordinator, entry, async_add_devices)
    await async_setup_fan_speed(coordinator, entry, async_add_devices)


async def async_setup_temperature_target(
    coordinator: MoonrakerDataUpdateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set optional temp target."""

    sensors = await thermal.build_temperature_target_numbers(coordinator)

    coordinator.load_sensor_data(sensors)
    async_add_entities([MoonrakerNumber(coordinator, entry, desc) for desc in sensors])


async def async_setup_output_pin(
    coordinator: MoonrakerDataUpdateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set optional binary sensor platform."""

    numbers = await pin.build_pwm_numbers(coordinator)

    coordinator.load_sensor_data(numbers)
    async_add_entities(
        [MoonrakerPWMOutputPin(coordinator, entry, desc) for desc in numbers]
    )


async def async_setup_speed_factor(
    coordinator: MoonrakerDataUpdateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up speed factor number entity."""

    object_list = coordinator.objects_list or {"objects": []}
    if "gcode_move" not in object_list["objects"]:
        return

    desc = MoonrakerNumberSensorDescription(
        key="speed_factor",
        sensor_name="gcode_move",
        name="Speed Factor",
        status_key="speed_factor",
        subscriptions=[("gcode_move", "speed_factor")],
        icon="mdi:speedometer",
        unit=UnitOfRatio.PERCENTAGE,
        update_code="M220 S",
        max_value=200,
    )

    coordinator.load_sensor_data([desc])
    async_add_entities(
        [MoonrakerNumber(coordinator, entry, desc, value_multiplier=100.0)]
    )


async def async_setup_fan_speed(
    coordinator: MoonrakerDataUpdateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up fan speed number entity."""

    descs = await fan.build_fan_speed_numbers(coordinator)

    if not descs:
        return

    entities: list[NumberEntity] = []
    for desc in descs:
        if desc.key == "fan_speed":
            entities.append(
                MoonrakerFanSpeed(coordinator, entry, desc, value_multiplier=100.0)
            )
        else:
            entities.append(
                MoonrakerKlipperFanSpeed(
                    coordinator, entry, desc, value_multiplier=100.0
                )
            )

    coordinator.load_sensor_data(descs)
    async_add_entities(entities)


_LOGGER = logging.getLogger(__name__)


def _coerce_float(value: Any) -> float | None:
    """Coerce arbitrary values to float."""
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class MoonrakerPWMOutputPin(BaseMoonrakerEntity, NumberEntity):
    """Moonraker PWM output pin class."""

    def __init__(
        self,
        coordinator: MoonrakerDataUpdateCoordinator,
        entry: ConfigEntry,
        description: MoonrakerNumberSensorDescription,
    ) -> None:
        """Initialize the switch class."""
        super().__init__(coordinator, entry)
        assert description.sensor_name is not None
        self.pin = description.sensor_name.replace("output_pin ", "")
        self._attr_mode = NumberMode.SLIDER
        self.entity_description: MoonrakerNumberSensorDescription = description
        self.sensor_name = description.sensor_name
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_name = cast(str | None, description.name)
        self._attr_has_entity_name = True
        self._attr_icon = description.icon
        self.coordinator: MoonrakerDataUpdateCoordinator = coordinator
        self._attr_native_value = self._extract_native_value()

    async def async_set_native_value(self, value: float) -> None:
        """Set native Value."""
        await self.coordinator.async_send_data(
            METHODS.PRINTER_GCODE_SCRIPT,
            {"script": f"SET_PIN PIN={self.pin} VALUE={round(value / 100, 2)}"},
        )
        self._attr_native_value = value
        self.async_write_ha_state()

    def _extract_native_value(self) -> float:
        """Return the current PWM value as percentage."""
        status = self.coordinator.data.get("status", {})
        obj = status.get(self.sensor_name, {})
        raw_value = obj.get("value") if isinstance(obj, dict) else None
        coerced = _coerce_float(raw_value)
        return coerced * 100 if coerced is not None else 0.0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self._extract_native_value()
        self.async_write_ha_state()


class MoonrakerNumber(BaseMoonrakerEntity, NumberEntity):
    """Generic Moonraker number class."""

    def __init__(
        self,
        coordinator: MoonrakerDataUpdateCoordinator,
        entry: ConfigEntry,
        description: MoonrakerNumberSensorDescription,
        value_multiplier: float = 1.0,
    ) -> None:
        """Initialize the number class."""
        super().__init__(coordinator, entry)
        self._attr_mode = NumberMode.SLIDER
        self.entity_description: MoonrakerNumberSensorDescription = description
        self.sensor_name = description.sensor_name
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_name = cast(str | None, description.name)
        self._attr_has_entity_name = True
        self._attr_icon = description.icon
        self._attr_native_max_value = cast(
            float,
            float(description.max_value) if description.max_value is not None else None,
        )
        self._attr_native_min_value = (
            float(description.min_value) if description.min_value is not None else 0.0
        )
        self._attr_device_class = description.device_class
        self._attr_native_unit_of_measurement = description.unit
        self.update_string = description.update_code
        self.value_multiplier = value_multiplier
        self.coordinator: MoonrakerDataUpdateCoordinator = coordinator
        self._attr_native_value = self._extract_native_value()

    async def async_set_native_value(self, value: float) -> None:
        """Set native Value."""
        await self.coordinator.async_send_data(
            METHODS.PRINTER_GCODE_SCRIPT,
            {"script": f"{self.update_string}{value}"},
        )
        self._attr_native_value = value
        self.async_write_ha_state()

    def _extract_native_value(self) -> float:
        """Return the current number value, falling back to zero when missing."""
        status_key = self.entity_description.status_key
        if status_key is None:
            return 0.0
        status = self.coordinator.data.get("status", {})
        obj = status.get(self.sensor_name, {})
        raw_value = obj.get(status_key) if isinstance(obj, dict) else None
        coerced = _coerce_float(raw_value)
        return coerced * self.value_multiplier if coerced is not None else 0.0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self._extract_native_value()
        self.async_write_ha_state()


class MoonrakerFanSpeed(MoonrakerNumber):
    """Moonraker fan speed number class."""

    async def async_set_native_value(self, value: float) -> None:
        """Set native Value."""
        # Apply the multiplier before sending to printer
        adjusted_value = 255 * (value / 100)
        await self.coordinator.async_send_data(
            METHODS.PRINTER_GCODE_SCRIPT,
            {"script": f"{self.update_string}{int(adjusted_value)}"},
        )
        self._attr_native_value = value
        self.async_write_ha_state()


class MoonrakerKlipperFanSpeed(MoonrakerNumber):
    """Fan speed slider 0..100% that sends 0.0..1.0 to SET_FAN_SPEED."""

    async def async_set_native_value(self, value: float) -> None:
        """Set native value."""
        adjusted_value = round(value / self.value_multiplier, 3)
        await self.coordinator.async_send_data(
            METHODS.PRINTER_GCODE_SCRIPT,
            {"script": f"{self.update_string}{adjusted_value}"},
        )
        self._attr_native_value = value
        self.async_write_ha_state()
