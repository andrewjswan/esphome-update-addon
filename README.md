<div align="center">
<h1>ESPHome Update Add-on</h1>
</div>

## General

[![ha addon_badge](https://img.shields.io/badge/HA-Addon-blue.svg)](https://developers.home-assistant.io/docs/add-ons)
[![ESPHome Update](https://img.shields.io/static/v1?label=ESPHome&message=Update&color=blue&logo=esphome)](https://github.com/andrewjswan/esphome-update-addon/)
[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/andrewjswan/esphome-update-addon/build.yml?logo=github)](https://github.com/andrewjswan/esphome-update-addon/actions)
[![GitHub release (latest SemVer including pre-releases)](https://img.shields.io/github/v/release/andrewjswan/esphome-update-addon?include_prereleases)](https://github.com/andrewjswan/esphome-update-addon/blob/master/esphome-update/CHANGELOG.md)
[![GitHub License](https://img.shields.io/github/license/andrewjswan/esphome-update-addon?color=blue)](https://github.com/andrewjswan/esphome-update-addon/blob/master/LICENSE)
[![StandWithUkraine](https://raw.githubusercontent.com/vshymanskyy/StandWithUkraine/main/badges/StandWithUkraine.svg)](https://github.com/vshymanskyy/StandWithUkraine/blob/main/docs/README.md)

**ESPHome Update Server** - monitors your device configurations in the ESPHome folder, and with each change, builds them into a ready-made firmware for [OTA Update via HTTP Request](https://esphome.io/components/update/http_request.html). 

The firmware storage is located in `\addon_configs\esphome-update\`

## Architecture

![Supports amd64 Architecture][amd64-shield] ![Supports aarch64 Architecture][aarch64-shield] ![Supports armv7 Architecture][armv7-shield] ![Supports armhf Architecture][armhf-shield] ![Supports i386 Architecture][i386-shield]


## Installation

Add the repository URL under **Supervisor → Add-on Store** in your Home Assistant front-end:

    https://github.com/andrewjswan/esphome-update-addon/

<br />

> [!IMPORTANT]
> For the **ESPHome Update** add-on to work, it must be given `full access` (turn off the `protected mode`) option, and the **ESPHome** add-on must be installed and running.

<br />

> [!TIP]
> ESPHome [configuration](https://github.com/andrewjswan/esphome-config)

[amd64-shield]: https://img.shields.io/badge/amd64-yes-blue.svg
[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-blue.svg
[armv7-shield]: https://img.shields.io/badge/armv7-no-red.svg
[armhf-shield]: https://img.shields.io/badge/armhf-no-red.svg
[i386-shield]: https://img.shields.io/badge/i386-no-red.svg
