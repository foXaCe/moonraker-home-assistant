"""Sensor platform for Moonraker integration."""

from __future__ import annotations


import asyncio
import logging
from typing import Any, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    UnitOfLength,
    UnitOfRatio,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import helpers
from .const import METHODS, PRINTERSTATES, PRINTSTATES, QUEUESTATES
from .coordinator import SLOW_UPDATER_TTL
from .coordinator import MoonrakerDataUpdateCoordinator
from .devices import fan, mcu, thermal
from .devices.base import MoonrakerSensorDescription
from .entity import BaseMoonrakerEntity

_LOGGER = logging.getLogger(__name__)


SENSORS: tuple[MoonrakerSensorDescription, ...] = (
    MoonrakerSensorDescription(
        key="state",
        translation_key="printer_state",
        icon="mdi:printer-3d",
        value_fn=lambda sensor: sensor.coordinator.data["printer.info"]["state"],
        device_class=SensorDeviceClass.ENUM,
        options=PRINTERSTATES.list(),
        subscriptions=[],
    ),
    MoonrakerSensorDescription(
        key="message",
        translation_key="printer_message",
        icon="mdi:message-text-outline",
        value_fn=lambda sensor: sensor.coordinator.data["printer.info"][
            "state_message"
        ],
        subscriptions=[],
    ),
    MoonrakerSensorDescription(
        key="print_state",
        translation_key="current_print_state",
        icon="mdi:printer-3d-nozzle",
        value_fn=lambda sensor: sensor.coordinator.data["status"]["print_stats"][
            "state"
        ],
        device_class=SensorDeviceClass.ENUM,
        options=PRINTSTATES.list(),
        subscriptions=[("print_stats", "state")],
    ),
    MoonrakerSensorDescription(
        key="print_message",
        translation_key="current_print_message",
        icon="mdi:message-text-outline",
        value_fn=lambda sensor: (
            sensor.coordinator.data["status"]["print_stats"]["message"] or None
        ),
        subscriptions=[("print_stats", "message")],
    ),
    MoonrakerSensorDescription(
        key="idle_timeout_state",
        translation_key="idle_timeout_state",
        icon="mdi:timer-sand",
        value_fn=lambda sensor: helpers.format_idle_timeout_state(
            sensor.coordinator.data
        ),
        device_class=SensorDeviceClass.ENUM,
        options=list(helpers.IDLE_TIMEOUT_STATE_OPTIONS),
        subscriptions=[("idle_timeout", "state")],
    ),
    MoonrakerSensorDescription(
        key="display_message",
        translation_key="current_display_message",
        icon="mdi:monitor",
        value_fn=lambda sensor: (
            sensor.coordinator.data["status"]["display_status"]["message"] or None
        ),
        subscriptions=[("display_status", "message")],
    ),
    MoonrakerSensorDescription(
        key="filename",
        translation_key="filename",
        icon="mdi:file",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            sensor.coordinator.data["status"]["print_stats"]["filename"]
        ),
        subscriptions=[("print_stats", "filename")],
    ),
    MoonrakerSensorDescription(
        key="print_projected_total_duration",
        translation_key="print_projected_total_duration",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            (
                sensor.coordinator.data["status"]["print_stats"]["print_duration"]
                / helpers.calculate_pct_job(sensor.coordinator.data)
                if helpers.calculate_pct_job(sensor.coordinator.data) != 0
                else 0
            )
            / 3600
        ),
        subscriptions=[
            ("print_stats", "total_duration"),
            ("display_status", "progress"),
            ("virtual_sdcard", "progress"),
        ],
        icon="mdi:timer",
        unit=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        suggested_display_precision=2,
    ),
    MoonrakerSensorDescription(
        key="print_time_left",
        translation_key="print_time_left",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            (
                (
                    sensor.coordinator.data["status"]["print_stats"]["print_duration"]
                    / helpers.calculate_pct_job(sensor.coordinator.data)
                    if helpers.calculate_pct_job(sensor.coordinator.data) != 0
                    else 0
                )
                - sensor.coordinator.data["status"]["print_stats"]["print_duration"]
            )
            / 3600
        ),
        subscriptions=[
            ("print_stats", "print_duration"),
            ("display_status", "progress"),
            ("virtual_sdcard", "progress"),
        ],
        icon="mdi:timer",
        unit=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        suggested_display_precision=2,
    ),
    MoonrakerSensorDescription(
        key="print_eta",
        translation_key="print_eta",
        value_fn=lambda sensor: helpers.calculate_eta(sensor.coordinator.data),
        subscriptions=[
            ("print_stats", "print_duration"),
            ("display_status", "progress"),
            ("virtual_sdcard", "progress"),
        ],
        icon="mdi:timer",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    MoonrakerSensorDescription(
        key="slicer_print_duration_estimate",
        translation_key="slicer_print_duration_estimate",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            max(0, sensor.coordinator.data["estimated_time"] / 3600)
        ),
        subscriptions=[],
        icon="mdi:timer",
        device_class=SensorDeviceClass.DURATION,
        unit=UnitOfTime.HOURS,
        suggested_display_precision=2,
    ),
    MoonrakerSensorDescription(
        key="slicer_print_time_left_estimate",
        translation_key="slicer_print_time_left_estimate",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            (
                sensor.coordinator.data["estimated_time"]
                - sensor.coordinator.data["status"]["print_stats"]["print_duration"]
            )
            / 3600
            if sensor.coordinator.data["estimated_time"] > 0
            else 0
        ),
        subscriptions=[("print_stats", "print_duration")],
        icon="mdi:timer",
        device_class=SensorDeviceClass.DURATION,
        unit=UnitOfTime.HOURS,
        suggested_display_precision=2,
    ),
    MoonrakerSensorDescription(
        key="print_duration",
        translation_key="print_duration",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            sensor.coordinator.data["status"]["print_stats"]["print_duration"] / 60,
        ),
        subscriptions=[("print_stats", "print_duration")],
        icon="mdi:timer",
        unit=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        suggested_display_precision=2,
    ),
    MoonrakerSensorDescription(
        key="filament_used",
        translation_key="filament_used",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            sensor.coordinator.data["status"]["print_stats"]["filament_used"] / 1000,
        ),
        subscriptions=[("print_stats", "filament_used")],
        icon="mdi:tape-measure",
        unit=UnitOfLength.METERS,
        suggested_display_precision=3,
    ),
    MoonrakerSensorDescription(
        key="progress",
        translation_key="progress",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            helpers.calculate_print_progress(sensor.coordinator.data) * 100
        ),
        subscriptions=[
            ("display_status", "progress"),
            ("virtual_sdcard", "progress"),
            ("virtual_sdcard", "file_position"),
        ],
        icon="mdi:percent",
        unit=UnitOfRatio.PERCENTAGE,
        suggested_display_precision=0,
    ),
    MoonrakerSensorDescription(
        key="print_speed",
        translation_key="print_speed",
        value_fn=lambda sensor: helpers.calculate_print_speed(sensor.coordinator.data),
        subscriptions=[("gcode_move", "speed"), ("motion_report", "live_velocity")],
        icon="mdi:speedometer",
        unit="mm/s",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MoonrakerSensorDescription(
        key="total_layer",
        translation_key="total_layer",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            helpers.calculate_total_layer(sensor.coordinator.data)
        ),
        subscriptions=[
            ("print_stats", "info", "total_layer"),
            ("virtual_sdcard", "total_layer"),
        ],
        icon="mdi:layers-triple",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MoonrakerSensorDescription(
        key="current_layer",
        translation_key="current_layer",
        value_fn=lambda sensor: helpers.calculate_current_layer(
            sensor.coordinator.data
        ),
        subscriptions=[
            ("print_stats", "info", "current_layer"),
            ("virtual_sdcard", "current_layer"),
            ("toolhead", "position"),
        ],
        icon="mdi:layers-edit",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MoonrakerSensorDescription(
        key="toolhead_position_x",
        translation_key="toolhead_position_x",
        value_fn=lambda sensor: sensor.coordinator.data["status"]["toolhead"][
            "position"
        ][0],
        subscriptions=[("toolhead", "position")],
        icon="mdi:axis-x-arrow",
        unit=UnitOfLength.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    MoonrakerSensorDescription(
        key="toolhead_position_y",
        translation_key="toolhead_position_y",
        value_fn=lambda sensor: sensor.coordinator.data["status"]["toolhead"][
            "position"
        ][1],
        subscriptions=[("toolhead", "position")],
        icon="mdi:axis-y-arrow",
        unit=UnitOfLength.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    MoonrakerSensorDescription(
        key="toolhead_position_z",
        translation_key="toolhead_position_z",
        value_fn=lambda sensor: sensor.coordinator.data["status"]["toolhead"][
            "position"
        ][2],
        subscriptions=[("toolhead", "position")],
        icon="mdi:axis-z-arrow",
        unit=UnitOfLength.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    MoonrakerSensorDescription(
        key="object_height",
        translation_key="object_height",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            sensor.coordinator.data["object_height"]
        ),
        subscriptions=[],
        icon="mdi:axis-z-arrow",
        device_class=SensorDeviceClass.DISTANCE,
        unit=UnitOfLength.MILLIMETERS,
    ),
    MoonrakerSensorDescription(
        key="sysload",
        translation_key="system_load",
        value_fn=lambda sensor: (
            sensor.coordinator.data["status"]["system_stats"]["sysload"] or 0
        ),
        subscriptions=[("system_stats", "sysload")],
        icon="mdi:cpu-64-bit",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    MoonrakerSensorDescription(
        key="memused",
        translation_key="memory_used",
        value_fn=lambda sensor: (
            helpers.calculate_memory_used(sensor.coordinator.data) or 0.0
        ),
        subscriptions=[("system_stats", "memavail")],
        icon="mdi:memory",
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfRatio.PERCENTAGE,
        suggested_display_precision=2,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set sensor platform."""
    coordinator = entry.runtime_data.coordinator

    # These groups query independent endpoints, so they are discovered
    # concurrently: setup then costs one round-trip instead of six in a row.
    await asyncio.gather(
        async_setup_basic_sensor(coordinator, entry, async_add_entities),
        async_setup_optional_sensors(coordinator, entry, async_add_entities),
        async_setup_history_sensors(coordinator, entry, async_add_entities),
        async_setup_machine_update_sensors(coordinator, entry, async_add_entities),
        async_setup_queue_sensors(coordinator, entry, async_add_entities),
        async_setup_spoolman_sensors(coordinator, entry, async_add_entities),
    )


async def _machine_system_info_updater(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> dict[str, Any]:
    result = await coordinator.async_fetch_data(METHODS.MACHINE_SYSTEM_INFO)
    return {"system_info": result.get("system_info", {}) if result else {}}


async def async_setup_basic_sensor(
    coordinator: MoonrakerDataUpdateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set basic sensor platform."""
    system_info = await coordinator.async_fetch_shared(
        METHODS.MACHINE_SYSTEM_INFO, offline_ok=True
    )
    coordinator.add_data_updater(
        _machine_system_info_updater,
        ttl=SLOW_UPDATER_TTL,
        seed={"system_info": system_info.get("system_info", {})},
    )
    coordinator.load_sensor_data(list(SENSORS))
    async_add_entities([MoonrakerSensor(coordinator, entry, desc) for desc in SENSORS])


async def async_setup_optional_sensors(
    coordinator: MoonrakerDataUpdateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set optional sensor platform."""

    # Independent discovery queries, run together but kept in a fixed order so
    # generated entity names stay stable.
    thermal_sensors, fan_sensors, mcu_sensors = await asyncio.gather(
        thermal.build_temperature_sensors(coordinator),
        fan.build_fan_sensors(coordinator),
        mcu.build_mcu_sensors(coordinator),
    )
    sensors = [*thermal_sensors, *fan_sensors, *mcu_sensors]

    coordinator.load_sensor_data(sensors)
    async_add_entities([MoonrakerSensor(coordinator, entry, desc) for desc in sensors])


async def _history_updater(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> dict[str, Any]:
    return {
        "history": await coordinator.async_fetch_data(METHODS.SERVER_HISTORY_TOTALS)
    }


async def async_setup_history_sensors(
    coordinator: MoonrakerDataUpdateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set history sensors."""
    history = await coordinator.async_fetch_data(
        METHODS.SERVER_HISTORY_TOTALS, offline_ok=True
    )
    if history.get("error"):
        return

    coordinator.add_data_updater(
        _history_updater, ttl=SLOW_UPDATER_TTL, seed={"history": history}
    )

    sensors = [
        MoonrakerSensorDescription(
            key="total_jobs",
            translation_key="totals_jobs",
            value_fn=lambda sensor: sensor.coordinator.data["history"]["job_totals"][
                "total_jobs"
            ],
            subscriptions=[],
            icon="mdi:numeric",
            unit="Jobs",
            state_class=SensorStateClass.TOTAL_INCREASING,
            suggested_display_precision=0,
        ),
        MoonrakerSensorDescription(
            key="total_print_time",
            translation_key="totals_print_time",
            value_fn=lambda sensor: helpers.convert_time(
                sensor.coordinator.data["history"]["job_totals"]["total_print_time"]
            ),
            subscriptions=[],
            icon="mdi:clock-outline",
        ),
        MoonrakerSensorDescription(
            key="total_filament_used",
            translation_key="totals_filament_used",
            value_fn=lambda sensor: (
                sensor.coordinator.data["history"]["job_totals"]["total_filament_used"]
                / 1000
            ),
            subscriptions=[],
            icon="mdi:clock-outline",
            unit=UnitOfLength.METERS,
            state_class=SensorStateClass.TOTAL_INCREASING,
            suggested_display_precision=2,
        ),
        MoonrakerSensorDescription(
            key="longest_print",
            translation_key="longest_print",
            value_fn=lambda sensor: helpers.convert_time(
                sensor.coordinator.data["history"]["job_totals"]["longest_print"]
            ),
            subscriptions=[],
            icon="mdi:clock-outline",
        ),
    ]

    coordinator.load_sensor_data(sensors)
    async_add_entities([MoonrakerSensor(coordinator, entry, desc) for desc in sensors])


async def _queue_updater(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> dict[str, Any]:
    return {
        "queue": await coordinator.async_fetch_data(METHODS.SERVER_JOB_QUEUE_STATUS)
    }


async def async_setup_queue_sensors(
    coordinator: MoonrakerDataUpdateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Job queue sensors."""
    queue = await coordinator.async_fetch_data(
        METHODS.SERVER_JOB_QUEUE_STATUS, offline_ok=True
    )
    if queue.get("queue_state") is None or queue.get("queued_jobs") is None:
        return

    coordinator.add_data_updater(
        _queue_updater, ttl=SLOW_UPDATER_TTL, seed={"queue": queue}
    )

    sensors = [
        MoonrakerSensorDescription(
            key="queue_state",
            translation_key="queue_state",
            icon="mdi:playlist-play",
            # An unlisted value would make Home Assistant reject the state, so
            # anything Moonraker adds later reads as unknown instead.
            value_fn=lambda sensor: (
                sensor.coordinator.data["queue"]["queue_state"]
                if sensor.coordinator.data["queue"]["queue_state"] in QUEUESTATES.list()
                else None
            ),
            device_class=SensorDeviceClass.ENUM,
            options=QUEUESTATES.list(),
            subscriptions=[("queue_state")],
        ),
        MoonrakerSensorDescription(
            key="queue_count",
            translation_key="jobs_in_queue",
            value_fn=lambda sensor: len(
                sensor.coordinator.data["queue"]["queued_jobs"]
            ),
            subscriptions=[("queued_jobs")],
            icon="mdi:numeric",
            unit="Jobs",
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
        ),
    ]

    coordinator.load_sensor_data(sensors)
    async_add_entities([MoonrakerSensor(coordinator, entry, desc) for desc in sensors])


async def _spoolman_updater(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> dict[str, Any]:
    return {"spoolman": await coordinator.async_fetch_data(METHODS.SERVER_SPOOLMAN_ID)}


async def async_setup_spoolman_sensors(
    coordinator: MoonrakerDataUpdateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Spoolman sensors."""
    spoolman = await coordinator.async_fetch_data(
        METHODS.SERVER_SPOOLMAN_ID, offline_ok=True
    )
    if spoolman.get("error"):
        return

    coordinator.add_data_updater(
        _spoolman_updater, ttl=SLOW_UPDATER_TTL, seed={"spoolman": spoolman}
    )

    sensors = [
        MoonrakerSensorDescription(
            key="spool_id",
            translation_key="spool_id",
            icon="mdi:tape-measure",
            value_fn=lambda sensor: sensor.coordinator.data["spoolman"].get("spool_id"),
            subscriptions=[("spool_id")],
        ),
    ]

    coordinator.load_sensor_data(sensors)
    async_add_entities([MoonrakerSensor(coordinator, entry, desc) for desc in sensors])


async def _machine_update_updater(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> dict[str, Any]:
    return {
        "machine_update": await coordinator.async_fetch_data(
            METHODS.MACHINE_UPDATE_STATUS
        )
    }


async def async_setup_machine_update_sensors(
    coordinator: MoonrakerDataUpdateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Test update available."""
    machine_status = await coordinator.async_fetch_shared(
        METHODS.MACHINE_UPDATE_STATUS, offline_ok=True
    )
    if machine_status.get("error") or not machine_status.get("version_info"):
        return
    coordinator.add_data_updater(
        _machine_update_updater,
        ttl=SLOW_UPDATER_TTL,
        seed={"machine_update": machine_status},
    )
    sensors = []

    for version_info in machine_status["version_info"]:
        if version_info == "system":
            sensors.append(
                MoonrakerSensorDescription(
                    key="machine_update_system",
                    translation_key="machine_update_system",
                    # A count, not a sentence: a sensor state is a value, and
                    # only entity names go through the translations.
                    value_fn=lambda sensor: sensor.coordinator.data["machine_update"][
                        "version_info"
                    ]["system"]["package_count"],
                    subscriptions=[],
                    icon="mdi:update",
                    state_class=SensorStateClass.MEASUREMENT,
                    suggested_display_precision=0,
                    entity_registry_enabled_default=False,
                    entity_category=EntityCategory.DIAGNOSTIC,
                )
            )
        elif (
            "version" in machine_status["version_info"][version_info]
            and "remote_version" in machine_status["version_info"][version_info]
        ):
            sensors.append(
                MoonrakerSensorDescription(
                    key=f"machine_update_{version_info}",
                    name=f"Version {version_info.title()}",
                    status_key=version_info,
                    value_fn=lambda sensor: (
                        lambda v, rv: f"{v} > {rv}" if v != rv else v
                    )(
                        sensor.coordinator.data["machine_update"]["version_info"][
                            sensor.status_key
                        ]["version"],
                        sensor.coordinator.data["machine_update"]["version_info"][
                            sensor.status_key
                        ]["remote_version"],
                    ),
                    subscriptions=[],
                    icon="mdi:update",
                    entity_registry_enabled_default=False,
                    entity_category=EntityCategory.DIAGNOSTIC,
                )
            )
    if len(sensors) > 0:
        coordinator.load_sensor_data(sensors)
        async_add_entities(
            [MoonrakerSensor(coordinator, entry, desc) for desc in sensors]
        )


class MoonrakerSensor(BaseMoonrakerEntity, SensorEntity):
    """MoonrakerSensor Sensor class."""

    def __init__(
        self,
        coordinator: MoonrakerDataUpdateCoordinator,
        entry: ConfigEntry,
        description: MoonrakerSensorDescription,
    ) -> None:
        """Init."""
        super().__init__(coordinator, entry)
        self.coordinator = coordinator
        self.status_key = description.status_key
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        if description.translation_key:
            self._attr_translation_key = description.translation_key
        else:
            self._attr_name = cast(str | None, description.name)
        self._attr_has_entity_name = True
        self.entity_description: MoonrakerSensorDescription = description
        self._attr_native_value = self._evaluate_value_fn()
        self._attr_icon = description.icon
        self._attr_native_unit_of_measurement = description.unit

    def _evaluate_value_fn(self) -> Any:
        """Evaluate the value function, tolerating incomplete printer data."""
        try:
            return self.entity_description.value_fn(self)
        except (KeyError, TypeError, IndexError, AttributeError):
            return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self._evaluate_value_fn()
        self.async_write_ha_state()

    def empty_result_when_not_printing(self, value: Any = "") -> Any:
        """Return a neutral value when no print is running.

        Text sensors report None rather than an empty string: Home Assistant
        shows an empty state as a blank cell, while None reads as "unknown",
        which is what "there is no print to describe" actually means.
        """
        if (
            self.coordinator.data["status"]["print_stats"]["state"]
            != PRINTSTATES.PRINTING.value
        ):
            return None if isinstance(value, str) else 0.0
        return value
