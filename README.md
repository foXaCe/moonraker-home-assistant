[![GitHub Release][releases-shield]][releases]
[![License][license-shield]][license]
[![hacs][hacsbadge]][hacs]
[![CI][ci-shield]][ci]
[![codecov](https://codecov.io/github/foXaCe/moonraker-home-assistant/branch/main/graph/badge.svg)](https://app.codecov.io/github/foXaCe/moonraker-home-assistant)
![install_badge](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.moonraker.total)

# Moonraker Home Assistant

Non official integration for Moonraker and Klipper in Home Assistant (via HACS).

> [!NOTE]
> This is a maintained fork of [marcolivierarsenault/moonraker-home-assistant](https://github.com/marcolivierarsenault/moonraker-home-assistant), whose upstream is no longer maintained.

# Supported Entities

This allows you home assistant to connect to your 3D printer and display:

- Key informations about the printer (sensors)
- Show the camera image (if installed)
- Thumbnail of what is being printed at the moment.
- Emergency stop button
- Button to trigger macros

To access the list of all entities and their documentations, look at our [documentation](https://moonraker-home-assistant.readthedocs.io/en/latest/).

## Hardware Limits

This software seems to have issues working on **FLSUN Speeder Pad** and **Sonic Pad**, so those are unsuported.

# Install

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=foXaCe&repository=moonraker-home-assistant&category=integration)

## Install via HACS

- The installation is done inside [HACS](https://hacs.xyz/) (Home Assistant Community Store). If you don't have HACS, you must install it before adding this integration. [Installation instructions here.](https://hacs.xyz/docs/use/#getting-started-with-hacs)
- Once HACS is installed, add this repository as a custom repository: HACS → three-dots menu → `Custom repositories` → repository `foXaCe/moonraker-home-assistant`, type `Integration` (or click the badge above).
- Search for `Moonraker` in HACS, select "Download". Once fully downloaded, restart HomeAssistant.
- In the sidebar, click 'Configuration', then 'Devices & Services'. Click the + icon to add "Moonraker" to your Home Assistant installation.
  - Enter the host or IP of your Moonraker installation.
  - Change your printer's port if you don't use the default of 7125.
  - Optionally enter your API key if you have required one in Moonraker.
  - Optionally specify your printer's name if you don't want to use the hostname of your moonraker installation.

# Support

You have issue with the integration, you want new sensors? Please open an [Issue](https://github.com/foXaCe/moonraker-home-assistant/issues).

# Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

# Screenshot

![sensor](https://raw.githubusercontent.com/foXaCe/moonraker-home-assistant/main/assets/sensors.png)
![button](https://raw.githubusercontent.com/foXaCe/moonraker-home-assistant/main/assets/button.png)
![camera](https://raw.githubusercontent.com/foXaCe/moonraker-home-assistant/main/assets/camera.png)
![thumbnial](https://raw.githubusercontent.com/foXaCe/moonraker-home-assistant/main/assets/thumbnail.png)

# Special thanks

This integration is built on other people's work, and it is worth naming them:

- [Marc-Olivier Arsenault](https://github.com/marcolivierarsenault), who created this integration and maintained it for years. This fork exists only because that work existed first.
- [cashew22](https://github.com/cashew22), by far the largest contributor after the author.
- [Clifford Roche](https://github.com/cmroche), who built [moonraker-api](https://github.com/cmroche/moonraker-api) — the library this integration talks to your printer through.
- [Arksine](https://github.com/Arksine) for [Moonraker](https://github.com/Arksine/moonraker) and [Kevin O'Connor](https://github.com/KevinOConnor) for [Klipper](https://github.com/Klipper3d/klipper). None of this exists without them.
- Every [contributor](https://github.com/marcolivierarsenault/moonraker-home-assistant/graphs/contributors) who sent a fix, a new sensor or a translation over the years.
- Everyone who opened an issue, tested a pre-release, or reported a bug on a printer nobody else could reproduce it on. Those reports are what makes an integration work on hardware its maintainers will never own. 🚀

# Author

Maintained by [foXaCe](https://github.com/foXaCe).

<!-- Badges links -->

[releases-shield]: https://img.shields.io/github/v/release/foXaCe/moonraker-home-assistant.svg?style=for-the-badge
[releases]: https://github.com/foXaCe/moonraker-home-assistant/releases
[license-shield]: https://img.shields.io/github/license/foXaCe/moonraker-home-assistant.svg?style=for-the-badge
[license]: https://github.com/foXaCe/moonraker-home-assistant/blob/main/LICENSE
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[ci-shield]: https://img.shields.io/github/actions/workflow/status/foXaCe/moonraker-home-assistant/ci.yml?branch=main&style=for-the-badge
[ci]: https://github.com/foXaCe/moonraker-home-assistant/actions/workflows/ci.yml
