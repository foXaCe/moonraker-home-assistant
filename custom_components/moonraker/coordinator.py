"""DataUpdateCoordinator for the Moonraker integration."""

from __future__ import annotations

import asyncio
import logging
import os.path
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from datetime import timedelta
from typing import Any, cast

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import helpers
from .api import MoonrakerApiClient
from .api.exceptions import ApiAuthError, ApiConnectionError, MoonrakerApiError
from .repairs import create_invalid_api_key_issue
from .const import (
    CONF_OPTION_POLLING_RATE,
    CONF_OPTION_QUIET_UNREACHABLE,
    CONF_PORT,
    CONF_URL,
    DEFAULT_PORT,
    DOMAIN,
    METHODS,
    OBJ,
    PRINTSTATES,
    TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

DISCOVERY_CACHE_TTL = 60.0
NOTIFY_STATUS_UPDATE = "notify_status_update"

# Notifications that invalidate data the object subscription does not carry:
# printer.info state, power devices, history, job queue and update status. They
# trigger a refresh so a long polling interval costs no freshness.
NOTIFY_REFRESH_EVENTS = frozenset(
    {
        "notify_klippy_ready",
        "notify_klippy_shutdown",
        "notify_klippy_disconnected",
        "notify_power_changed",
        "notify_history_changed",
        "notify_job_queue_changed",
        "notify_update_refreshed",
        "notify_update_response",
    }
)

# While Moonraker pushes updates, polling is only there to catch what a dropped
# notification would lose, so it runs far less often than the configured rate.
SAFETY_NET_INTERVAL = timedelta(minutes=5)
SLOW_UPDATER_TTL = 60.0

type Updater = Callable[["MoonrakerDataUpdateCoordinator"], Any]


def _ttl_updater(updater: Updater, ttl: float) -> Updater:
    """Wrap an updater so it only re-runs every ``ttl`` seconds."""

    async def _wrapped(coordinator: MoonrakerDataUpdateCoordinator) -> Any:
        now = time.monotonic()
        last = coordinator._updater_times.get(updater)
        if last is not None and now - last < ttl:
            return {}
        result = await updater(coordinator)
        coordinator._updater_times[updater] = now
        return result

    return _wrapped


def _log_unreachable(entry: ConfigEntry, message: str, *args: Any) -> None:
    """Log unreachable-device messages at the configured verbosity."""
    if entry.options.get(CONF_OPTION_QUIET_UNREACHABLE, False):
        _LOGGER.debug(message, *args)
    else:
        _LOGGER.warning(message, *args)


def _entry_port(entry: ConfigEntry) -> int:
    """Return the effective Moonraker port for a config entry."""
    return helpers.normalize_moonraker_port(entry.data.get(CONF_PORT, DEFAULT_PORT))


async def _async_is_tcp_reachable(host: str, port: int | str | None) -> bool:
    """Return whether a TCP connection to the Moonraker endpoint can be opened."""
    writer: asyncio.StreamWriter | None = None
    try:
        async with async_timeout.timeout(TIMEOUT):
            _reader, writer = await asyncio.open_connection(
                host, helpers.normalize_moonraker_port(port)
            )
        return True
    except (TimeoutError, OSError, TypeError, ValueError):
        return False
    finally:
        if writer is not None:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()


async def _printer_objects_updater(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> dict[str, Any]:
    """Fetch the queried printer objects."""
    if not coordinator.query_obj[OBJ]:
        # First refresh of a setup: no platform has subscribed an object yet, so
        # querying an empty object set would be a wasted round-trip.
        coordinator._objects_status = {}
        return {}

    result = cast(
        dict[str, Any],
        await coordinator._async_fetch_data(
            METHODS.PRINTER_OBJECTS_QUERY, coordinator.query_obj
        ),
    )
    coordinator._objects_status = result.get("status") or {}
    return result


async def _printer_info_updater(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> dict[str, Any]:
    """Fetch the printer info."""
    seeded = coordinator.initial_printer_info
    if seeded is not None:
        # Setup just read printer.info to identify the instance; reuse it for the
        # first refresh instead of asking again milliseconds later.
        coordinator.initial_printer_info = None
        return {"printer.info": seeded}

    return {
        "printer.info": await coordinator._async_fetch_data(METHODS.PRINTER_INFO, None)
    }


async def _gcode_file_detail_updater(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> dict[str, Any]:
    """Fetch metadata of the currently printing gcode file.

    Reads the printer objects fetched by ``_printer_objects_updater`` earlier in
    the same refresh cycle instead of re-querying the whole object set: the two
    updaters run in order, so the status is always fresh here.
    """
    filename = ""
    status = coordinator._objects_status
    print_stats = status.get("print_stats") or {}
    filename = print_stats.get("filename") or ""
    if not filename:
        virtual_sdcard = status.get("virtual_sdcard") or {}
        filename = virtual_sdcard.get("file_path") or ""

    # A gcode file does not change while it is being printed, so its metadata is
    # cached per filename. A new print starting is the one moment the same name
    # can point at a re-sliced file, so the cache is dropped there.
    state = print_stats.get("state")
    if state == PRINTSTATES.PRINTING.value and coordinator._gcode_detail_state != state:
        coordinator._gcode_detail_cache = None
    coordinator._gcode_detail_state = state

    return await coordinator._async_get_gcode_file_detail(filename)


class MoonrakerDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching data from the Moonraker API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: MoonrakerApiClient,
        config_entry: ConfigEntry,
        api_device_name: str,
        printer_info: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the coordinator."""
        self.moonraker = client
        self.initial_printer_info = printer_info
        self.platforms: list[str] = []
        self.updaters: list[Updater] = [
            _printer_objects_updater,
            _printer_info_updater,
            _gcode_file_detail_updater,
        ]
        self.hass = hass
        self.config_entry = config_entry
        self.api_device_name = api_device_name
        self.query_obj: dict[str, dict[str, Any]] = {OBJ: {}}
        self.objects_list: dict[str, Any] | None = None
        self.configfile_settings: dict[str, Any] | None = None
        self._objects_status: dict[str, Any] = {}
        self._gcode_detail_cache: tuple[str, dict[str, Any]] | None = None
        self._gcode_detail_state: str | None = None
        self._shared_fetches: dict[METHODS, tuple[float, asyncio.Task[Any]]] = {}
        self._subscribed = False
        self._last_print_state: str | None = None
        self._discovery_cache_time: float | None = None
        self._updater_times: dict[Updater, float] = {}
        self._default_interval = timedelta(
            seconds=config_entry.options.get(CONF_OPTION_POLLING_RATE, 30)
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=self._default_interval,
            config_entry=config_entry,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via the Moonraker API."""
        data: dict[str, Any] = dict(self.data or {})

        for updater in self.updaters:
            data.update(await updater(self))

        await self._refresh_discovery_cache()

        # --- Dynamic polling logic ---
        prev_state = self._last_print_state
        current_state = data.get("status", {}).get("print_stats", {}).get("state")
        if current_state != prev_state:
            self.update_interval = self._target_interval(current_state)
            self._schedule_refresh()
        self._last_print_state = current_state
        # --- end dynamic polling logic ---

        return data

    def _target_interval(self, print_state: str | None) -> timedelta:
        """Return the polling interval matching the current mode.

        Once subscribed, Moonraker pushes every object change, so the fast
        printing cadence buys nothing and polling drops to a safety net. A user
        who configured an even longer rate keeps theirs.
        """
        if self._subscribed:
            return max(self._default_interval, SAFETY_NET_INTERVAL)
        if print_state == PRINTSTATES.PRINTING.value:
            return timedelta(seconds=2)
        return self._default_interval

    async def _refresh_discovery_cache(self) -> None:
        """Refresh the cached objects list and configfile settings.

        The platform setups read these caches instead of issuing their own
        network calls, so that integration setup stays fast even on slow
        printers. The cache is refreshed at most once per
        ``DISCOVERY_CACHE_TTL`` seconds.
        """
        now = time.monotonic()
        if (
            self.objects_list is not None
            and self._discovery_cache_time is not None
            and now - self._discovery_cache_time < DISCOVERY_CACHE_TTL
        ):
            return

        objects_list, config_query = await asyncio.gather(
            self._fetch_or_none(METHODS.PRINTER_OBJECTS_LIST, None),
            self._fetch_or_none(
                METHODS.PRINTER_OBJECTS_QUERY, {OBJ: {"configfile": ["settings"]}}
            ),
        )

        # Moonraker answers errors in-band, so an error payload would otherwise
        # be cached and used as if it were the object list.
        if isinstance(objects_list, dict) and "objects" in objects_list:
            self.objects_list = objects_list
            self._discovery_cache_time = now

        if config_query is not None:
            self.configfile_settings = (
                config_query.get("status", {}).get("configfile", {}).get("settings", {})
            )
            self._discovery_cache_time = now

    async def _fetch_or_none(
        self, query_path: METHODS, query_object: dict[str, Any] | None
    ) -> Any:
        """Fetch an endpoint, returning None when the printer cannot answer."""
        try:
            return await self._async_fetch_data(query_path, query_object)
        except (UpdateFailed, ConfigEntryAuthFailed):
            return None

    async def _async_get_gcode_file_detail(
        self, gcode_filename: str | None
    ) -> dict[str, Any]:
        """Return metadata about the gcode file currently being printed."""
        return_gcode: dict[str, Any] = {
            "thumbnails_path": None,
            "estimated_time": 1,
            "filament_total": 1,
            "layer_count": None,
            "layer_height": None,
            "object_height": None,
            "first_layer_height": None,
            "gcode_start_byte": None,
            "gcode_end_byte": None,
        }
        if not gcode_filename:
            return return_gcode

        # Get prefix of the filename to get the appropriate thumbnail
        normalized_filename, root = helpers.normalize_gcode_path(gcode_filename)
        if not normalized_filename:
            return return_gcode

        if (
            self._gcode_detail_cache is not None
            and self._gcode_detail_cache[0] == normalized_filename
        ):
            return dict(self._gcode_detail_cache[1])

        dirname = os.path.dirname(normalized_filename)

        query_object = {"filename": normalized_filename}
        gcode = await self._async_fetch_data(
            METHODS.SERVER_FILES_METADATA, query_object
        )
        return_gcode["estimated_time"] = gcode.get("estimated_time", 0)
        return_gcode["object_height"] = gcode.get("object_height", 0)
        return_gcode["filament_total"] = gcode.get("filament_total", 0)
        return_gcode["layer_count"] = gcode.get("layer_count", 0)
        return_gcode["layer_height"] = gcode.get("layer_height", 0)
        return_gcode["first_layer_height"] = gcode.get("first_layer_height", 0)
        return_gcode["gcode_start_byte"] = gcode.get("gcode_start_byte")
        return_gcode["gcode_end_byte"] = gcode.get("gcode_end_byte")

        thumbnails = gcode.get("thumbnails")
        if not thumbnails or not isinstance(thumbnails, list):
            self._gcode_detail_cache = (normalized_filename, dict(return_gcode))
            return return_gcode

        best_path = None
        best_size = -1.0
        for thumbnail in thumbnails:
            if not isinstance(thumbnail, dict):
                continue
            relative_path = thumbnail.get("relative_path")
            if not relative_path:
                continue
            size = thumbnail.get("size")
            size_value = None
            if size is not None:
                try:
                    size_value = float(size)
                except (TypeError, ValueError):
                    size_value = None

            if size_value is None:
                if best_path is None:
                    best_path = relative_path
                continue

            if size_value > best_size:
                best_size = size_value
                best_path = relative_path

        if not best_path:
            self._gcode_detail_cache = (normalized_filename, dict(return_gcode))
            return return_gcode

        return_gcode["thumbnails_path"] = helpers.build_thumbnail_path(
            dirname, best_path, root
        )
        self._gcode_detail_cache = (normalized_filename, dict(return_gcode))
        return return_gcode

    async def _async_fetch_data(
        self, query_path: METHODS, query_object: dict[str, Any] | None
    ) -> Any:
        """Fetch data from the Moonraker API, reconnecting when needed."""
        myuuid = str(uuid.uuid4())
        _LOGGER.debug("fetching data, uuid: %s, from: %s", myuuid, query_path.value)
        _LOGGER.debug("fetching, uuid: %s, object: %s", myuuid, query_object)
        await self._ensure_connected()
        try:
            if query_object is None:
                result = await self.moonraker.call_method(query_path.value)
            else:
                result = await self.moonraker.call_method(
                    query_path.value, **query_object
                )
            _LOGGER.debug("Query Result, uuid: %s: %s", myuuid, result)
            return result
        except ApiAuthError as exception:
            await self._raise_auth_failed(exception)
        except (ApiConnectionError, MoonrakerApiError) as exception:
            raise UpdateFailed() from exception

    async def _async_send_data(
        self, query_path: METHODS, query_obj: dict[str, Any] | None
    ) -> None:
        """Send data to the Moonraker API, reconnecting when needed."""
        await self._ensure_connected()
        try:
            if query_obj is None:
                await self.moonraker.call_method(query_path.value)
            else:
                await self.moonraker.call_method(query_path.value, **query_obj)
        except ApiAuthError as exception:
            await self._raise_auth_failed(exception)
        except (ApiConnectionError, MoonrakerApiError) as exception:
            raise UpdateFailed() from exception

    async def async_fetch_data(
        self,
        query_path: METHODS,
        query_obj: dict[str, Any] | None = None,
        quiet: bool = False,
        offline_ok: bool = False,
    ) -> Any:
        """Fetch data from Moonraker.

        When ``offline_ok`` is True and the printer is unreachable, an empty
        mapping is returned instead of raising, so platform setup can proceed
        with entities in an unavailable state.
        """
        try:
            return await self._async_fetch_data(query_path, query_obj)
        except UpdateFailed:
            if offline_ok:
                return {}
            raise

    async def async_subscribe_objects(self) -> None:
        """Subscribe to the printer objects the entities depend on.

        Moonraker then pushes every change over the websocket that is already
        open, so entity values follow the printer instead of waiting for the
        next poll. Polling stays enabled as a safety net: it catches anything a
        dropped notification would otherwise lose.
        """
        if not self.query_obj[OBJ]:
            return

        self.moonraker.set_notification_callback(self._handle_notification)

        try:
            result = await self._async_fetch_data(
                METHODS.PRINTER_OBJECTS_SUBSCRIBE, self.query_obj
            )
        except (UpdateFailed, ConfigEntryAuthFailed):
            self.moonraker.set_notification_callback(None)
            _LOGGER.debug("Could not subscribe to printer objects; polling only")
            return

        self._subscribed = True
        self.update_interval = self._target_interval(self._last_print_state)
        self._schedule_refresh()

        status = (result or {}).get("status")
        if status:
            self._apply_status_update(status)

    @callback
    def _handle_notification(self, method: str, data: Any) -> None:
        """Handle a websocket notification pushed by Moonraker."""
        if method in NOTIFY_REFRESH_EVENTS:
            # These change data the subscription does not carry; drop the TTL
            # windows so the refresh actually re-reads those endpoints.
            self._updater_times.clear()
            self.hass.async_create_task(self.async_request_refresh())
            return

        if method != NOTIFY_STATUS_UPDATE:
            return

        # notify_status_update carries [changed_objects, eventtime].
        if not isinstance(data, list) or not data:
            return
        status = data[0]
        if not isinstance(status, dict) or not status:
            return

        self._apply_status_update(status)
        self.async_set_updated_data(dict(self.data or {}))

    def _apply_status_update(self, status: dict[str, Any]) -> None:
        """Merge a partial status payload into the coordinator data."""
        data = dict(self.data or {})
        merged = dict(data.get("status") or {})

        for obj, values in status.items():
            if isinstance(values, dict) and isinstance(merged.get(obj), dict):
                updated = dict(merged[obj])
                updated.update(values)
                merged[obj] = updated
            else:
                merged[obj] = values

        data["status"] = merged
        self._objects_status = merged
        self.data = data

    async def async_fetch_shared(
        self,
        query_path: METHODS,
        ttl: float = SLOW_UPDATER_TTL,
        offline_ok: bool = False,
    ) -> Any:
        """Fetch an endpoint several platforms need, querying it only once.

        Platform setups run concurrently, so a plain cache would still let two
        of them issue the same call. The pending task is shared instead: the
        second caller awaits the first one's result, and that result is reused
        for ``ttl`` seconds afterwards.
        """
        now = time.monotonic()
        pending = self._shared_fetches.get(query_path)
        if pending is not None and now - pending[0] < ttl:
            return await pending[1]

        task = self.hass.async_create_task(
            self.async_fetch_data(query_path, offline_ok=offline_ok)
        )
        self._shared_fetches[query_path] = (now, task)
        try:
            return await task
        except BaseException:
            # Do not let a failed call poison the cache for the whole TTL.
            self._shared_fetches.pop(query_path, None)
            raise

    async def async_send_data(
        self, query_path: METHODS, query_obj: dict[str, Any] | None = None
    ) -> None:
        """Send data to Moonraker."""
        return await self._async_send_data(query_path, query_obj)

    def add_data_updater(
        self,
        updater: Updater,
        ttl: float | None = None,
        seed: dict[str, Any] | None = None,
    ) -> None:
        """Add a data updater to the refresh cycle.

        When ``ttl`` is set, the updater is only re-run when the previous run is
        older than ``ttl`` seconds; the last value is kept in between. This keeps
        rarely changing endpoints (system info, history, …) from being polled on
        every refresh.

        ``seed`` carries the value a platform already fetched during its setup.
        It is injected into the coordinator data and starts the TTL window, so
        the next refresh does not immediately repeat the same round-trip.
        """
        if seed is not None:
            if self.data is None:
                self.data = dict(seed)
            else:
                self.data.update(seed)
            if ttl is not None:
                self._updater_times[updater] = time.monotonic()
        if ttl is not None:
            updater = _ttl_updater(updater, ttl)
        self.updaters.append(updater)

    def load_sensor_data(self, sensor_list: list[Any]) -> None:
        """Load sensor data, so we can poll the right object."""
        for sensor in sensor_list:
            for subscriptions in sensor.subscriptions:
                self.add_query_objects(subscriptions[0], subscriptions[1])

    def add_query_objects(self, query_object: str, result_key: str | None) -> None:
        """Build the list of object we want to retrieve from the server."""
        if result_key is None:
            self.query_obj[OBJ][query_object] = None
            return

        if (
            query_object in self.query_obj[OBJ]
            and self.query_obj[OBJ][query_object] is None
        ):
            return

        if query_object not in self.query_obj[OBJ]:
            self.query_obj[OBJ][query_object] = []
        if result_key not in self.query_obj[OBJ][query_object]:
            self.query_obj[OBJ][query_object].append(result_key)

    async def _ensure_connected(self) -> None:
        """Ensure the Moonraker websocket is connected, restarting it if needed."""
        if not self.moonraker.is_connected:
            entry = self.config_entry
            assert entry is not None
            if not await _async_is_tcp_reachable(
                str(entry.data.get(CONF_URL)),
                _entry_port(entry),
            ):
                self._log_unreachable(
                    "connection to moonraker down; %s:%s is unreachable",
                    entry.data.get(CONF_URL),
                    _entry_port(entry),
                )
                raise UpdateFailed()
            _LOGGER.warning("connection to moonraker down, restarting")
            try:
                await self.moonraker.start()
            except ApiConnectionError as exception:
                raise UpdateFailed() from exception

    def _log_unreachable(self, message: str, *args: Any) -> None:
        """Log unreachable-device messages at the configured verbosity."""
        entry = self.config_entry
        assert entry is not None
        if entry.options.get(CONF_OPTION_QUIET_UNREACHABLE, False):
            _LOGGER.debug(message, *args)
        else:
            _LOGGER.warning(message, *args)

    async def _raise_auth_failed(self, exception: Exception) -> None:
        """Create a repair issue and raise ConfigEntryAuthFailed."""
        entry = self.config_entry
        assert entry is not None
        await create_invalid_api_key_issue(self.hass, entry)
        raise ConfigEntryAuthFailed("Invalid Moonraker API key") from exception
