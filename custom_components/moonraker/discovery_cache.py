"""Persisted snapshot of what a printer exposes.

Discovering a printer costs several large responses (the object list, the whole
Klipper config, a probe of the thermal and fan objects). None of it changes
between two Home Assistant restarts unless the printer itself changed, so the
result is stored and replayed at startup. The real discovery still runs, but
after setup: if it disagrees with the snapshot, the entry is reloaded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.discovery"


@dataclass(frozen=True)
class PrinterSnapshot:
    """What a printer exposed the last time it was fully discovered."""

    objects_list: dict[str, Any]
    configfile_settings: dict[str, Any]
    discovery_status: dict[str, Any]
    # What was asked to obtain discovery_status. Replaying the exact same query
    # is the only way a later probe can be compared to this one.
    discovery_objects: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Return the JSON-serialisable form."""
        return {
            "objects_list": self.objects_list,
            "configfile_settings": self.configfile_settings,
            "discovery_status": self.discovery_status,
            "discovery_objects": self.discovery_objects,
        }

    @classmethod
    def from_dict(cls, data: Any) -> PrinterSnapshot | None:
        """Rebuild a snapshot, or None when the stored shape is unusable."""
        if not isinstance(data, dict):
            return None

        objects_list = data.get("objects_list")
        if not isinstance(objects_list, dict) or "objects" not in objects_list:
            return None

        settings = data.get("configfile_settings")
        status = data.get("discovery_status")
        probed = data.get("discovery_objects")
        return cls(
            objects_list=objects_list,
            configfile_settings=settings if isinstance(settings, dict) else {},
            discovery_status=status if isinstance(status, dict) else {},
            discovery_objects=probed if isinstance(probed, dict) else {},
        )

    def matches(self, other: PrinterSnapshot) -> bool:
        """Return whether both snapshots describe the same printer."""
        return not self.differences(other)

    def differences(self, other: PrinterSnapshot) -> list[str]:
        """Describe how another snapshot differs from this one.

        Only the shape matters — which objects exist and which of them report a
        value. Measurements move constantly and must not trigger a reload.
        """
        found: list[str] = []

        gained, lost = _diff(
            set(self.objects_list.get("objects", [])),
            set(other.objects_list.get("objects", [])),
        )
        if gained or lost:
            found.append(f"objects gained={sorted(gained)} lost={sorted(lost)}")

        gained, lost = _diff(
            set(self.configfile_settings), set(other.configfile_settings)
        )
        if gained or lost:
            found.append(f"config gained={sorted(gained)} lost={sorted(lost)}")

        gained, lost = _diff(
            _reported_fields(self.discovery_status, self.discovery_objects),
            _reported_fields(other.discovery_status, self.discovery_objects),
        )
        if gained or lost:
            found.append(f"fields gained={sorted(gained)} lost={sorted(lost)}")

        return found


def _diff(before: set[Any], after: set[Any]) -> tuple[set[Any], set[Any]]:
    """Return what the second set gained and lost compared to the first."""
    return after - before, before - after


def _reported_fields(
    status: dict[str, Any], requested: dict[str, Any]
) -> set[tuple[str, str]]:
    """Return the (object, field) pairs that decide which entities exist.

    Only the fields discovery actually asked about are considered. Moonraker
    answers a query with everything the connection is subscribed to, so the rest
    of the payload says more about our own subscription than about the printer.

    Within those fields a null matters: a driver reporting no temperature and a
    fan reporting no rpm get no sensor at all.
    """
    reported: set[tuple[str, str]] = set()
    for name, values in status.items():
        if not isinstance(values, dict):
            continue
        wanted = requested.get(name)
        for field, value in values.items():
            if wanted is not None and field not in wanted:
                continue
            if value is None:
                continue
            reported.add((name, field))
    return reported


def _store(hass: HomeAssistant) -> Store[dict[str, Any]]:
    """Return the store shared by every Moonraker entry."""
    return Store(hass, STORAGE_VERSION, STORAGE_KEY)


async def async_load_snapshot(hass: HomeAssistant, key: str) -> PrinterSnapshot | None:
    """Return the stored snapshot for a printer, if any."""
    data = await _store(hass).async_load()
    if not isinstance(data, dict):
        return None
    return PrinterSnapshot.from_dict(data.get(key))


async def async_save_snapshot(
    hass: HomeAssistant, key: str, snapshot: PrinterSnapshot
) -> None:
    """Store the snapshot for a printer, leaving other printers untouched."""
    store = _store(hass)
    data = await store.async_load()
    if not isinstance(data, dict):
        data = {}
    data[key] = snapshot.as_dict()
    await store.async_save(data)


async def async_remove_snapshot(hass: HomeAssistant, key: str) -> None:
    """Drop the snapshot of a printer that is no longer configured."""
    store = _store(hass)
    data = await store.async_load()
    if not isinstance(data, dict) or key not in data:
        return
    del data[key]
    await store.async_save(data)
