"""Base entity descriptions for Moonraker devices."""

from __future__ import annotations


from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.components.button import ButtonEntityDescription
from homeassistant.components.light import LightEntityDescription
from homeassistant.components.light.const import ColorMode
from homeassistant.components.number import NumberDeviceClass, NumberEntityDescription
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.switch import SwitchEntityDescription


@dataclass(frozen=True)
class MoonrakerSensorDescription(SensorEntityDescription):
    """Class describing Mookraker sensor entities."""

    value_fn: Callable[[Any], Any] = lambda sensor: None
    sensor_name: str | None = None
    status_key: str | None = None
    icon: str | None = None
    unit: str | None = None
    subscriptions: list[Any] | None = None
    # Optional extra attributes, for sensors whose state alone cannot carry
    # everything the printer reports.
    extra_state_fn: Callable[[Any], dict[str, Any] | None] | None = None


@dataclass(frozen=True)
class MoonrakerNumberSensorDescription(NumberEntityDescription):
    """Class describing Moonraker number entities."""

    sensor_name: str | None = None
    subscriptions: list[Any] | None = None
    icon: str | None = None
    unit: str | None = None
    update_code: str | None = None
    max_value: float | None = None  # type: ignore[assignment]
    min_value: float | None = None  # type: ignore[assignment]
    device_class: NumberDeviceClass | None = None
    status_key: str | None = None


@dataclass(frozen=True)
class MoonrakerSwitchSensorDescription(SwitchEntityDescription):
    """Class describing Mookraker binary_sensor entities."""

    sensor_name: str | None = None
    icon: str | None = None
    subscriptions: list[Any] | None = None


@dataclass(frozen=True)
class MoonrakerLightSensorDescription(LightEntityDescription):
    """Class describing Mookraker light entities."""

    color_mode: ColorMode | None = None
    sensor_name: str | None = None
    icon: str | None = None
    subscriptions: list[Any] | None = None


@dataclass(frozen=True)
class MoonrakerBinarySensorDescription(BinarySensorEntityDescription):
    """Class describing Mookraker binary_sensor entities."""

    is_on_fn: Callable[[Any], bool] | None = None
    sensor_name: str | None = None
    subscriptions: list[Any] | None = None
    icon: str | None = None


@dataclass(frozen=True)
class MoonrakerButtonDescription(ButtonEntityDescription):
    """Class describing Mookraker button entities."""

    press_fn: Callable[..., Any] | None = None
    macro_object: str | None = None
    button_name: str | None = None
    icon: str | None = None
    unit: str | None = None
    entity_registry_enabled_default: bool = False
