"""Thermal device description builders for the Moonraker integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    UnitOfRatio,
    UnitOfLength,
    UnitOfPressure,
    UnitOfTemperature,
)

from ..coordinator import MoonrakerDataUpdateCoordinator
from .base import MoonrakerNumberSensorDescription, MoonrakerSensorDescription
from .labels import fr_name


async def build_temperature_sensors(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> list[MoonrakerSensorDescription]:
    """Build temperature sensor descriptions from the printer object list."""

    temperature_keys = [
        "temperature_sensor",
        "temperature_fan",
        "temperature_probe",
        "tmc2240",
        "bme280",
        "htu21d",
        "lm75",
        "aht10",
        "aht20_f",
        "sht3x",
    ]
    environmental_keys = [
        "bme280",
        "htu21d",
        "aht10",
        "aht20_f",
        "sht3x",
    ]
    # Stepper drivers expose a "temperature" field that stays null unless the
    # driver actually reports a die temperature, so they are probed before an
    # entity is created for them.
    driver_keys = ["tmc2240"]

    sensors: list[MoonrakerSensorDescription] = []
    object_list = coordinator.objects_list or {"objects": []}
    objects = set(object_list.get("objects", []))

    # Build a set of names that already have a generic temperature_sensor <name>
    # This will be used to deduplicate sensors reported both as a generic temperature_sensor
    # and as a temperature sensor exposed via a klipper module (eg. BME280)
    generic_temp_names = set()
    for obj in objects:
        parts = obj.split(maxsplit=1)
        if len(parts) == 2 and parts[0] == "temperature_sensor":
            generic_temp_names.add(parts[1])

    # Collect every object that needs discovery (environmental sensors and hall
    # filament width sensors) so they can be queried in a single request.
    discovery_objects: dict[str, Any] = {}
    for obj in object_list.get("objects", []):
        split_obj = obj.split()
        if not split_obj:
            continue
        if split_obj[0] in environmental_keys and len(split_obj) > 1:
            discovery_objects[obj] = None
        elif split_obj[0] in driver_keys and len(split_obj) > 1:
            discovery_objects[obj] = ["temperature"]
        elif split_obj[0] == "hall_filament_width_sensor":
            discovery_objects[obj] = None

    discovery_status = await coordinator.async_discover_objects(discovery_objects)

    for obj in object_list.get("objects", []):
        split_obj = obj.split()

        if not split_obj:
            continue
        if split_obj[0] in temperature_keys and len(split_obj) > 1:
            # A driver that reports no die temperature would only ever produce an
            # unknown sensor, so it is skipped entirely.
            if (
                split_obj[0] in driver_keys
                and (discovery_status.get(obj) or {}).get("temperature") is None
            ):
                continue
            # If we already have a temperature_sensor <name>, don't also create a Temp entity
            # from bme280/aht10/etc for the same <name>.
            if not (
                split_obj[0] in environmental_keys
                and split_obj[1] in generic_temp_names
            ):
                desc = MoonrakerSensorDescription(
                    key=f"{split_obj[0]}_{split_obj[1]}",
                    status_key=obj,
                    name=fr_name(
                        "temp",
                        split_obj[1].removesuffix("_temp").replace("_", " ").title(),
                    ),
                    value_fn=lambda sensor: sensor.coordinator.data["status"][
                        sensor.status_key
                    ]["temperature"],
                    subscriptions=[(obj, "temperature")],
                    icon="mdi:thermometer",
                    unit=UnitOfTemperature.CELSIUS,
                    state_class=SensorStateClass.MEASUREMENT,
                    suggested_display_precision=2,
                )
                sensors.append(desc)

            if split_obj[0] in environmental_keys:
                status = discovery_status.get(obj, {})

                if "pressure" in status:
                    desc = MoonrakerSensorDescription(
                        key=f"{split_obj[0]}_{split_obj[1]}_pressure",
                        status_key=obj,
                        name=fr_name(
                            "pressure", split_obj[1].replace("_", " ").title()
                        ),
                        value_fn=lambda sensor: sensor.coordinator.data["status"][
                            sensor.status_key
                        ]["pressure"],
                        subscriptions=[(obj, "pressure")],
                        icon="mdi:gauge",
                        unit=UnitOfPressure.HPA,
                        state_class=SensorStateClass.MEASUREMENT,
                        suggested_display_precision=1,
                    )
                    sensors.append(desc)

                if "humidity" in status:
                    desc = MoonrakerSensorDescription(
                        key=f"{split_obj[0]}_{split_obj[1]}_humidity",
                        status_key=obj,
                        name=fr_name(
                            "humidity", split_obj[1].replace("_", " ").title()
                        ),
                        value_fn=lambda sensor: sensor.coordinator.data["status"][
                            sensor.status_key
                        ]["humidity"],
                        subscriptions=[(obj, "humidity")],
                        icon="mdi:water-percent",
                        unit=UnitOfRatio.PERCENTAGE,
                        state_class=SensorStateClass.MEASUREMENT,
                        suggested_display_precision=0,
                    )
                    sensors.append(desc)

                if "gas" in status:
                    desc = MoonrakerSensorDescription(
                        key=f"{split_obj[0]}_{split_obj[1]}_gas",
                        status_key=obj,
                        name=fr_name("gas", split_obj[1].replace("_", " ").title()),
                        value_fn=lambda sensor: sensor.coordinator.data["status"][
                            sensor.status_key
                        ]["gas"],
                        subscriptions=[(obj, "gas")],
                        icon="mdi:eye",
                        unit=None,
                        state_class=SensorStateClass.MEASUREMENT,
                        suggested_display_precision=0,
                    )
                    sensors.append(desc)
        elif split_obj[0] == "hall_filament_width_sensor":
            # Hall filament width sensor: expose Diameter (mm) and Raw readings
            status = discovery_status.get(obj, {})

            base_key = obj.replace(" ", "_")
            base_name = (
                split_obj[1].replace("_", " ").title()
                if len(split_obj) > 1
                else "Filament Width Sensor"
            )

            if "Diameter" in status:
                sensors.append(
                    MoonrakerSensorDescription(
                        key=f"{base_key}_diameter",
                        status_key=obj,
                        name=fr_name("diameter", base_name),
                        value_fn=lambda sensor: sensor.coordinator.data["status"][
                            sensor.status_key
                        ]["Diameter"],
                        subscriptions=[(obj, "Diameter")],
                        icon="mdi:tape-measure",
                        unit=UnitOfLength.MILLIMETERS,
                        device_class=SensorDeviceClass.DISTANCE,
                        state_class=SensorStateClass.MEASUREMENT,
                        suggested_display_precision=3,
                    )
                )

            if "Raw" in status:
                sensors.append(
                    MoonrakerSensorDescription(
                        key=f"{base_key}_raw",
                        status_key=obj,
                        name=fr_name("raw", base_name),
                        value_fn=lambda sensor: sensor.coordinator.data["status"][
                            sensor.status_key
                        ]["Raw"],
                        subscriptions=[(obj, "Raw")],
                        icon="mdi:counter",
                        state_class=SensorStateClass.MEASUREMENT,
                        suggested_display_precision=0,
                    )
                )
        elif split_obj[0] == "heater_generic":
            desc = MoonrakerSensorDescription(
                key=f"{split_obj[0]}_{split_obj[1]}_power",
                status_key=obj,
                name=fr_name("power", split_obj[1].replace("_", " ").title()),
                value_fn=lambda sensor: (
                    (
                        sensor.coordinator.data["status"][sensor.status_key]["power"]
                        or 0.0
                    )
                    * 100
                ),
                subscriptions=[(obj, "power")],
                icon="mdi:flash",
                unit=UnitOfRatio.PERCENTAGE,
                state_class=SensorStateClass.MEASUREMENT,
                suggested_display_precision=0,
            )
            sensors.append(desc)

            desc = MoonrakerSensorDescription(
                key=f"{split_obj[0]}_{split_obj[1]}_temperature",
                status_key=obj,
                name=fr_name("temperature", split_obj[1].replace("_", " ").title()),
                value_fn=lambda sensor: sensor.coordinator.data["status"][
                    sensor.status_key
                ]["temperature"],
                subscriptions=[(obj, "temperature")],
                icon="mdi:thermometer",
                unit=UnitOfTemperature.CELSIUS,
                state_class=SensorStateClass.MEASUREMENT,
                suggested_display_precision=2,
            )
            sensors.append(desc)
        elif obj.startswith("extruder") or obj.startswith("heater_bed"):
            if obj.startswith("extruder"):
                icon = "mdi:printer-3d-nozzle-heat"
                base_name = obj
            else:
                icon = "mdi:radiator"
                base_name = "Bed"

            desc = MoonrakerSensorDescription(
                key=f"{obj}_temp",
                status_key=obj,
                name=fr_name("temperature", base_name),
                value_fn=lambda sensor: sensor.coordinator.data["status"][
                    sensor.status_key
                ]["temperature"],
                subscriptions=[(obj, "temperature")],
                icon=icon,
                unit=UnitOfTemperature.CELSIUS,
                state_class=SensorStateClass.MEASUREMENT,
                suggested_display_precision=2,
            )
            sensors.append(desc)

            desc = MoonrakerSensorDescription(
                key=f"{obj}_power",
                status_key=obj,
                name=fr_name("power", base_name),
                value_fn=lambda sensor: (
                    (
                        sensor.coordinator.data["status"][sensor.status_key]["power"]
                        or 0.0
                    )
                    * 100
                ),
                subscriptions=[(obj, "power")],
                icon="mdi:flash",
                unit=UnitOfRatio.PERCENTAGE,
                state_class=SensorStateClass.MEASUREMENT,
                suggested_display_precision=0,
            )
            sensors.append(desc)

    return sensors


async def build_temperature_target_numbers(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> list[MoonrakerNumberSensorDescription]:
    """Build temperature target number descriptions from the printer object list."""

    sensors: list[MoonrakerNumberSensorDescription] = []

    config_settings = coordinator.configfile_settings or {}

    object_list = coordinator.objects_list or {"objects": []}
    for obj in object_list.get("objects", []):
        if obj.startswith("heater_bed"):
            desc = MoonrakerNumberSensorDescription(
                key=f"{obj}_target",
                sensor_name=obj,
                name=fr_name("target", "Bed"),
                status_key="target",
                subscriptions=[(obj, "target")],
                icon="mdi:radiator",
                unit=UnitOfTemperature.CELSIUS,
                update_code="M140 S",
                max_value=130,
                device_class=NumberDeviceClass.TEMPERATURE,
            )
            sensors.append(desc)

        elif obj.startswith("extruder"):
            extruder_val = "0" if obj == "extruder" else obj[-1]

            desc = MoonrakerNumberSensorDescription(
                key=f"{obj}_target",
                sensor_name=obj,
                name=fr_name("target", obj),
                status_key="target",
                subscriptions=[(obj, "target")],
                icon="mdi:printer-3d-nozzle-heat",
                unit=UnitOfTemperature.CELSIUS,
                update_code=f"M104 T{extruder_val} S",
                max_value=350,
                device_class=NumberDeviceClass.TEMPERATURE,
            )
            sensors.append(desc)

        elif obj.startswith("heater_generic"):
            _, _, heater_name = obj.partition(" ")
            display_name = (
                heater_name.replace("_", " ").title()
                if heater_name
                else "Heater Generic"
            )

            settings = config_settings.get(obj)
            if settings is None:
                settings = config_settings.get(obj.lower())
            if settings is None:
                settings = {}

            max_temp = settings.get("max_temp")
            min_temp = settings.get("min_temp")

            if max_temp is None:
                # Without an upper bound there is nothing safe to offer: Home
                # Assistant needs a numeric max, and guessing one for a heater
                # would let the user ask for a temperature the printer refuses.
                # Seen on printers that list a heater with no matching
                # configfile.settings entry.
                continue

            desc = MoonrakerNumberSensorDescription(
                key=f"{obj.replace(' ', '_')}_target_number",
                sensor_name=obj,
                name=fr_name("target", display_name),
                status_key="target",
                subscriptions=[(obj, "target")],
                icon="mdi:radiator",
                unit=UnitOfTemperature.CELSIUS,
                update_code=f"SET_HEATER_TEMPERATURE HEATER={heater_name or 'heater_generic'} TARGET=",
                max_value=float(max_temp),
                min_value=float(min_temp) if min_temp is not None else 0.0,
                device_class=NumberDeviceClass.TEMPERATURE,
            )
            sensors.append(desc)
            coordinator.add_query_objects(obj, "target")

        elif obj.startswith("temperature_fan"):
            object_type, _, object_name = obj.partition(" ")
            fan_name = object_name or object_type
            fan_key = fan_name.replace(" ", "_")
            display_name = fan_name.replace("_", " ").title()

            settings = config_settings.get(obj)
            if settings is None:
                lower_obj = obj.lower()
                settings = config_settings.get(lower_obj)
            if settings is None:
                settings = {}

            max_temp = settings.get("max_temp")
            min_temp = settings.get("min_temp")

            max_value = float(max_temp) if max_temp is not None else 100.0
            min_value = float(min_temp) if min_temp is not None else 0.0

            desc = MoonrakerNumberSensorDescription(
                key=f"{object_type}_{fan_key}_target_control",
                sensor_name=obj,
                name=fr_name("target", display_name),
                status_key="target",
                subscriptions=[(obj, "target")],
                icon="mdi:thermometer",
                unit=UnitOfTemperature.CELSIUS,
                update_code=f"SET_TEMPERATURE_FAN_TARGET FAN={fan_name} TARGET=",
                max_value=max_value,
                min_value=min_value,
                device_class=NumberDeviceClass.TEMPERATURE,
            )
            sensors.append(desc)
            coordinator.add_query_objects(obj, "target")

    return sensors
