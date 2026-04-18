"""ESPHome Update Server."""

import asyncio
import datetime
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Thread

import requests
import yaml
from bottle import route, run, static_file, template

ESPHOME_FOLDER = "/config/esphome/"
ESPHOME_UPDATE = "/config/addons_config/esphome-update/"
ESPHOME_UPDATE_STORAGE = "/addon_configs/esphome-update/"

PIO_CACHE_BASE = "/data/cache/platformio"

CONFIGS_FILE = ESPHOME_UPDATE + "configs.json"

ESPHOME_JS_URL = "https://oi.esphome.io/v{version}/www.js"
WEB_JS_FILE = ESPHOME_UPDATE + "www/v{version}/www.js"
WEB_JS_URL = "{path}/www/v{version}/"

BUILD_OK = 0
BUILD_NEW = -1
BUILD_COPY = -5
BUILD_ERROR = 555

STATUS_NEW = "new"
STATUS_BUILD = "build"
STATUS_COMPLETE = "complete"

PROJECT_LEN = 2
WEB_UPDATE_HOURS = 12

ESPHOME = "esphome"
ESP32 = "ESP32"
ESP8266 = "ESP8266"
RP2040 = "RP2040"

addon_config = {
    "esphome_domain": "",
    "esphome_version": "",
    "esphome_hash": "",
    "update_interval": 900,
    "only_http_ota": True,
    "auto_clean": True,
    "web_update": False,
}

esphome_devices = {}

env_vars = {
    "ESPHOME_IS_HA_ADDON": "true",
    "PLATFORMIO_GLOBALLIB_DIR": "/piolibs",
    "PLATFORMIO_PLATFORMS_DIR": PIO_CACHE_BASE + "/platforms",
    "PLATFORMIO_PACKAGES_DIR": PIO_CACHE_BASE + "/packages",
    "PLATFORMIO_CACHE_DIR": PIO_CACHE_BASE + "/cache",
}


webupdate = datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(weeks=1)

LOGGER = logging.getLogger(__name__)


@dataclass
class Config:
    """Configuration data."""

    name: str
    platform: str
    original_name: str
    friendly_name: str | None = None

    project_name: str | None = None
    project_version: str | None = None

    raw_config: dict | None = None

    def dest_manifest(self, file_base: Path) -> Path:
        """Get the destination manifest path."""
        return file_base / f"{self.original_name}-manifest.json"

    def dest_factory_bin(self, file_base: Path) -> Path:
        """Get the destination factory binary path."""
        if self.platform == RP2040:
            return file_base / f"{self.original_name}.uf2"
        return file_base / f"{self.original_name}.factory.bin"

    def dest_ota_bin(self, file_base: Path) -> Path:
        """Get the destination OTA binary path."""
        return file_base / f"{self.original_name}.ota.bin"

    def dest_elf(self, file_base: Path) -> Path:
        """Get the destination ELF path."""
        return file_base / f"{self.original_name}.elf"

    def source_factory_bin(self, elf: Path) -> Path:
        """Get the source factory binary path."""
        if self.platform == RP2040:
            return elf.with_name("firmware.uf2")
        return elf.with_name("firmware.factory.bin")

    def source_ota_bin(self, elf: Path) -> Path:
        """Get the source OTA binary path."""
        return elf.with_name("firmware.ota.bin")


def move_files(src: str, dst: str, pattern: str = "*") -> bool:
    """Move files by Mask."""
    src_path = Path(src)
    dst_path = Path(dst)
    try:
        if not dst_path.is_dir():
            dst_path.mkdir(parents=True, exist_ok=True)
        for file_path in src_path.glob(pattern):
            shutil.move(file_path, dst_path / file_path.name)

    except Exception as e:
        LOGGER.exception("Error:", exc_info=e)
        return False
    else:
        return True


def delete_files(src: str, pattern: str = "*") -> bool:
    """Delete files by Mask."""
    try:
        for file_path in Path(src).glob(pattern):
            if file_path.is_file():
                file_path.unlink()
    except Exception as e:
        LOGGER.exception("Error:", exc_info=e)
        return False
    else:
        return True


def delete_from_storage(name: str) -> None:
    """Delete data from ESPHome Update storage."""
    delete_files(ESPHOME_UPDATE_STORAGE, name + "-manifest.json")
    delete_files(ESPHOME_UPDATE_STORAGE, name + ".*.bin")


