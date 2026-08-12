# Architecture

High-level overview of the Moonraker Home Assistant integration (`custom_components/moonraker/`).

## Data flow

```
Klipper printer
   └── Moonraker server (WebSocket JSON-RPC, port 7125)
        └── moonraker-api (external client library)
             └── api/client.py (MoonrakerApiClient: reconnect, retry, typed errors)
                  └── coordinator.py (MoonrakerDataUpdateCoordinator)
                       └── Entity platforms (sensor, binary_sensor, button, camera,
                           switch, number, light, update)
```

## Key modules

| Module                                           | Role                                                                        |
| ------------------------------------------------ | --------------------------------------------------------------------------- |
| `__init__.py`                                    | Config entry setup/unload, `async_migrate_entry`, `send_gcode` service      |
| `coordinator.py`                                 | `DataUpdateCoordinator` (typed), dynamic polling, data fetch/send           |
| `config_flow.py`                                 | Config flow + options flow: selectors, reauth, reconfigure, zeroconf        |
| `repairs.py`                                     | Repair flow + issue for invalid API key                                     |
| `diagnostics.py`                                 | `async_get_config_entry_diagnostics` (API key redacted)                     |
| `const.py`                                       | Domain constants, platforms, API methods, config keys (`Final`)             |
| `helpers.py`                                     | Pure functions (print progress/ETA, gcode path, ports)                      |
| `api/`                                           | `client.py` (wrapper + retry/backoff + push notifications), `exceptions.py` |
| `devices/`                                       | Per-device description builders (thermal, fan, mcu, pin, led, macro)        |
| `entity.py`                                      | `BaseMoonrakerEntity` (DeviceInfo, coordinator wiring)                      |
| `sensor.py`, `number.py`, …                      | Entity platforms: thin `async_setup_entry` calling `devices/` builders      |
| `camera.py`                                      | Webcam stream (MjpegCamera) + printed-object thumbnail                      |
| `update.py`                                      | `UpdateEntity` for system/firmware components                               |
| `services.yaml`, `strings.json`, `translations/` | Service descriptions and UI translations (en, es, fr)                       |

## Runtime data

Each config entry stores a `MoonrakerData` dataclass in `entry.runtime_data`
with `client` (the API wrapper) and `coordinator`. Platforms read the
coordinator through `entry.runtime_data.coordinator` — never `hass.data`.

Static sensors and buttons expose their names through `translation_key`
(`entity` section in `strings.json` / `translations/*.json`); dynamically
discovered printer objects keep generated names.

## Device model

One HA device per config entry, identified by `(DOMAIN, entry.entry_id)`.
The config entry `unique_id` is the Moonraker instance UUID (`server.info.uuid`,
falling back to the hostname) and prefixes every entity `unique_id` as
`{entry.unique_id}_{entity_key}`. Entity ids are stable across restarts; a
migration (`async_migrate_entry`, version 1 → 2) converts legacy
`{entry_id}_...` ids automatically.

## Adding a new device type

1. Create `devices/<type>.py` with a `build_<type>_sensors(coordinator) -> list[<Description>]` (or a name target builder) that queries the printer
   objects and returns descriptions.
2. Reuse the description dataclasses from `devices/base.py`; put any pure
   computation in `helpers.py`.
3. Call the builder from the relevant platform's `async_setup_entry`, then
   `coordinator.load_sensor_data(...)` + `async_refresh()` +
   `async_add_entities(...)`.
4. Add tests in `tests/` (mirror `tests/devices/` or the platform test file).

## Adding a new platform

1. Add the `Platform` to `PLATFORMS` in `const.py`.
2. Create `<platform>.py` with only `async_setup_entry(hass, entry, async_add_entities)` (thin) delegating to `devices/` builders.
3. Add entity classes and translations, then tests.

## Update behaviour

Once every platform has registered its printer objects, the coordinator calls
`printer.objects.subscribe`: Moonraker then pushes each change over the
websocket that is already open (`notify_status_update`), and the coordinator
merges the partial payload into its data. A printer that refuses the
subscription simply stays on polling.

Polling remains enabled as a safety net for anything a dropped notification
would lose. Once subscribed it runs every `SAFETY_NET_INTERVAL` (5 min, or the
configured `options.polling_rate` when that is longer) and no longer switches to
the 2 s printing cadence — Moonraker already pushes those changes. Events the
subscription does not carry (Klippy state, power devices, history, job queue,
update status) arrive as their own notifications and trigger a refresh.

Without a subscription the original behaviour applies: every
`options.polling_rate` seconds (default 30), 2 s while printing.

Each refresh runs the registered updaters in order. `_printer_objects_updater`
stores its status payload on the coordinator so `_gcode_file_detail_updater`
reads it instead of re-querying the whole object set. Slow endpoints (history,
job queue, spoolman, update status, power devices, system info) are registered
with a 60 s TTL, and gcode metadata is cached per filename until a new print
starts — the file itself cannot change while it prints.

## Setup cost

Setup latency on a real printer is dominated by serialized JSON-RPC
round-trips, so the call count is what the integration optimises for:

- platforms pass what they already fetched to `add_data_updater(..., seed=...)`,
  which fills the coordinator data and starts the TTL window instead of letting
  the next refresh repeat the same call;
- endpoints several platforms need (`machine.update.status`,
  `machine.system_info`) go through `coordinator.async_fetch_shared()`, which
  shares the pending task so concurrent platform setups issue one call;
- the discovery caches (`objects_list`, `configfile_settings`) are read by the
  `devices/` builders rather than being re-queried per platform;
- independent discovery calls run concurrently (`sensor.py` setup groups, the
  thermal/fan/mcu builders, the two discovery-cache queries);
- a single refresh runs after all platforms registered their objects — no
  platform triggers its own, and the first refresh skips the printer object
  query while no object is registered yet;
- the subscription happens before that refresh, which reuses its reply instead
  of querying the same objects again;
- concurrent discovery probes are merged into one `printer.objects.query` by
  `coordinator.async_discover_objects()`.

`tests/test_boot_perf.py` enforces the budget (`MAX_SETUP_CALLS`); run it with
`-s` to print the full per-method profile.

Beyond the first start, discovery does not happen during setup at all.
`discovery_cache.py` stores what the printer exposed — its object list, its
Klipper config and the probe of its thermal and fan objects — and setup replays
that snapshot. The real discovery runs afterwards, and the entry is reloaded
only if the printer turned out to have changed. The comparison looks at shape
only: which objects exist, which config sections exist, and whether the fields
discovery asked about report a value. Measurements are ignored, and so is
anything Moonraker returns because of the active subscription rather than
because it was asked for.

## Quality gates

- `scripts/test_strict` — 385 tests, 100 % statement coverage.
- `ruff check` / `ruff format` — clean.
- `mypy --strict custom_components/moonraker/` — clean.
- `hassfest` — clean (config-entry-only `CONFIG_SCHEMA`).

## Release pipeline

Conventional commits on `main` → release-please maintains a release PR (version bump in
`manifest.json` + `const.py` + `CHANGELOG.md`) → merging it publishes the tag and the
GitHub release → HACS picks up the new version.
