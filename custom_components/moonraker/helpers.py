"""Pure helper functions for the Moonraker integration.

This module contains only pure, side-effect free functions: no Home
Assistant state, no I/O, no globals. Everything here is unit-testable in
isolation.
"""

from __future__ import annotations

import math
import os.path
from datetime import datetime, timedelta, UTC
from typing import Any

from .const import DEFAULT_PORT, PRINTSTATES

_GCODE_ROOT = "gcodes"

IDLE_TIMEOUT_STATE_OPTIONS = (
    "Printing",
    "Ready",
    "Idle",
    "Standby",
    "Paused",
    "Complete",
)
IDLE_TIMEOUT_STATE_MAP = {
    option.casefold(): option for option in IDLE_TIMEOUT_STATE_OPTIONS
}


def normalize_moonraker_port(port: int | str | None) -> int:
    """Return the effective Moonraker port used at runtime."""
    if port is None or port == "":
        return DEFAULT_PORT
    return int(port)


def normalize_gcode_path(filename: str | None) -> tuple[str, str | None]:
    """Return normalized filename and detected root for gcode metadata calls."""
    if not filename:
        return "", None

    normalized = filename.replace("\\", "/").strip()
    if not normalized:
        return "", None

    normalized = normalized.lstrip("/")
    lowered = normalized.casefold()

    root = None
    root_prefix = f"{_GCODE_ROOT}/"
    if lowered.startswith(root_prefix):
        root = _GCODE_ROOT
        normalized = normalized[len(root_prefix) :]
    else:
        marker = f"/{_GCODE_ROOT}/"
        idx = lowered.find(marker)
        if idx != -1:
            root = _GCODE_ROOT
            normalized = normalized[idx + len(marker) :]

    return normalized, root


def strip_gcode_root(path: str | None, root: str | None) -> str:
    """Strip a known root prefix from a path for URL usage."""
    if not path:
        return ""

    normalized = path.replace("\\", "/").strip()
    if not normalized:
        return ""

    normalized = normalized.lstrip("/")
    if not root:
        root_prefix = f"{_GCODE_ROOT}/"
        lowered = normalized.casefold()
        if lowered.startswith(root_prefix):
            return normalized[len(root_prefix) :]
        return normalized

    lowered = normalized.casefold()
    root_prefix = f"{root}/"
    if lowered.startswith(root_prefix):
        return normalized[len(root_prefix) :]

    marker = f"/{root}/"
    idx = lowered.find(marker)
    if idx != -1:
        return normalized[idx + len(marker) :]

    return normalized


def build_thumbnail_path(
    gcode_dir: str, thumbnail_path: str | None, root: str | None
) -> str | None:
    """Build a thumbnail path relative to the gcodes root."""
    normalized = strip_gcode_root(thumbnail_path, root)
    if not normalized:
        return None

    if normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized:
        return None

    if not gcode_dir:
        return normalized

    gcode_dir = gcode_dir.replace("\\", "/").strip("/")
    if not gcode_dir:
        return normalized

    if normalized.startswith(f"{gcode_dir}/"):
        return normalized

    return os.path.join(gcode_dir, normalized)


def format_idle_timeout_state(data: dict[str, Any]) -> str | None:
    """Return the idle timeout state in title case when available."""
    state = data["status"].get("idle_timeout", {}).get("state")
    if state is None:
        return None

    if not isinstance(state, str):
        return None

    normalized = state.replace("_", " ").strip()
    if not normalized:
        return None

    mapped = IDLE_TIMEOUT_STATE_MAP.get(normalized.casefold())
    if mapped is not None:
        return mapped

    return None


def calculate_print_speed(data: dict[str, Any]) -> float | None:
    """Calculate the current print speed in mm/s."""
    state = data["status"]["print_stats"]["state"]
    if state != PRINTSTATES.PRINTING.value:
        return 0.0

    motion_report = data["status"].get("motion_report", {})
    live_velocity = motion_report.get("live_velocity")
    if live_velocity is not None:
        return 0.0 if live_velocity <= 0 else round(live_velocity, 2)

    gcode_move = data["status"].get("gcode_move", {})
    speed = gcode_move.get("speed")
    if speed is None:
        return None

    return 0.0 if speed <= 0 else round(speed, 2)


