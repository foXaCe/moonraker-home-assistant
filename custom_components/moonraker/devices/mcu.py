"""MCU device description builders for the Moonraker integration."""

from __future__ import annotations


from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import UnitOfRatio

from ..coordinator import MoonrakerDataUpdateCoordinator
from .base import MoonrakerSensorDescription
from .labels import fr_name


async def build_mcu_sensors(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> list[MoonrakerSensorDescription]:
    """Build MCU sensor descriptions from the printer object list."""

    sensors: list[MoonrakerSensorDescription] = []
    object_list = coordinator.objects_list or {"objects": []}

    for obj in object_list.get("objects", []):
        split_obj = obj.split()

        if not split_obj:
            continue
        if split_obj[0] == "mcu":
            if len(split_obj) > 1:
                key = f"{split_obj[0]}_{split_obj[1]}"
                name = obj.replace("_", " ").title()
            else:
                key = split_obj[0]
                name = split_obj[0].title()
            desc = MoonrakerSensorDescription(
                key=f"{key}_load",
                status_key=obj,
                name=fr_name("load", name),
                value_fn=lambda sensor: (
                    (
                        (
                            sensor.coordinator.data["status"][sensor.status_key][
                                "last_stats"
                            ]["mcu_task_avg"]
                            + 3
                            * sensor.coordinator.data["status"][sensor.status_key][
                                "last_stats"
                            ]["mcu_task_stddev"]
                        )
                        / 0.0025
                        * 100
                    )
                    if sensor.coordinator.data["status"][sensor.status_key][
                        "last_stats"
                    ]
                    is not None
                    else 0
                ),
                subscriptions=[(obj, "last_stats")],
                icon="mdi:cpu-64-bit",
                state_class=SensorStateClass.MEASUREMENT,
                unit=UnitOfRatio.PERCENTAGE,
                suggested_display_precision=0,
            )
            sensors.append(desc)
            desc = MoonrakerSensorDescription(
                key=f"{key}_awake",
                status_key=obj,
                name=fr_name("awake", name),
                value_fn=lambda sensor: (
                    (
                        sensor.coordinator.data["status"][sensor.status_key][
                            "last_stats"
                        ]["mcu_awake"]
                        / 5
                        * 100
                    )
                    if sensor.coordinator.data["status"][sensor.status_key][
                        "last_stats"
                    ]
                    is not None
                    else 0
                ),
                icon="mdi:cpu-64-bit",
                subscriptions=[(obj, "last_stats")],
                state_class=SensorStateClass.MEASUREMENT,
                unit=UnitOfRatio.PERCENTAGE,
                suggested_display_precision=0,
            )
            sensors.append(desc)

    return sensors
