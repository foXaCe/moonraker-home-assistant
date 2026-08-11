"""Output pin device description builders for the Moonraker integration."""

from __future__ import annotations


from ..coordinator import MoonrakerDataUpdateCoordinator
from .base import MoonrakerNumberSensorDescription, MoonrakerSwitchSensorDescription


async def build_output_pin_switches(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> list[MoonrakerSwitchSensorDescription]:
    """Build digital output pin switch descriptions from the printer object list."""

    object_list = coordinator.objects_list or {"objects": []}

    settings = coordinator.configfile_settings or {}

    switches: list[MoonrakerSwitchSensorDescription] = []
    for obj in object_list.get("objects", []):
        if "output_pin" not in obj:
            continue

        if settings.get(obj.lower(), {}).get("pwm"):
            continue

        desc = MoonrakerSwitchSensorDescription(
            key=obj,
            sensor_name=obj,
            name=obj.replace("_", " ").title(),
            icon="mdi:switch",
            subscriptions=[(obj, "value")],
        )
        switches.append(desc)

    return switches


async def build_pwm_numbers(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> list[MoonrakerNumberSensorDescription]:
    """Build PWM output pin number descriptions from the printer object list."""

    object_list = coordinator.objects_list or {"objects": []}

    settings = coordinator.configfile_settings or {}

    numbers: list[MoonrakerNumberSensorDescription] = []
    for obj in object_list.get("objects", []):
        if "output_pin" not in obj:
            continue

        if not settings.get(obj.lower(), {}).get("pwm"):
            continue

        desc = MoonrakerNumberSensorDescription(
            key=obj,
            sensor_name=obj,
            name=obj.replace("_", " ").title(),
            icon="mdi:switch",
            subscriptions=[(obj, "value")],
        )
        numbers.append(desc)

    return numbers
