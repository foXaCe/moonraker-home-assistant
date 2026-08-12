"""Filament information sensors for printers that report it per extruder.

Snapmaker U1 exposes a ``print_task_config`` object holding one entry per
extruder: the loaded filament's colour, vendor, type and so on. Printers that do
not have it simply list no such object, and no sensor is created.
"""

from __future__ import annotations

import logging
from functools import partial
from typing import Any

from ..const import FILAMENT_INFO_FIELDS, FILAMENT_INFO_OBJECT
from ..coordinator import MoonrakerDataUpdateCoordinator
from .base import MoonrakerSensorDescription

_LOGGER = logging.getLogger(__name__)


def _filament_field(sensor: Any, field: str, index: int) -> Any:
    """Return one filament field for one extruder, or None when absent."""
    values = (
        (sensor.coordinator.data.get("status") or {})
        .get(FILAMENT_INFO_OBJECT, {})
        .get(field)
    )
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def _colour(sensor: Any, index: int) -> str | None:
    """Return the filament colour as a hex string, as Home Assistant expects."""
    value = _filament_field(sensor, "filament_color_rgba", index)
    if not value:
        return None
    return f"#{value}"


def _attributes(sensor: Any, index: int) -> dict[str, Any]:
    """Return everything else the printer knows about that filament."""
    attributes: dict[str, Any] = {}
    for field in FILAMENT_INFO_FIELDS:
        if field == "filament_color_rgba":
            continue
        value = _filament_field(sensor, field, index)
        if value is not None:
            attributes[field.removeprefix("filament_")] = value
    return attributes


async def build_filament_sensors(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> list[MoonrakerSensorDescription]:
    """Build one filament sensor per extruder, when the printer reports them."""
    object_list = coordinator.objects_list or {"objects": []}
    if FILAMENT_INFO_OBJECT not in object_list.get("objects", []):
        return []

    discovery = await coordinator.async_discover_objects(
        {FILAMENT_INFO_OBJECT: list(FILAMENT_INFO_FIELDS)}
    )
    colours = (discovery.get(FILAMENT_INFO_OBJECT) or {}).get("filament_color_rgba")
    if not isinstance(colours, list) or not colours:
        _LOGGER.debug("%s reports no filament colour; no sensor", FILAMENT_INFO_OBJECT)
        return []

    # The object is subscribed like any other, so its values arrive with the
    # push updates rather than costing a query per refresh.
    return [_describe(index) for index in range(len(colours))]


def _describe(index: int) -> MoonrakerSensorDescription:
    """Describe the filament sensor of one extruder."""
    return MoonrakerSensorDescription(
        key=f"extruder_{index}_filament",
        name=f"Filament E{index}",
        value_fn=partial(_colour, index=index),
        extra_state_fn=partial(_attributes, index=index),
        subscriptions=[(FILAMENT_INFO_OBJECT, field) for field in FILAMENT_INFO_FIELDS],
        icon="mdi:format-color-highlight",
    )
