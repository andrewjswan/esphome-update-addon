#! /bin/bash

if ! [ -z $4 ]; then
 ADDON=$4
else
 ADDON=5c53de3b_esphome
fi

if [ "$HOSTNAME" != "${ADDON/'_'/'-'}" ]; then
 SCRIPT=$(basename "$0")
 SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
 SCRIPT_DIR="${SCRIPT_DIR/"/root"/""}"
 echo $SCRIPT_DIR

 COMMANDS="compile upload clean config logs run"

 if ! [[ " $COMMANDS " =~ .*\ $1\ .* && $# -ge 4 ]]; then
  echo
  echo "Usage:"
  for COMMAND in $COMMANDS
  do
   echo "$0 $COMMAND <filename.yaml> esp_name esphome_domain_name"
  done
  echo
  echo "Example:"
  echo "$0 "${COMMANDS%% *}" <filename.yaml> hall_light $ADDON"
  echo
  exit 1
 fi
 if ! [[ -f $2 ]]; then
  echo "File not found $2"
  exit 2
 fi

 docker exec addon_$ADDON $SCRIPT_DIR/$SCRIPT $1 $2 $3 $ADDON $5
else
 export ESPHOME_IS_HA_ADDON=true
 if [[ -d /data/cache ]]; then
     pio_cache_base=/data/cache/platformio
 else
     pio_cache_base=/config/esphome/.esphome/platformio
 fi
 export PLATFORMIO_PLATFORMS_DIR="${pio_cache_base}/platforms"
 export PLATFORMIO_PACKAGES_DIR="${pio_cache_base}/packages"
 export PLATFORMIO_CACHE_DIR="${pio_cache_base}/cache"
 export PLATFORMIO_GLOBALLIB_DIR=/piolibs

 if esphome $1 $2; then
  mkdir -p /config/addons_config/esphome-update
  if ! [ -z $5 ]; then
    # cp -R /data/.build/$3/.pioenvs/$3/firmware.factory.bin /config/addons_config/esphome-update/$3-firmware.factory.bin
    cp -R /data/.build/$3/.pioenvs/$3/firmware.ota.bin /config/addons_config/esphome-update/$3-firmware.ota.bin
  fi
  exit 0
 else
  echo "esphome $1 for $2 failed"
  exit 3
 fi
fi

# For interactive session to esphome
# docker exec -it addon_5c53de3b_esphome bash
