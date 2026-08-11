# Architecture

High-level overview of the Moonraker Home Assistant integration (`custom_components/moonraker/`).

## Data flow

```
Klipper printer
   └── Moonraker server (HTTP/WebSocket API, port 7125)
        └── moonraker-api (external client library, cmroche/moonraker-api)
             └── MoonrakerDataUpdateCoordinator (__init__.py)
                  └── Entity platforms (sensor, binary_sensor, button, camera,
                      switch, number, light)
```

## Key modules

| Module                             | Role                                                                   |
| ---------------------------------- | ---------------------------------------------------------------------- |
| `__init__.py`                      | Config entry setup, `DataUpdateCoordinator`, connection lifecycle      |
| `config_flow.py`                   | UI configuration flow (host, port, API key, printer name)              |
| `const.py`                         | Domain constants, platform list, `VERSION` (managed by release-please) |
| `sensor.py`, `binary_sensor.py`, … | Entity platforms fed by the coordinator                                |
| `camera.py`                        | Webcam stream + printed-object thumbnail                               |
| `translations/`                    | UI translations (en, es, fr, …)                                        |

## Release pipeline

Conventional commits on `main` → release-please maintains a release PR (version bump in
`manifest.json` + `const.py` + `CHANGELOG.md`) → merging it publishes the tag and the
GitHub release → HACS picks up the new version.
