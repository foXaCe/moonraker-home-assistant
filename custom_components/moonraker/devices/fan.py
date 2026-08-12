"""Fan device description builders for the Moonraker integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import UnitOfRatio, REVOLUTIONS_PER_MINUTE

from ..coordinator import MoonrakerDataUpdateCoordinator
from .base import MoonrakerNumberSensorDescription, MoonrakerSensorDescription
from .labels import fr_name


async def build_fan_sensors(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> list[MoonrakerSensorDescription]:
    """Build fan sensor descriptions from the printer object list."""

    fan_keys = ["heater_fan", "controller_fan", "fan_generic", "chamber_fan"]

    sensors: list[MoonrakerSensorDescription] = []
    object_list = coordinator.objects_list or {"objects": []}

    # Collect every fan object that needs RPM discovery so it can be queried in
    # a single request.
    discovery_objects: dict[str, Any] = {}
    for obj in object_list.get("objects", []):
        split_obj = obj.split()
        if not split_obj:
            continue
        if split_obj[0] in fan_keys or obj == "fan":
            discovery_objects[obj] = ["rpm"]

    discovery_status = await coordinator.async_discover_objects(discovery_objects)

    for obj in object_list.get("objects", []):
        split_obj = obj.split()

        if not split_obj:
            continue
        if split_obj[0] in fan_keys:
            desc = MoonrakerSensorDescription(
                key=f"{split_obj[0]}_{split_obj[1]}",
                status_key=obj,
                name=fr_name("speed", split_obj[1].replace("_", " ").title()),
                value_fn=lambda sensor: (
                    sensor.coordinator.data["status"][sensor.status_key]["speed"] * 100
                ),
                subscriptions=[(obj, "speed")],
                icon="mdi:fan",
                unit=UnitOfRatio.PERCENTAGE,
                state_class=SensorStateClass.MEASUREMENT,
                suggested_display_precision=0,
            )
            sensors.append(desc)

            rpm = discovery_status.get(obj, {}).get("rpm")

            if rpm:
                desc = MoonrakerSensorDescription(
                    key=f"{split_obj[0]}_{split_obj[1]}_rpm",
                    status_key=obj,
                    name=fr_name("rpm", split_obj[1].replace("_", " ").title()),
                    value_fn=lambda sensor: sensor.coordinator.data["status"][
                        sensor.status_key
                    ]["rpm"],
                    subscriptions=[(obj, "rpm")],
                    icon="mdi:fan",
                    unit=REVOLUTIONS_PER_MINUTE,
                    state_class=SensorStateClass.MEASUREMENT,
                    suggested_display_precision=0,
                )
                sensors.append(desc)
        elif obj == "fan":
            rpm = discovery_status.get(obj, {}).get("rpm")

            if rpm:
                desc = MoonrakerSensorDescription(
                    key="fan_rpm",
                    name=fr_name("rpm", "Ventilateur"),
                    value_fn=lambda sensor: sensor.coordinator.data["status"]["fan"][
                        "rpm"
                    ],
                    subscriptions=[("fan", "rpm")],
                    icon="mdi:fan",
                    unit=REVOLUTIONS_PER_MINUTE,
                    state_class=SensorStateClass.MEASUREMENT,
                    suggested_display_precision=0,
                )
                sensors.append(desc)

    return sensors


async def build_fan_speed_numbers(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> list[MoonrakerNumberSensorDescription]:
    """Build fan speed number descriptions from the printer object list."""

    object_list = coordinator.objects_list or {"objects": []}
    objects = object_list.get("objects", [])

    descs: list[MoonrakerNumberSensorDescription] = []

    # Classic part-cooling fan ([fan]) - use M106 (0-255) but expose as %.
    if "fan" in objects:
        desc = MoonrakerNumberSensorDescription(
            key="fan_speed",
            sensor_name="fan",
            translation_key="fan_speed",
            status_key="speed",
            subscriptions=[("fan", "speed")],
            icon="mdi:fan",
            unit=UnitOfRatio.PERCENTAGE,
            update_code="M106 S",
            max_value=100,
            min_value=0,
        )
        descs.append(desc)

    # Named fans: only fan_generic* fans are exposed here as controllable Number entities.
    # Other fan types (e.g. heater_fan, controller_fan, chamber_fan) are read-only sensors.
    prefixes = ("fan_generic ",)
    for obj in objects:
        if not obj.startswith(prefixes):
            continue

        section, fan_name = obj.split(" ", 1)
        display_name = fan_name.replace("_", " ").title()
        key = f"{section}_{fan_name}_speed".replace(" ", "_")

        desc = MoonrakerNumberSensorDescription(
            key=key,
            sensor_name=obj,
            name=fr_name("speed", display_name),
            status_key="speed",
            subscriptions=[(obj, "speed")],
            icon="mdi:fan",
            unit=UnitOfRatio.PERCENTAGE,
            # Klipper expects SPEED 0.0..1.0 for SET_FAN_SPEED
            update_code=f"SET_FAN_SPEED FAN={fan_name} SPEED=",
            max_value=100,
            min_value=0,
        )
        descs.append(desc)

    return descs