def folder_md5(directory: str) -> tuple[str | None, int]:
    """Calculate MD5 for Folder."""
    path_obj = Path(directory)
    if not path_obj.exists():
        return None, -1

    md5_hash = hashlib.md5()  # noqa: S324
    try:
        for root, dirs, files in os.walk(directory, topdown=True):
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            for file in sorted(files):
                if file.lower().endswith(".yaml"):
                    if file.startswith("."):
                        continue

                    file_path = Path(root) / file
                    stat = file_path.stat()
                    LOGGER.debug("Hashing: %s/%s", root, file)

                    meta = f"{file}:{stat.st_size}:{stat.st_mtime}"
                    md5_hash.update(meta.encode())

    except Exception as e:
        LOGGER.exception("Error during hashing:", exc_info=e)
        return None, -2

    return md5_hash.hexdigest(), 0


def config_md5(config: Config) -> str:
    """Calculate MD5 for Configuration."""
    config_string = json.dumps(config.raw_config, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(config_string.encode("utf-8")).hexdigest()  # noqa: S324


def logger_init() -> None:
    """Init Logger and set settings."""
    # Logger settings
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s")
    LOGGER.setLevel(logging.DEBUG)
    # Set logger level
    log_level = os.getenv("LOG_LEVEL")  # Log level for Logger
    if log_level:
        level = logging.getLevelName(log_level)
        LOGGER.setLevel(level)


def load_config() -> None:
    """Load ESPHome Update settings."""
    # Get ESPHome App Domain Name
    esphome_domain = os.getenv("ESPHOME_DOMAIN")  # ESPhome App Domain Name
    if not esphome_domain:
        esphome_domain = "5c53de3b_esphome"
    addon_config["esphome_domain"] = esphome_domain

    # Get Update interval
    update_interval = os.getenv("UPDATE_INTERVAL")
    if update_interval:
        addon_config["update_interval"] = int(update_interval) * 60

    # Get Only HTTP OTA
    http_ota = os.getenv("HTTP_OTA")
    if http_ota:
        addon_config["only_http_ota"] = http_ota.lower() == "true"

    # Get Web Update
    web_update = os.getenv("WEB_UPDATE")
    if web_update:
        addon_config["web_update"] = web_update.lower() == "true"


def esphome_start() -> bool:
    """Start ESPHome addon."""
    access_token = os.getenv("SUPERVISOR_TOKEN")
    url = "http://supervisor/addons/" + addon_config["esphome_domain"] + "/start"
    try:
        result = requests.post(url, headers={"Authorization": "Bearer " + access_token}, timeout=30)
        details = result.json()
        return details["result"] == "ok"
    except Exception as e:
        LOGGER.debug("Response: %s", result)
        LOGGER.exception("Error:", exc_info=e)
    return False


def esphome_stop() -> bool:
    """Stop ESPHome addon."""
    access_token = os.getenv("SUPERVISOR_TOKEN")
    url = "http://supervisor/addons/" + addon_config["esphome_domain"] + "/stop"
    try:
        result = requests.post(url, headers={"Authorization": "Bearer " + access_token}, timeout=30)
        details = result.json()
        return details["result"] == "ok"
    except Exception as e:
        LOGGER.debug("Response: %s", result)
        LOGGER.exception("Error:", exc_info=e)
    return False


def esphome_version() -> tuple[str, int]:
    """Get the ESPHome version."""
    command = ["docker", "exec"]
    for key, value in env_vars.items():
        command.extend(["-e", f"{key}={value}"])
    command.extend(["addon_" + addon_config["esphome_domain"], "esphome", "version"])

    try:
        version = subprocess.check_output(command)  # noqa: S603
    except subprocess.CalledProcessError as e:
        return "", e.returncode

    version = version.decode("utf-8").strip()
    version = version.split(" ")[1].strip()
    LOGGER.debug("ESPHome: %s Version: %s", addon_config["esphome_domain"], version)
    return version, 0


def esphome_idedata(filename: Path) -> tuple[dict | None, int]:
    """Get the IDEData."""
    command = ["docker", "exec"]
    for key, value in env_vars.items():
        command.extend(["-e", f"{key}={value}"])
    command.extend(["addon_" + addon_config["esphome_domain"], "esphome", "idedata", filename])

    try:
        idedata = subprocess.check_output(command, stderr=sys.stderr)  # noqa: S603
    except subprocess.CalledProcessError as e:
        return None, e.returncode

    data = json.loads(idedata.decode("utf-8"))
    return data, 0


def esphome_config(filename: Path) -> tuple[Config | None, int]:
    """Get the configuration."""
    command = ["docker", "exec"]
    for key, value in env_vars.items():
        command.extend(["-e", f"{key}={value}"])
    command.extend(["addon_" + addon_config["esphome_domain"], "esphome", "config", filename])
    try:
        config = subprocess.check_output(command, stderr=sys.stderr)  # noqa: S603
    except subprocess.CalledProcessError as e:
        return None, e.returncode

    config = config.decode("utf-8")
    yaml.add_multi_constructor("", lambda _, t, n: t + " " + n.value)
    try:
        config = yaml.load(config, Loader=yaml.FullLoader)  # noqa: S506
    except Exception as e:
        LOGGER.exception("Error reading Configuration:", exc_info=e)
        return None, -1

    original_name = config["esphome"]["name"]
    friendly_name = config["esphome"].get("friendly_name", "")

    platform = ""
    if "esp32" in config:
        platform = config["esp32"]["variant"].upper()
    elif "esp8266" in config:
        platform = ESP8266
    elif "rp2040" in config:
        platform = RP2040
    if not platform:
        return None, -1

    name = f"{original_name}-{platform}".lower()

    if project_config := config["esphome"].get("project"):
        project_name = project_config["name"]
        project_version = project_config["version"]
    else:
        project_name = None
        project_version = None

    return Config(
        name=name,
        platform=platform,
        original_name=original_name,
        raw_config=config,
        friendly_name=friendly_name,
        project_name=project_name,
        project_version=project_version,
    ), 0


def esphome_build(filename: Path) -> int:
    """Build ESPHome Firmware."""
    command = ["docker", "exec"]
    for key, value in env_vars.items():
        command.extend(["-e", f"{key}={value}"])
    command.extend(["addon_" + addon_config["esphome_domain"], "esphome", "compile", filename])

    build = subprocess.run(command, capture_output=True, check=False)  # noqa: S603

    LOGGER.debug(build.stderr.decode("utf-8"))
    return build.returncode


def esphome_store_firmware(config: Config, idedata: dict, dst_path: Path) -> int:
    """Store ESPHome Firmware to Storage."""
    if not dst_path.is_dir():
        dst_path.mkdir(parents=True, exist_ok=True)

    elf = Path(idedata["prog_path"])
    source_factory_bin = config.source_factory_bin(elf)
    source_ota_bin = config.source_ota_bin(elf)
    dest_factory_bin = config.dest_factory_bin(dst_path)
    dest_ota_bin = config.dest_ota_bin(dst_path)

    command = ["docker", "exec"]
    for key, value in env_vars.items():
        command.extend(["-e", f"{key}={value}"])
    command.extend(["addon_" + addon_config["esphome_domain"]])

    copy_commands = (
        f"cp -R {source_ota_bin} {dest_ota_bin} && cp -R {source_factory_bin} {dest_factory_bin}"
    )
    command.extend(["sh", "-c", copy_commands])

    store = subprocess.run(command, capture_output=True, check=False)  # noqa: S603
    LOGGER.debug(store.stderr.decode("utf-8"))
    return store.returncode


def generate_manifest_part(
    config: Config,
    release_summary: str | None,
    release_url: str | None,
) -> tuple[dict | None, int]:
    """Generate the manifest."""
    chip_family = None
    has_factory_part = False
    if ESP32 in config.platform:
        if config.platform != ESP32:
            chip_family = config.platform.replace("ESP32", "ESP32-")
        else:
            chip_family = config.platform
        has_factory_part = True
    elif config.platform == ESP8266:
        chip_family = config.platform
        has_factory_part = True
    elif config.platform == RP2040:
        chip_family = RP2040
    else:
        return None, -1

    factory_bin = config.dest_factory_bin(Path(ESPHOME_UPDATE_STORAGE))
    ota_bin = config.dest_ota_bin(Path(ESPHOME_UPDATE_STORAGE))

    with ota_bin.open("rb") as f:
        ota_md5 = hashlib.md5(f.read()).hexdigest()  # noqa: S324
        f.seek(0)
        ota_sha256 = hashlib.sha256(f.read()).hexdigest()

    manifest = {
        "chipFamily": chip_family,
        "ota": {
            "path": ota_bin.name,
            "md5": ota_md5,
            "sha256": ota_sha256,
        },
    }

    if release_summary:
        manifest["ota"]["summary"] = release_summary
    if release_url:
        manifest["ota"]["release_url"] = release_url

    if has_factory_part:
        with factory_bin.open("rb") as f:
            factory_md5 = hashlib.md5(f.read()).hexdigest()  # noqa: S324
            f.seek(0)
            factory_sha256 = hashlib.sha256(f.read()).hexdigest()
        manifest["parts"] = [
            {
                "path": str(factory_bin.name),
                "offset": 0x00,
                "md5": factory_md5,
                "sha256": factory_sha256,
            },
        ]

    return manifest, 0


def generate_manifest(
    config: Config,
    release_summary: str | None,
    release_url: str | None,
) -> int:
    """Generate the manifest."""
    manifest, rc = generate_manifest_part(
        config,
        release_summary,
        release_url,
    )
    if rc != 0:
        return rc

    manifest = {
        "name": config.project_name or config.friendly_name or config.original_name,
        "version": config.project_version or esphome_version,
        "home_assistant_domain": "esphome",
        "new_install_prompt_erase": False,
        "builds": [
            manifest,
        ],
    }

    manifest_file = config.dest_manifest(Path(ESPHOME_UPDATE_STORAGE))
    with manifest_file.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return 0


def load_devices() -> None:
    """Load ESP configuration list."""
    global esphome_devices  # noqa: PLW0603

    if Path(CONFIGS_FILE).exists():
        with Path(CONFIGS_FILE).open(mode="r") as file:
            esphome_devices = json.load(file)


def save_devices() -> None:
    """Save ESP configuration list."""
    global esphome_devices  # noqa: PLW0602

    json_object = json.dumps(esphome_devices, indent=2)
    with Path(CONFIGS_FILE).open(mode="w") as outfile:
        outfile.write(json_object)


def work() -> None:  # noqa: C901 PLR0912 PLR0915
    """ESPHome Update Main work function."""
    global esphome_devices  # noqa: PLW0602

    esphome_started = True
    version, rc = esphome_version()
    addon_config["esphome_version"] = ""
    if rc == 0:
        addon_config["esphome_version"] = version
    if not addon_config["esphome_version"]:
        LOGGER.debug("Look like ESPHome Builder App not started, try start...")
        if not esphome_start():
            LOGGER.warning("ESPHome Builder App start failed, skip...")
            return
        version, rc = esphome_version()
        if rc == 0:
            addon_config["esphome_version"] = version
        esphome_started = False

    if not addon_config["esphome_version"]:
        LOGGER.warning("ESPHome version - unknown, skip...")
        return

    esphome_folder_md5, rc = folder_md5(ESPHOME_FOLDER)
    if rc == 0:
        if esphome_folder_md5 == addon_config["esphome_hash"]:
            LOGGER.debug("ESPHome config folder %s not changed, skip...", ESPHOME_FOLDER)
            return
        addon_config["esphome_hash"] = esphome_folder_md5
    else:
        LOGGER.error("Could not calculate hash, error code: %s", rc)
        return

    esphome_path = Path(ESPHOME_FOLDER)
    for file_path in sorted(esphome_path.glob("*.yaml"), key=lambda x: x.name):
        file = file_path.name
        if file.lower() == "secrets.yaml":
            continue

        LOGGER.info("-------------------------------------------------------")
        LOGGER.info("ESPHome config file: %s", file)
        need_build = False

        update_reason = "Automatic update " + (
            datetime.datetime.now(tz=datetime.UTC)
        ).astimezone().strftime("%Y-%m-%d %H:%M:%S")

        if file not in esphome_devices:
            file_info = {}
            file_info["status"] = STATUS_NEW
            file_info["name"] = ""
            file_info["friendly_name"] = ""
            file_info["comment"] = ""
            file_info["author"] = ""
            file_info["project"] = ""
            file_info["version"] = addon_config["esphome_version"]
            file_info["chip"] = ""
            file_info["file"] = os.fspath(file_path)
            file_info["build_path"] = "-"
            file_info["time"] = ""
            file_info["md5"] = ""
            file_info["zzz"] = False
            file_info["http_ota"] = False
            file_info["esphome"] = addon_config["esphome_version"]
            file_info["build"] = BUILD_NEW

            esphome_devices[file] = file_info
            update_reason = "New build " + (
                datetime.datetime.now(tz=datetime.UTC)
            ).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            need_build = True
            LOGGER.debug("Need build: Found new device configuration")

        if esphome_devices[file]["build"] != BUILD_OK:
            need_build = True
            if esphome_devices[file]["build"] != BUILD_NEW:
                LOGGER.debug("Need build: Previous build status: Failure")

        mod_time = (
            (datetime.datetime.fromtimestamp(Path(file_path).stat().st_mtime, tz=datetime.UTC))
            .astimezone()
            .strftime("%Y%m%d%H%M%S")
        )
        if esphome_devices[file]["time"] != mod_time:
            need_build = True
            esphome_devices[file]["time"] = mod_time
            LOGGER.debug("Need build: Configuration time changed")

        config, rc = esphome_config(file_path)
        if rc != 0:
            config = None
            LOGGER.error("Error %d when reading %s", rc, file_path)

        if config and "esphome" in config.raw_config:
            conf_md5 = config_md5(config)
            if conf_md5 != esphome_devices[file]["md5"]:
                need_build = True
                LOGGER.debug(
                    "Need build: Configuration MD5 changed %s - %s",
                    esphome_devices[file]["md5"],
                    conf_md5,
                )
            esphome_devices[file]["md5"] = conf_md5

            esphome_devices[file]["name"] = config.original_name
            esphome_devices[file]["friendly_name"] = config.friendly_name
            if "comment" in config.raw_config["esphome"]:
                esphome_devices[file]["comment"] = config.raw_config["esphome"]["comment"]
            if "build_path" in config.raw_config["esphome"]:
                esphome_devices[file]["build_path"] = config.raw_config["esphome"]["build_path"]
            if "project" in config.raw_config["esphome"]:
                if "name" in config.raw_config["esphome"]["project"]:
                    name = config.raw_config["esphome"]["project"]["name"].split(".")
                    if len(name) == PROJECT_LEN:
                        esphome_devices[file]["author"] = name[0].replace("_", " ")
                        esphome_devices[file]["project"] = name[1].replace("_", " ")
                if "version" in config.raw_config["esphome"]["project"]:
                    version = config.raw_config["esphome"]["project"]["version"]
                    if (
                        esphome_devices[file]["version"] != version
                        and esphome_devices[file]["build"] != BUILD_NEW
                    ):
                        update_reason = (
                            "Version bump from "
                            + esphome_devices[file]["version"]
                            + " to "
                            + version
                        )
                        need_build = True
                        LOGGER.debug(
                            "Need build: Configuration version changed: %s - %s",
                            esphome_devices[file]["version"],
                            version,
                        )
                    esphome_devices[file]["version"] = version
                else:
                    esphome_devices[file]["version"] = addon_config["esphome_version"]

            esphome_devices[file]["chip"] = config.platform
            esphome_devices[file]["zzz"] = "deep_sleep" in config.raw_config

            http_update = (
                "update" in config.raw_config
                and len(
                    [
                        item
                        for item in config.raw_config["update"]
                        if "platform" in item and item["platform"] == "http_request"
                    ],
                )
                > 0
            )
            if http_update != esphome_devices[file]["http_ota"]:
                need_build = True
                LOGGER.debug("Need build: Configuration OTA status changed")
            esphome_devices[file]["http_ota"] = http_update

            if not addon_config["only_http_ota"] or (
                addon_config["only_http_ota"] and esphome_devices[file]["http_ota"]
            ):
                need_store = True
                if not config.dest_ota_bin(Path(ESPHOME_UPDATE_STORAGE)).exists():
                    need_build = True
            else:
                need_store = False
        else:
            esphome_devices[file]["build"] = BUILD_ERROR
            need_build = False

        if need_build:
            esphome_devices[file]["status"] = STATUS_BUILD
            build = esphome_build(file_path)
            if build == 0:
                esphome_devices[file]["esphome"] = addon_config["esphome_version"]
                LOGGER.debug("Build complete!")

                if need_store:
                    idedata, rc = esphome_idedata(file_path)
                    if rc == 0:
                        if esphome_store_firmware(
                            config,
                            idedata,
                            Path(ESPHOME_UPDATE),
                        ) == 0 and move_files(
                            ESPHOME_UPDATE,
                            ESPHOME_UPDATE_STORAGE,
                            esphome_devices[file]["name"] + "*.bin",
                        ):
                            rc = generate_manifest(config, update_reason, None)
                            if rc == 0:
                                esphome_devices[file]["build"] = BUILD_OK
                                LOGGER.debug("Store complete.")
                            else:
                                esphome_devices[file]["build"] = rc
                                LOGGER.warning("Manifest ERROR!")
                        else:
                            esphome_devices[file]["build"] = BUILD_COPY
                            LOGGER.warning("Store ERROR!")
                    else:
                        esphome_devices[file]["build"] = rc
                        LOGGER.warning("IDE Store ERROR!")
                else:
                    esphome_devices[file]["build"] = BUILD_OK
            else:
                esphome_devices[file]["build"] = build
            esphome_devices[file]["status"] = STATUS_COMPLETE

        if (
            addon_config["auto_clean"]
            and addon_config["only_http_ota"]
            and file in esphome_devices
            and not esphome_devices[file]["http_ota"]
        ):
            delete_from_storage(esphome_devices[file]["name"])

        LOGGER.info("")

    LOGGER.debug("Cleanup configuration list...")
    for file in list(esphome_devices):
        file_path = Path(ESPHOME_FOLDER) / file
        if not Path(file_path).exists():
            LOGGER.debug("Delete not existing config [%s] from configuration list", file)
            delete_from_storage(esphome_devices[file]["name"])
            del esphome_devices[file]

    LOGGER.debug("Save configuration list...")
    save_devices()

    if not esphome_started:
        LOGGER.debug("Stop ESPHome addon...")
        esphome_stop()

    LOGGER.debug("Work done.")


def web_update() -> None:
    """ESPHome Update Update WEB server index page."""
    global webupdate  # noqa: PLW0603
    if not addon_config["web_update"]:
        return

    now = datetime.datetime.now(tz=datetime.UTC)
    if divmod((now - webupdate).total_seconds(), 3600)[0] > WEB_UPDATE_HOURS:
        webupdate = now
        for v in range(2, 4):
            try:
                LOGGER.debug("Update ESPHome WEB server index page...")
                if not Path(Path(WEB_JS_FILE.format(version=v)).parent).is_dir():
                    Path(Path(WEB_JS_FILE.format(version=v)).parent).mkdir(
                        parents=True,
                        exist_ok=True,
                    )
                with Path(WEB_JS_FILE.format(version=v)).open(mode="wb") as outfile:
                    content = requests.get(
                        ESPHOME_JS_URL.format(version=v),
                        stream=True,
                        timeout=10,
                    ).content
                    outfile.write(content)
                LOGGER.debug("ESPHome WEB server index page updated.")
            except Exception as e:
                LOGGER.exception("Error:", exc_info=e)


def get_data() -> dict:
    """Get data for index page."""
    global esphome_devices  # noqa: PLW0602
    return dict(sorted(esphome_devices.items()))


@route("/")
def index() -> object:
    """Show index page."""
    data = get_data()
    return template("index.tpl", configs=data, time=time.time())


@route("/ping")
def ping() -> object:
    """Show Ping echo."""
    return {"status": "online", "servertime": time.time()}


@route(r"/<filename:re:.*\.css>")
def stylesheets(filename: str) -> object:
    """Get static CSS."""
    return static_file(filename, root="static/")


@route("/firmware/<filename:path>")
def firmware_download(filename: str) -> object:
    """Download file from ESPHome Update storage."""
    return static_file(filename, root=ESPHOME_UPDATE_STORAGE, download=filename)


@route("/config/<filename:path>")
def config_download(filename: str) -> object:
    """Download file from ESPHome config folder."""
    return static_file(filename, root=ESPHOME_FOLDER, download=filename)


@route("/web/www.js")
def web_default() -> object:
    """Web server index page."""
    return static_file("www.js", root=WEB_JS_URL.format(path=ESPHOME_UPDATE, version=3))


@route("/web/v<version:int>/www.js")
def web_version(version: int) -> object:
    """Web server index page."""
    return static_file("www.js", root=WEB_JS_URL.format(path=ESPHOME_UPDATE, version=version))


def work_loop() -> None:
    """Start ESPHome Update main processing cycle."""
    while True:
        work()
        web_update()
        time.sleep(addon_config["update_interval"])


async def main() -> None:
    """Start the main processing cycle."""
    logger_init()
    load_config()
    load_devices()

    LOGGER.info("ESPHome Update: started...")

    p = Thread(target=work_loop)
    p.start()

    run(host="0.0.0.0", port=5500)  # noqa: S104

    LOGGER.info("ESPHome Update: stopped.")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
