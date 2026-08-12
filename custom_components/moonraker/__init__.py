"""Moonraker integration for Home Assistant."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import Any, cast

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import async_get_platforms
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import ConfigType
from moonraker_api import ClientNotAuthenticatedError

from .api import MoonrakerApiClient
from .const import (
    CONF_API_KEY,
    CONF_PRINTER_NAME,
    CONF_TLS,
    CONF_URL,
    DOMAIN,
    HOSTNAME,
    METHODS,
    OBJ,
    PLATFORMS,
    SERVER_INFO_UUID,
    TIMEOUT,
)
from .discovery_cache import (
    PrinterSnapshot,
    async_load_snapshot,
    async_remove_snapshot,
    async_save_snapshot,
)
from .coordinator import (
    MoonrakerDataUpdateCoordinator,
    _async_is_tcp_reachable,
    _entry_port,
    _log_unreachable,
)

_LOGGER = logging.getLogger(__name__)

# Entities are added asynchronously; the registry is only worth comparing to
# them once everything has settled.
STALE_ENTITY_SCAN_DELAY = timedelta(minutes=1)


@dataclass
class MoonrakerData:
    """Runtime data stored on the config entry."""

    client: MoonrakerApiClient
    coordinator: MoonrakerDataUpdateCoordinator


def get_user_name(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """Return the user-defined name of the printer device, if any."""
    device_registry = dr.async_get(hass)
    device_entries = dr.async_entries_for_config_entry(device_registry, entry.entry_id)

    if len(device_entries) < 1:
        return None

    return device_entries[0].name_by_user


async def async_setup(_hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up this integration using YAML is not supported."""
    return True


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate a config entry to a newer version."""
    _LOGGER.info("Migrating %s from version %s", entry.title, entry.version)

    if entry.version == 1:
        hass.config_entries.async_update_entry(entry, version=2)

    _LOGGER.info("Migration of %s to version %s completed", entry.title, entry.version)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""

    url = entry.data[CONF_URL]
    port = _entry_port(entry)
    tls = entry.data.get(CONF_TLS, False)
    api_key = entry.data.get(CONF_API_KEY, "")
    custom_name = get_user_name(hass, entry)
    printer_name = (
        entry.data.get(CONF_PRINTER_NAME) if custom_name is None else custom_name
    )

    client = MoonrakerApiClient(
        url,
        async_get_clientsession(hass, verify_ssl=False),
        port=port,
        api_key=api_key,
        tls=tls,
    )

    cache_key = entry.unique_id or entry.entry_id
    snapshot = await async_load_snapshot(hass, cache_key)

    connected = False
    printer_info: dict[str, Any] | None = None
    objects_list: Any = None
    config_query: Any = None
    api_device_name = entry.title or DOMAIN
    try:
        if not await _async_is_tcp_reachable(url, port):
            _log_unreachable(
                entry,
                "Cannot configure moonraker instance: %s:%s is unreachable",
                url,
                port,
            )
            if entry.unique_id is None:
                raise ConfigEntryNotReady(f"Error connecting to {url}:{port}")
            _LOGGER.warning(
                "Moonraker %s is offline; setting up with unavailable entities",
                entry.title,
            )
        else:
            async with async_timeout.timeout(TIMEOUT):
                await client.start()

                # The identity calls and the discovery cache are independent, so
                # they share one round-trip window instead of four. Discovery is
                # by far the slowest of the four on a real printer, and this
                # hides the others behind it.
                calls = [
                    client.client.call_method(METHODS.PRINTER_INFO.value),
                    client.client.call_method(METHODS.SERVER_INFO.value),
                ]
                if snapshot is None:
                    # Nothing stored for this printer yet, so discovery has to
                    # happen now. Otherwise it runs after setup instead.
                    calls += [
                        client.client.call_method(METHODS.PRINTER_OBJECTS_LIST.value),
                        client.client.call_method(
                            METHODS.PRINTER_OBJECTS_QUERY.value,
                            objects={"configfile": ["settings"]},
                        ),
                    ]

                results = await asyncio.gather(*calls, return_exceptions=True)
                # Identity is required; discovery is not. A failed discovery
                # simply leaves nothing to seed, and the refresh below retries
                # it — and fails setup properly if the printer really is broken.
                for result in results[:2]:
                    if isinstance(result, BaseException):
                        raise result

                printer_info, server_info = cast(
                    tuple[dict[str, Any], dict[str, Any]], tuple(results[:2])
                )
                if len(results) == 4:
                    objects_list, config_query = (
                        None if isinstance(value, BaseException) else value
                        for value in results[2:]
                    )
                connected = True
                _LOGGER.debug("printer.info: %s", printer_info)

                printer_uuid = (
                    server_info.get(SERVER_INFO_UUID) if server_info else None
                ) or printer_info.get(HOSTNAME)
                if not printer_uuid:
                    raise ConfigEntryNotReady(
                        "Moonraker did not report an instance UUID or hostname"
                    )

                api_device_name = (
                    printer_info[HOSTNAME]
                    if printer_name in (None, "")
                    else printer_name
                )

            if entry.unique_id is None:
                hass.config_entries.async_update_entry(entry, unique_id=printer_uuid)
                await _async_migrate_entity_unique_ids(hass, entry)

            hass.config_entries.async_update_entry(entry, title=api_device_name)

    except ConfigEntryNotReady:
        await client.stop()
        raise
    except ClientNotAuthenticatedError as exc:
        _LOGGER.warning("Cannot configure moonraker instance, authentication failed")
        await client.stop()
        raise ConfigEntryAuthFailed("Invalid Moonraker API key") from exc
    except Exception as exc:
        _LOGGER.warning("Cannot configure moonraker instance")
        if entry.unique_id is None:
            await client.stop()
            raise ConfigEntryNotReady(f"Error connecting to {url}:{port}") from exc
        _LOGGER.warning(
            "Moonraker %s unreachable; setting up with unavailable entities",
            entry.title,
        )

    coordinator = MoonrakerDataUpdateCoordinator(
        hass,
        client=client,
        config_entry=entry,
        api_device_name=api_device_name,
        printer_info=printer_info,
    )
    if snapshot is not None:
        coordinator.seed_from_snapshot(snapshot)
    else:
        coordinator.seed_discovery(objects_list, config_query)

    await coordinator.async_refresh()

    # Only fail setup on a failed first refresh when the printer answered at
    # setup time. Offline printers keep their entities unavailable instead of
    # leaving the config entry in an endless retry loop.
    if not coordinator.last_update_success and connected:
        raise ConfigEntryNotReady

    entry.runtime_data = MoonrakerData(client=client, coordinator=coordinator)
    coordinator.platforms = list(PLATFORMS)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if connected:
        # Every platform has registered its objects by now, so this is the point
        # where the whole set can be pushed by Moonraker instead of polled. Done
        # before the refresh: the subscription reply carries the same status the
        # refresh would have queried, which the refresh then reuses.
        await coordinator.async_subscribe_objects()

    # A single refresh after all platforms registered their printer objects:
    # populating the initial entity values with one API cycle instead of one
    # refresh per platform (each platform refresh would re-query the full object
    # set and slow setup down on real printers).
    await coordinator.async_refresh()

    if connected:
        # async_add_entities schedules the entities rather than adding them
        # synchronously, so the registry is only comparable to what this setup
        # created once the loop has drained. Scanning too early would delete
        # perfectly live entities.
        entry.async_on_unload(
            async_call_later(
                hass,
                STALE_ENTITY_SCAN_DELAY,
                partial(_async_remove_stale_entities, hass, entry),
            )
        )

        entry.async_create_background_task(
            hass,
            _async_check_discovery_snapshot(hass, entry, coordinator, snapshot),
            "moonraker discovery snapshot",
        )

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    async def _stop_client(_event: Event) -> None:
        """Stop the Moonraker client on HA shutdown."""
        await client.stop()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop_client)
    )

    _register_send_gcode_service(hass)

    return True


async def _async_check_discovery_snapshot(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: MoonrakerDataUpdateCoordinator,
    cached: PrinterSnapshot | None,
) -> None:
    """Confirm the stored snapshot still describes the printer.

    Runs after setup, so a stale snapshot costs a reload rather than a slow
    start. Without a snapshot, setup just discovered everything and there is
    nothing to re-probe: the result is simply stored for next time.
    """
    cache_key = entry.unique_id or entry.entry_id

    if cached is None:
        fresh = coordinator.take_snapshot()
        if fresh is not None:
            await async_save_snapshot(hass, cache_key, fresh)
        return

    fresh = await _async_probe_printer(coordinator, cached)
    if fresh is None:
        return

    differences = cached.differences(fresh)
    if not differences:
        return

    _LOGGER.debug("Printer differs from its snapshot: %s", "; ".join(differences))

    await async_save_snapshot(hass, cache_key, fresh)

    # One reload per Home Assistant run: if the comparison somehow never
    # settles, the entry must not reload itself forever.
    reloaded: set[str] = hass.data.setdefault(f"{DOMAIN}_snapshot_reloads", set())
    if entry.entry_id in reloaded:
        _LOGGER.debug("Snapshot changed again for %s; not reloading twice", entry.title)
        return
    reloaded.add(entry.entry_id)

    _LOGGER.info("Printer changed since last start, reloading %s", entry.title)
    hass.config_entries.async_schedule_reload(entry.entry_id)


async def _async_probe_printer(
    coordinator: MoonrakerDataUpdateCoordinator,
    cached: PrinterSnapshot,
) -> PrinterSnapshot | None:
    """Ask the printer what it exposes right now."""
    probed: dict[str, Any] = dict.fromkeys(cached.discovery_status)

    calls: list[Any] = [
        coordinator.async_fetch_data(METHODS.PRINTER_OBJECTS_LIST, offline_ok=True),
        coordinator.async_fetch_data(
            METHODS.PRINTER_OBJECTS_QUERY,
            {OBJ: {"configfile": ["settings"]}},
            offline_ok=True,
        ),
    ]
    if probed:
        calls.append(
            coordinator.async_fetch_data(
                METHODS.PRINTER_OBJECTS_QUERY, {OBJ: probed}, offline_ok=True
            )
        )

    results = await asyncio.gather(*calls, return_exceptions=True)

    objects_list = results[0]
    if not isinstance(objects_list, dict) or "objects" not in objects_list:
        return None

    config_query = results[1]
    if not isinstance(config_query, dict):
        return None
    settings = config_query.get("status", {}).get("configfile", {}).get("settings")
    if not isinstance(settings, dict):
        return None

    status: dict[str, Any] = {}
    if len(results) > 2 and isinstance(results[2], dict):
        status = results[2].get("status") or {}

    return PrinterSnapshot(
        objects_list=objects_list,
        configfile_settings=settings,
        discovery_status=status,
        discovery_objects=probed,
    )


@callback
def _async_remove_stale_entities(
    hass: HomeAssistant, entry: ConfigEntry, _now: datetime | None = None
) -> None:
    """Drop registry entries the printer no longer exposes.

    A printer object that disappears (a webcam removed, Spoolman uninstalled, a
    fan that stopped reporting RPM) leaves an entity behind that Home Assistant
    keeps showing as unavailable forever. Anything still in the registry but not
    among the entities this setup just created is one of those.

    Only runs when the printer answered during setup: an unreachable printer
    exposes nothing and must never be a reason to delete an entity. Disabled
    entities are never instantiated, so they are skipped as well.
    """
    data: MoonrakerData | None = getattr(entry, "runtime_data", None)
    if data is None:
        return

    coordinator = data.coordinator
    if coordinator.discovery_degraded or coordinator.objects_list is None:
        # An endpoint that failed produces no entity, which is indistinguishable
        # from one the printer no longer exposes. Removing anything here would
        # delete entities over a transient error.
        _LOGGER.debug("Skipping stale entity scan: discovery was incomplete")
        return

    live_unique_ids = {
        entity.unique_id
        for platform in async_get_platforms(hass, DOMAIN)
        if platform.config_entry is not None
        and platform.config_entry.entry_id == entry.entry_id
        for entity in platform.entities.values()
        if entity.unique_id is not None
    }

    if not live_unique_ids:
        # Nothing was created at all; treat it as a failed setup rather than as
        # a printer that exposes nothing.
        return

    entity_registry = er.async_get(hass)

    for registry_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if registry_entry.disabled_by is not None:
            continue
        if registry_entry.unique_id in live_unique_ids:
            continue

        _LOGGER.info(
            "Removing %s: the printer no longer exposes it",
            registry_entry.entity_id,
        )
        entity_registry.async_remove(registry_entry.entity_id)


@callback
def _register_send_gcode_service(hass: HomeAssistant) -> None:
    """Register the send_gcode service once for all Moonraker entries."""

    async def send_gcode_service(service_call: ServiceCall) -> None:
        """Handle the service call to send g-code."""
        gcode = service_call.data["gcode"]
        raw_device_ids = service_call.data["device_id"]
        dev_reg = dr.async_get(hass)

        if isinstance(gcode, list):
            script = "\n".join(line for line in gcode if line)
        else:
            script = str(gcode)

        if not script.strip():
            _LOGGER.warning("Received empty G-code payload, skipping send")
            return

        if isinstance(raw_device_ids, str):
            device_ids = [raw_device_ids]
        else:
            device_ids = list(raw_device_ids)

        processed_entries: set[str] = set()

        for device_id in device_ids:
            device = dev_reg.async_get(device_id)
            entry_ids: set[str] = set()

            if device is None:
                if device_id in _loaded_entry_ids(hass):
                    entry_ids.add(device_id)
                else:
                    _LOGGER.warning("Unknown Moonraker device_id %s", device_id)
                    continue
            else:
                if getattr(device, "config_entries", None):
                    entry_ids.update(device.config_entries)
                if device.primary_config_entry:
                    entry_ids.add(device.primary_config_entry)
                if not entry_ids:
                    for domain, identifier in device.identifiers:
                        if domain == DOMAIN:
                            entry_ids.add(identifier)

            for entry_id in entry_ids:
                if entry_id not in _loaded_entry_ids(hass):
                    _LOGGER.warning(
                        "Moonraker device %s entry %s not loaded",
                        device_id,
                        entry_id,
                    )
                    continue

                if entry_id in processed_entries:
                    continue

                processed_entries.add(entry_id)

                _LOGGER.debug(
                    "Sending G-code via entry %s for device %s", entry_id, device_id
                )

                await _loaded_entry_ids(hass)[entry_id].async_send_data(
                    METHODS.PRINTER_GCODE_SCRIPT,
                    {"script": script},
                )

    if hass.services.has_service(DOMAIN, "send_gcode"):
        return

    hass.services.async_register(DOMAIN, "send_gcode", send_gcode_service)


def _loaded_entry_ids(hass: HomeAssistant) -> dict[str, MoonrakerDataUpdateCoordinator]:
    """Return the {entry_id: coordinator} map of loaded Moonraker entries."""
    loaded: dict[str, MoonrakerDataUpdateCoordinator] = {}
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state.value == "loaded":
            data: MoonrakerData | None = getattr(entry, "runtime_data", None)
            if data is not None:
                loaded[entry.entry_id] = data.coordinator
    return loaded


async def _async_migrate_entity_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Migrate entity unique_ids from the entry_id prefix to the entry unique_id."""

    @callback
    def _update_unique_id(entity: er.RegistryEntry) -> dict[str, str] | None:
        old_prefix = f"{entry.entry_id}_"
        if entity.unique_id.startswith(old_prefix):
            new_suffix = entity.unique_id[len(old_prefix) :]
            return {"new_unique_id": f"{entry.unique_id}_{new_suffix}"}
        return None

    await er.async_migrate_entries(hass, entry.entry_id, _update_unique_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    data: MoonrakerData = entry.runtime_data
    coordinator = data.coordinator
    unloaded = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
                if platform in coordinator.platforms
            ]
        )
    )
    if unloaded:
        data.client.set_notification_callback(None)
        # Cancel the scheduled refresh and the request debouncer, otherwise a
        # reloaded entry leaves the previous coordinator ticking behind it.
        await coordinator.async_shutdown()
        await data.client.stop()
        del entry.runtime_data

        remaining = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.state.value == "loaded" and e is not entry
        ]
        if not remaining and hass.services.has_service(DOMAIN, "send_gcode"):
            hass.services.async_remove(DOMAIN, "send_gcode")

    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop the stored snapshot when the printer is removed."""
    await async_remove_snapshot(hass, entry.unique_id or entry.entry_id)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
