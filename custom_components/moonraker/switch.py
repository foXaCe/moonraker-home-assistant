"""Switch platform for Moonraker integration."""

from __future__ import annotations


from typing import Any, cast

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import METHODS
from .coordinator import MoonrakerDataUpdateCoordinator, SLOW_UPDATER_TTL
from .devices import pin
from .devices.base import MoonrakerSwitchSensorDescription
from .entity import BaseMoonrakerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    coordinator = entry.runtime_data.coordinator

    await async_setup_power_device(coordinator, entry, async_add_devices)
    await async_setup_output_pin(coordinator, entry, async_add_devices)


async def _power_device_updater(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> dict[str, Any]:
    return {
        "power_devices": await coordinator.async_fetch_data(
            METHODS.MACHINE_DEVICE_POWER_DEVICES
        )
    }


async def async_setup_output_pin(
    coordinator: MoonrakerDataUpdateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set optional binary sensor platform."""

    switches = await pin.build_output_pin_switches(coordinator)

    coordinator.load_sensor_data(switches)
    async_add_entities(
        [MoonrakerDigitalOutputPin(coordinator, entry, desc) for desc in switches]
    )


async def async_setup_power_device(
    coordinator: MoonrakerDataUpdateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set optional binary sensor platform."""

    power_devices = await coordinator.async_fetch_data(
        METHODS.MACHINE_DEVICE_POWER_DEVICES, offline_ok=True
    )
    if power_devices.get("error"):
        return

    coordinator.add_data_updater(
        _power_device_updater,
        ttl=SLOW_UPDATER_TTL,
        seed={"power_devices": power_devices},
    )

    sensors = []
    for device in power_devices.get("devices", []):
        desc = MoonrakerSwitchSensorDescription(
            key=device["device"],
            sensor_name=device["device"],
            name=device["device"].replace("_", " ").title(),
            icon="mdi:power",
            subscriptions=[],
        )
        sensors.append(desc)

    coordinator.load_sensor_data(sensors)
    async_add_entities(
        [MoonrakerPowerDeviceSwitchSensor(coordinator, entry, desc) for desc in sensors]
    )


class MoonrakerSwitchSensor(BaseMoonrakerEntity, SwitchEntity):
    """Moonraker switch class."""

    def __init__(
        self,
        coordinator: MoonrakerDataUpdateCoordinator,
        entry: ConfigEntry,
        description: MoonrakerSwitchSensorDescription,
    ) -> None:
        """Initialize the switch class."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self.sensor_name = description.sensor_name
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_name = cast(str | None, description.name)
        self._attr_has_entity_name = True
        self._attr_icon = description.icon
        self.coordinator: MoonrakerDataUpdateCoordinator = coordinator


class MoonrakerPowerDeviceSwitchSensor(MoonrakerSwitchSensor):
    """Moonraker power device switch class."""

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        current_state = False
        # data is None until a refresh succeeds: entities are still built from
        # the cached snapshot when the printer is offline at startup.
        power_devices = (self.coordinator.data or {}).get("power_devices") or {}
        for device in power_devices.get("devices", []):
            if device["device"] == self.sensor_name:
                current_state = device["status"] == "on"
        return current_state

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        await self.coordinator.async_send_data(
            METHODS.MACHINE_DEVICE_POWER_POST_DEVICE,
            {"device": self.sensor_name, "action": "on"},
        )
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        await self.coordinator.async_send_data(
            METHODS.MACHINE_DEVICE_POWER_POST_DEVICE,
            {"device": self.sensor_name, "action": "off"},
        )
        await self.coordinator.async_refresh()


class MoonrakerDigitalOutputPin(MoonrakerSwitchSensor):
    """Moonraker power device switch class."""

    def __init__(
        self,
        coordinator: MoonrakerDataUpdateCoordinator,
        entry: ConfigEntry,
        description: MoonrakerSwitchSensorDescription,
    ) -> None:
        """Init."""
        super().__init__(coordinator, entry, description)
        assert description.sensor_name is not None
        self.pin = description.sensor_name.replace("output_pin ", "")

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        value = (
            (self.coordinator.data or {})
            .get("status", {})
            .get(self.sensor_name, {})
            .get("value")
        )
        return bool(value == 1)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        await self.coordinator.async_send_data(
            METHODS.PRINTER_GCODE_SCRIPT,
            {"script": f"SET_PIN PIN={self.pin} VALUE=1"},
        )
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        await self.coordinator.async_send_data(
            METHODS.PRINTER_GCODE_SCRIPT,
            {"script": f"SET_PIN PIN={self.pin} VALUE=0"},
        )
        await self.coordinator.async_refresh()