def _parse_progress(value: Any) -> float | None:
    """Parse and clamp a progress value to [0, 1]."""
    if value is None:
        return None

    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return None


def _get_progress_value(status: Any) -> float | None:
    """Return the print progress reported by display_status or virtual_sdcard."""
    if not isinstance(status, dict):
        return None

    display_status = status.get("display_status")
    if isinstance(display_status, dict):
        progress = _parse_progress(display_status.get("progress"))
        if progress is not None:
            return progress

    virtual_sdcard = status.get("virtual_sdcard")
    if isinstance(virtual_sdcard, dict):
        progress = _parse_progress(virtual_sdcard.get("progress"))
        if progress is not None:
            return progress

    return None


def _as_int(value: Any) -> int | None:
    """Coerce a value to int, returning None on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    """Coerce a value to float, returning None on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_positive_float(value: Any) -> float | None:
    """Coerce a value to a strictly positive float."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number <= 0:
        return None

    return number


def _coerce_positive_int(value: Any) -> int | None:
    """Coerce a value to a strictly positive int."""
    number = _coerce_positive_float(value)
    if number is None:
        return None

    return int(round(number, 0))


def calculate_print_progress(data: Any) -> float:
    """Calculate print progress using file-relative progress when available."""
    if not isinstance(data, dict):
        return 0.0

    status = data.get("status")
    if not isinstance(status, dict):
        return 0.0

    print_stats = status.get("print_stats")
    if not isinstance(print_stats, dict):
        print_stats = {}

    virtual_sdcard = status.get("virtual_sdcard")
    if not isinstance(virtual_sdcard, dict):
        virtual_sdcard = {}

    file_position = virtual_sdcard.get("file_position")
    gcode_start_byte = data.get("gcode_start_byte")
    gcode_end_byte = data.get("gcode_end_byte")
    filename = print_stats.get("filename")

    if filename:
        start = _as_int(gcode_start_byte)
        end = _as_int(gcode_end_byte)
        position = _as_int(file_position)
        if start is not None and end is not None and position is not None:
            if end > start and end > 0:
                if position <= start:
                    return 0.0
                if position >= end:
                    return 1.0

                current_position = position - start
                max_position = end - start
                if current_position > 0 and max_position > 0:
                    return max(0.0, min(current_position / max_position, 1.0))

    progress = _get_progress_value(status)
    return progress if progress is not None else 0.0


def calculate_pct_job(data: dict[str, Any]) -> float:
    """Get a pct estimate of the job based on a mix of progress value and filament used.

    This strategy is inline with Mainsail estimate.
    """
    print_expected_duration = data["estimated_time"]
    filament_used = data["status"]["print_stats"]["filament_used"]
    expected_filament = data["filament_total"]
    divider = 0
    time_pct: float = 0
    filament_pct = 0
    progress = _get_progress_value(data.get("status", {}))
    if progress is None:
        progress = 0.0

    if print_expected_duration != 0:
        time_pct = progress
        divider += 1

    if expected_filament != 0:
        filament_pct = 1.0 * filament_used / expected_filament
        divider += 1

    if divider == 0:
        return progress

    return (time_pct + filament_pct) / divider


def calculate_eta(data: dict[str, Any]) -> datetime | None:
    """Calculate ETA of current print."""
    percent_job = calculate_pct_job(data)
    if (
        data["status"]["print_stats"]["state"] != PRINTSTATES.PRINTING.value
        or data["status"]["print_stats"]["print_duration"] <= 0
        or percent_job <= 0
        or percent_job >= 1
    ):
        return None

    time_left = (data["status"]["print_stats"]["print_duration"] / percent_job) - data[
        "status"
    ]["print_stats"]["print_duration"]

    eta = datetime.now(UTC) + timedelta(seconds=time_left)
    # Round to nearest minute by adding 30s bias before truncating seconds
    return (eta + timedelta(seconds=30)).replace(second=0, microsecond=0)


def calculate_current_layer(data: dict[str, Any]) -> int:
    """Calculate current layer."""
    print_stats = data["status"].get("print_stats", {})
    print_duration = print_stats.get("print_duration")
    filename = print_stats.get("filename") or ""
    if not filename:
        filename = data["status"].get("virtual_sdcard", {}).get("file_path") or ""

    if (
        print_stats.get("state") != PRINTSTATES.PRINTING.value
        or filename == ""
        or print_duration is None
        or print_duration <= 0
    ):
        return 0

    info = print_stats.get("info")
    if not isinstance(info, dict):
        info = {}
    virtual_sdcard = data["status"].get("virtual_sdcard", {})
    virtual_current_layer = _coerce_positive_int(virtual_sdcard.get("current_layer"))

    current_layer_raw = info.get("current_layer")
    current_layer = _as_int(current_layer_raw)
    if current_layer is None:
        current_layer_float = _as_float(current_layer_raw)
        if current_layer_float is not None:
            current_layer = int(current_layer_float)

    if current_layer is not None and current_layer > 0:
        return current_layer

    if virtual_current_layer is not None and virtual_current_layer > 0:
        return virtual_current_layer

    calculated_layer = 0
    layer_height = _as_float(data.get("layer_height"))
    if layer_height is not None and layer_height > 0:
        toolhead = data["status"].get("toolhead", {})
        position = toolhead.get("position")
        if position and len(position) >= 3:
            first_layer_height = _as_float(data.get("first_layer_height"))
            if first_layer_height is None:
                first_layer_height = layer_height
            z_height = _as_float(position[2])

            if z_height is not None:
                progress_height = z_height - (first_layer_height or 0)
                # Use floor to avoid round-threshold jitter from bed compensation.
                calculated_layer = math.floor(progress_height / layer_height) + 1
                if calculated_layer < 0:
                    calculated_layer = 0

    if calculated_layer > 0:
        return calculated_layer

    if current_layer is not None:
        return current_layer

    return 0


def calculate_total_layer(data: dict[str, Any]) -> int:
    """Calculate total layer."""
    print_stats = data.get("status", {}).get("print_stats", {})
    info = print_stats.get("info") or {}

    info_total_layer = _coerce_positive_int(info.get("total_layer"))
    if info_total_layer:
        return info_total_layer

    virtual_sdcard = data.get("status", {}).get("virtual_sdcard", {})
    virtual_total_layer = _coerce_positive_int(virtual_sdcard.get("total_layer"))
    if virtual_total_layer:
        return virtual_total_layer

    layer_count = _coerce_positive_int(data.get("layer_count"))
    if layer_count:
        return layer_count

    layer_height = _coerce_positive_float(data.get("layer_height"))
    object_height = _coerce_positive_float(data.get("object_height"))
    if layer_height and object_height:
        first_layer_height = _coerce_positive_float(data.get("first_layer_height"))
        if not first_layer_height:
            first_layer_height = layer_height

        remaining_height = max(0.0, object_height - first_layer_height)
        total_layers = int(round(remaining_height / layer_height, 0)) + 1
        return max(total_layers, 0)

    return 0


def convert_time(time_s: float) -> str:
    """Convert time in seconds to a human readable string."""
    return (
        f"{round(time_s // 3600)}h {round(time_s % 3600 // 60)}m {round(time_s % 60)}s"
    )


def calculate_memory_used(data: dict[str, Any]) -> float | None:
    """Calculate memory used."""
    system_info = data.get("system_info") or {}
    cpu_info = system_info.get("cpu_info") or {}
    total_memory = cpu_info.get("total_memory")
    memavail = data.get("status", {}).get("system_stats", {}).get("memavail")
    if total_memory is None or memavail is None:
        return None
    memory_used = float(total_memory) - float(memavail)
    return memory_used / float(total_memory) * 100
