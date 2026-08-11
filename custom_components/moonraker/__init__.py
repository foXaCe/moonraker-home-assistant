"""Moonraker integration for Home Assistant."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import Any

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
    PLATFORMS,
    SERVER_INFO_UUID,
    TIMEOUT,
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

    connected = False
    printer_info: dict[str, Any] | None = None
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
                printer_info = await client.client.call_method(
                    METHODS.PRINTER_INFO.value
                )
                server_info = await client.client.call_method(METHODS.SERVER_INFO.value)
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

    await coordinator.async_refresh()

    # Only fail setup on a failed first refresh when the printer answered at
    # setup time. Offline printers keep their entities unavailable instead of
    # leaving the config entry in an endless retry loop.
    if not coordinator.last_update_success and connected:
        raise ConfigEntryNotReady

    entry.runtime_data = MoonrakerData(client=client, coordinator=coordinator)
    coordinator.platforms = list(PLATFORMS)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # A single refresh after all platforms subscribed their printer objects:
    # populating the initial entity values with one API cycle instead of one
    # refresh per platform (each platform refresh would re-query the full object
    # set and slow setup down on real printers).
    await coordinator.async_refresh()

    if connected:
        # Every platform has subscribed its objects by now, so this is the point
        # where the whole set can be pushed by Moonraker instead of polled.
        await coordinator.async_subscribe_objects()

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

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    async def _stop_client(_event: Event) -> None:
        """Stop the Moonraker client on HA shutdown."""
        await client.stop()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop_client)
    )

    _register_send_gcode_service(hass)

    return True


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


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
