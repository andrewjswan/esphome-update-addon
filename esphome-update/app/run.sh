#!/usr/bin/with-contenv bashio

# ==============================================================================
# Home Assistant ESPHome Update Add-on
# Displays a simple add-on banner on startup
# ==============================================================================

if bashio::supervisor.ping; then
  bashio::log.blue \
    '-----------------------------------------------------------'
  bashio::log.blue " Add-on: $(bashio::addon.name)"
  bashio::log.blue " $(bashio::addon.description)"
  bashio::log.blue \
    '-----------------------------------------------------------'
  bashio::log.blue " Add-on version: $(bashio::addon.version)"
  if bashio::var.true "$(bashio::addon.update_available)"; then
    bashio::log.magenta ' There is an update available for this add-on!'
    bashio::log.magenta \
        " Latest add-on version: $(bashio::addon.version_latest)"
    bashio::log.magenta ' Please consider upgrading as soon as possible.'
  else
    bashio::log.green ' You are running the latest version of this add-on.'
  fi

  bashio::log.blue " System: $(bashio::info.operating_system)" \
    " ($(bashio::info.arch) / $(bashio::info.machine))"
  bashio::log.blue " Home Assistant Core: $(bashio::info.homeassistant)"
  bashio::log.blue " Home Assistant Supervisor: $(bashio::info.supervisor)"

  bashio::log.blue \
    '-----------------------------------------------------------'
  bashio::log.blue \
    ' Please, share the above information when looking for help'
  bashio::log.blue \
    ' or support in, e.g., GitHub, forums or the Discord chat.'
  bashio::log.blue \
    '-----------------------------------------------------------'
fi

# ==============================================================================

CONFIG_PATH=/data/options.json

export ARCH=$(cat /arch)

DOCKER=$(docker version -f json | jq -r .Client.Version)

bashio::log.info 'ESPHome Update Starting...'
bashio::log.info 'Configuration:'
bashio::log.blue "  Architecture: ${ARCH}"
bashio::log.blue "  Docker version: ${DOCKER}"
if bashio::config.has_value 'esphome_domain_name'; then
  export ESPHOME_DOMAIN=$(bashio::config 'esphome_domain_name')
  bashio::log.blue "  ESPHome: ${ESPHOME_DOMAIN}"
else
  bashio::log.blue "  ESPHome: 5c53de3b_esphome"
fi
if bashio::config.has_value 'update_interval'; then
  export UPDATE_INTERVAL=$(bashio::config 'update_interval')
  bashio::log.blue "  Update Interval: ${UPDATE_INTERVAL}min"
else
  bashio::log.blue "  Update Interval: 15min"
fi
if bashio::config.has_value 'http_ota'; then
  export HTTP_OTA=$(bashio::config 'http_ota')
  bashio::log.blue "  Only with HTTP OTA: ${HTTP_OTA}"
else
  bashio::log.blue "  Only with HTTP OTA: False"
fi
if bashio::config.has_value 'log_level'; then
  export LOG_LEVEL=$(bashio::config 'log_level')
fi

bashio::log.blue "  Prepare add-on folder..."
mkdir -p /config/addons_config/esphome-update
mkdir -p /addon_configs/esphome-update/

bashio::log.blue "  Prepare make script..."
cp /app/make.sh /config/addons_config/esphome-update/

bashio::log.info 'ESPHome Update Start'
bashio::log.info

# ==============================================================================

bashio::color.reset
cd /app
python ./esphome-update.py
bashio::color.reset

# ==============================================================================

bashio::log.info
bashio::log.info 'ESPHome Update Stop'
bashio::exit.ok
