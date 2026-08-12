# Changelog

## [1.15.0](https://github.com/foXaCe/moonraker-home-assistant/compare/moonraker-home-assistant-1.14.0...moonraker-home-assistant-1.15.0) (2026-08-12)


### Features

* offline-tolerant setup, french entity names, camera icons ([#16](https://github.com/foXaCe/moonraker-home-assistant/issues/16)) ([4cc7c55](https://github.com/foXaCe/moonraker-home-assistant/commit/4cc7c5579bbb394e0e25aa75b3e78302bec4f0d1))
* push updates, faster setup, and correctness fixes ([#17](https://github.com/foXaCe/moonraker-home-assistant/issues/17)) ([a782bca](https://github.com/foXaCe/moonraker-home-assistant/commit/a782bca71b706244fb7de09902923e90dd06e9e1))
* translate remaining static entities and add missing icons ([#14](https://github.com/foXaCe/moonraker-home-assistant/issues/14)) ([4777a9a](https://github.com/foXaCe/moonraker-home-assistant/commit/4777a9a8206e76889f40f5a1d0d9b88bc3407072))

## [1.14.0](https://github.com/foXaCe/moonraker-home-assistant/releases) (2026-08-11)

### Features

- add speed factor sensor ([62f3775](https://github.com/foXaCe/moonraker-home-assistant/commit/62f3775cb783a027c8bfb00f4db009dfcdaec2b7))

## Changelog

All notable changes to this project are documented in this file.

Releases are managed by [release-please](https://github.com/googleapis/release-please) based on [Conventional Commits](https://www.conventionalcommits.org/); entries below are generated automatically.

For the history prior to 1.13.4, see the [GitHub releases](https://github.com/foXaCe/moonraker-home-assistant/releases) of the original upstream project.

## Unreleased (overhaul)

### Added

- `update` platform with `UpdateEntity` for system and firmware components (`machine.update.status`).
- Config flow reauthentication (`async_step_reauth`) and discovery via zeroconf (`_moonraker._tcp`).
- `strings.json` as the translation source of truth; complete `translations/fr.json` (vouvoiement).
- `diagnostics`-ready module layout: `api/` (client, typed exceptions), `devices/` (per-device builders), `helpers.py` (pure functions).
- Modern selectors in config flow and options flow.

### Changed

- Refactored the integration into a modular structure: `coordinator.py`, `api/`, `devices/`, `helpers.py`; platform files are now thin setup wrappers.
- `DataUpdateCoordinator` is typed and the polling interval is configured per entry (no more global `SCAN_INTERVAL`).
- Config entry runtime data moved to `entry.runtime_data`; the `send_gcode` service is unregistered on unload.
- Entity unique ids migrate from `{entry_id}_{key}` to `{entry.unique_id}_{key}` (entry version 1 → 2, automatic migration).
- `PERCENTAGE` replaced by `UnitOfRatio.PERCENTAGE` (deprecated unit constant).
- API client hardened: retry with exponential backoff, best-effort reconnect, typed `ApiAuthError`/`ApiConnectionError`, explicit timeouts.
- `moonraker` no longer crashes when a printer reports partial data (defensive value handling).
- Diagnostic entities carry `EntityCategory.DIAGNOSTIC`; update sensors are disabled by default.
- `CONFIG_SCHEMA` declared as config-entry-only; `min_ha_version` removed from the manifest (hassfest compliant).

### Fixed

- Spoolman sensor no longer crashes the sensor platform when `server.spoolman.status` returns no `spool_id`.
- `output_pin`, `led`, and PWM pins tolerate printers missing configfile entries.
- Service `send_gcode` no longer leaks across entry unloads.
- Logging uses lazy `%s` formatting; camera connection messages no longer use f-string logs.

### Quality

- 281 tests, 100% statement coverage (`scripts/test_strict` green).
- `ruff check` / `ruff format` clean.
- `mypy --strict` clean (0 errors).
- `hassfest` validation: 0 errors.
