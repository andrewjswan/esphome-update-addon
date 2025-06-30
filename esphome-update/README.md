<div align="center">
<h1>ESPHome Update Add-on</h1>
</div>

## General

[![ha addon_badge](https://img.shields.io/badge/HA-Addon-blue.svg)](https://developers.home-assistant.io/docs/add-ons)
[![ESPHome Update](https://img.shields.io/badge/ESPHome-Update-blue.svg)](https://github.com/andrewjswan/esphome-update-addon/)
[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/andrewjswan/esphome-update-addon/build.yml?logo=github)](https://github.com/andrewjswan/esphome-update-addon/actions)
[![GitHub release (latest SemVer including pre-releases)](https://img.shields.io/github/v/release/andrewjswan/esphome-update-addon?include_prereleases)](https://github.com/andrewjswan/esphome-update-addon/blob/master/esphome-update/CHANGELOG.md)
[![GitHub License](https://img.shields.io/github/license/andrewjswan/esphome-update-addon?color=blue)](https://github.com/andrewjswan/esphome-update-addon/blob/master/LICENSE)
[![StandWithUkraine](https://raw.githubusercontent.com/vshymanskyy/StandWithUkraine/main/badges/StandWithUkraine.svg)](https://github.com/vshymanskyy/StandWithUkraine/blob/main/docs/README.md)

**ESPHome Update Server** - monitors your device configurations in the ESPHome folder, and with each change, builds them into a ready-made firmware for [OTA Update via HTTP Request](https://esphome.io/components/update/http_request.html). 

The firmware storage is located in `\addon_configs\esphome-update\`

## Architecture

![Supports amd64 Architecture][amd64-shield] ![Supports aarch64 Architecture][aarch64-shield] ![Supports armv7 Architecture][armv7-shield] ![Supports armhf Architecture][armhf-shield] ![Supports i386 Architecture][i386-shield]

## Confururation settings

- `esphome_domain_name`: Domain name of the ESPHome Add-on, for performing firmware check and assembly.
- `update_interval`: Period for checking ESPHome configurations for updates
- `http_ota`: Store in storage, only firmware with HTTP Request OTA support

### Default confururation
```
  esphome_domain_name: 5c53de3b_esphome  # Optional
  update_interval: 15  # Optional, values from 1 to 60 minutes
  http_ota: true  # Optional
  log_level: DEBUG  # Optional, values: DEBUG|INFO|WARNING|ERROR|CRITICAL
```

<br />

> [!IMPORTANT]
> For the **ESPHome Update** add-on to work, it must be given `full access` (turn off the `protected mode`) option, and the **ESPHome** add-on must be installed and running.

### OTA Update via HTTP Request Sample
```Yaml
substitutions:
  device: esp_with_http_ota
  name: Grill
  project_name: "andrewjswan.ESP_With_HTTP_OTA"
  project_version: "1.0.5"
  comment: "ESP With HTTP OTA Support"

esphome:
  name: $device
  comment: $comment
  project:
    name: $project_name
    version: $project_version

http_request:
  useragent: "esphome/${device} (${project_version})"
  verify_ssl: false
  timeout: 10s

ota:
  - platform: http_request

update:
  - platform: http_request
    name: "${name} Firmware Update"
    source: http://${home_assistant_ip}:5500/firmware/${device}-manifest.json
    icon: mdi:update
    web_server_sorting_weight: 15
```

### Local Web Server index page (only if Update ESPhome Web index page enabled)
```Yaml
web_server:
  js_url: "http://${home_assistant_ip}:5500/web/www.js"
  version: 3
```

```Yaml
web_server:
  js_url: "http://${home_assistant_ip}:5500/web/v2/www.js"
  version: 2
```

> [!TIP]
> ESPHome [configuration](https://github.com/andrewjswan/esphome-config)

[amd64-shield]: https://img.shields.io/badge/amd64-yes-blue.svg
[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-blue.svg
[armv7-shield]: https://img.shields.io/badge/armv7-no-red.svg
[armhf-shield]: https://img.shields.io/badge/armhf-no-red.svg
[i386-shield]: https://img.shields.io/badge/i386-no-red.svg
