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

| Module                                           | Role                                                                   |
| ------------------------------------------------ | ---------------------------------------------------------------------- |
| `__init__.py`                                    | Config entry setup/unload, `async_migrate_entry`, `send_gcode` service |
| `coordinator.py`                                 | `DataUpdateCoordinator` (typed), dynamic polling, data fetch/send      |
| `config_flow.py`                                 | Config flow + options flow: selectors, reauth, reconfigure, zeroconf   |
| `repairs.py`                                     | Repair flow + issue for invalid API key                                |
| `diagnostics.py`                                 | `async_get_config_entry_diagnostics` (API key redacted)                |
| `const.py`                                       | Domain constants, platforms, API methods, config keys (`Final`)        |
| `helpers.py`                                     | Pure functions (print progress/ETA, gcode path, ports)                 |
| `api/`                                           | `client.py` (wrapper + retry/backoff), `exceptions.py` (typed errors)  |
| `devices/`                                       | Per-device description builders (thermal, fan, mcu, pin, led, macro)   |
| `entity.py`                                      | `BaseMoonrakerEntity` (DeviceInfo, coordinator wiring)                 |
| `sensor.py`, `number.py`, …                      | Entity platforms: thin `async_setup_entry` calling `devices/` builders |
| `camera.py`                                      | Webcam stream (MjpegCamera) + printed-object thumbnail                 |
| `update.py`                                      | `UpdateEntity` for system/firmware components                          |
| `services.yaml`, `strings.json`, `translations/` | Service descriptions and UI translations (en, es, fr)                  |

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

## Polling behaviour

The coordinator polls every `options.polling_rate` seconds (default 30).
While printing (`print_stats.state == "printing"`) it switches to a 2 s
interval and back to the configured interval when printing ends.

## Quality gates

- `scripts/test_strict` — 293 tests, 100 % statement coverage.
- `ruff check` / `ruff format` — clean.
- `mypy --strict custom_components/moonraker/` — clean.
- `hassfest` — clean (config-entry-only `CONFIG_SCHEMA`).

## Release pipeline

Conventional commits on `main` → release-please maintains a release PR (version bump in
`manifest.json` + `const.py` + `CHANGELOG.md`) → merging it publishes the tag and the
GitHub release → HACS picks up the new version.
