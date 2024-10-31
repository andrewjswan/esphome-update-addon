"""ESPHome Update Server."""

import asyncio
import contextlib
import datetime
import fnmatch
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from threading import Thread

import requests
from bottle import route, run, static_file, template
from esphome.config import dump_dict, read_config
from esphome.core import CORE

ESPHOME_FOLDER = "/config/esphome/"
ESPHOME_UPDATE = "/config/addons_config/esphome-update/"
ESPHOME_UPDATE_STORAGE = "/addon_configs/esphome-update/"

CONFIGS_FILE = ESPHOME_UPDATE + "configs.json"
MAKE_FILE = ESPHOME_UPDATE + "make.sh"
HTML_FILE = ESPHOME_UPDATE + "configs.html"
VERSION_FILE = "./esphome-version.sh"

COMPILE = "compile"

BUILD_OK = 0
BUILD_NEW = -1
BUILD_COPY = -5
BUILD_ERROR = 555

STATUS_NEW = "new"
STATUS_BUILD = "build"
STATUS_COMPLETE = "complete"

PROJECT_LEN = 2

ESPHOME = "esphome"
ESP32 = "ESP32"
ESP8266 = "ESP8266"

addon_config = {
    "esphome_domain": "",
    "esphome_version": "",
    "esphome_hash": "",
    "update_interval": 900,
    "only_http_ota": True,
    "auto_clean": True,
}

esphome_devices = {}

LOGGER = logging.getLogger(__name__)


def move_dir(src: str, dst: str, pattern: str = "*") -> bool:
    """Move files by Mask."""
    try:
        if not Path(dst).is_dir():
            Path(dst).mkdir(parents=True, exist_ok=True)
        for f in fnmatch.filter(os.listdir(src), pattern):
            shutil.move(Path(src) / f, Path(dst) / f)
    except Exception as e:
        LOGGER.exception("Error:", exc_info=e)
        return False
    else:
        return True


def delete_files(src: str, pattern: str = "*") -> bool:
    """Delete files by Mask."""
    try:
        for f in fnmatch.filter(os.listdir(src), pattern):
            (Path(src) / f).unlink()
    except Exception as e:
        LOGGER.exception("Error:", exc_info=e)
        return False
    else:
        return True


def delete_from_storage(name: str) -> None:
    """Delete data from ESPHome Update storage."""
    delete_files(ESPHOME_UPDATE_STORAGE, name + "-manifest.json")
    delete_files(ESPHOME_UPDATE_STORAGE, name + "-firmware.*.bin")


def md5(fname: str) -> str:
    """Calculate MD5 for File."""
    hash_md5 = hashlib.md5()  # noqa: S324
    with Path(fname).open(mode="rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def folder_md5(directory: str) -> str:
    """Calculate MD5 for Folder."""
    md5_hash = hashlib.md5()  # noqa: S324
    if not Path(directory).exists():
        return "-1"

    try:
        for root, _, files in os.walk(ESPHOME_FOLDER):
            for file in sorted(files):
                if file.lower().endswith(".yaml"):
                    LOGGER.debug("Hashing: %s/%s", root, file)
                    with (Path(root) / file).open(mode="rb") as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            md5_hash.update(chunk)

    except Exception as e:
        LOGGER.exception("Error:", exc_info=e)
        return "-2"

    return md5_hash.hexdigest()


def config_md5(config: dict) -> str:
    """Calculate MD5 for Folder."""
    digest = {}
    for path, domain in sorted(config.output_paths):
        digest["path"] = path
        digest["domain"] = domain
        digest["dump"] = sorted(dump_dict(config, path)[0].splitlines())
    return hashlib.md5(repr(digest).encode("utf-8")).hexdigest()  # noqa: S324


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
    # Get ESPHome Add-On Domain Name
    esphome_domain = os.getenv("ESPHOME_DOMAIN")  # ESPhome Add-on Domain Name
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


def esphome_version() -> None:
    """Get ESPHome version."""
    esphome = subprocess.run(  # noqa: S603
        ["docker", "exec", "addon_" + addon_config["esphome_domain"], "esphome", "version"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    if esphome.returncode == 0:
        esphome_version = re.search(
            r"\d{4}\.\d{1,2}\.\d{1,2}",
            esphome.stdout.decode("utf-8"),
        ).group()
        LOGGER.debug("ESPHome: %s Version: %s", addon_config["esphome_domain"], esphome_version)
        addon_config["esphome_version"] = esphome_version
    else:
        addon_config["esphome_version"] = ""


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
    esphome_version()
    if not addon_config["esphome_version"]:
        LOGGER.debug("Look like ESPHome Add-on not started, try start...")
        if not esphome_start():
            LOGGER.debug("ESPHome addon start failed, skip...")
            return
        esphome_version()
        esphome_started = False

    if not addon_config["esphome_version"]:
        LOGGER.debug("ESPHome version - unknown, skip...")
        return

    esphome_folder_md5 = folder_md5(ESPHOME_FOLDER)
    if esphome_folder_md5 == addon_config["esphome_hash"]:
        LOGGER.debug("ESPHome config folder %s not changed, skip...", ESPHOME_FOLDER)
        return
    addon_config["esphome_hash"] = esphome_folder_md5

    for file in sorted(os.listdir(ESPHOME_FOLDER)):
        if file.lower().endswith(".yaml") and not file.lower().endswith("secrets.yaml"):
            LOGGER.debug("ESPHome config file: %s", file)
            file_path = Path(ESPHOME_FOLDER) / file
            need_build = False

            update_reason = "Automatic update " + (
                datetime.datetime.now(tz=datetime.UTC)
            ).astimezone().strftime("%Y-%m-%d %H:%M:%S")

            if file not in esphome_devices:
                file_info = {}
                file_info["status"] = STATUS_NEW
                file_info["name"] = ""
                file_info["comment"] = ""
                file_info["author"] = ""
                file_info["project"] = ""
                file_info["version"] = addon_config["esphome_version"]
                file_info["chip"] = ""
                file_info["file"] = os.fspath(file_path)
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

            try:
                CORE.reset()
                CORE.verbose = False
                CORE.config_path = file_path
                with (
                    contextlib.redirect_stderr(Path(os.devnull).open(mode="w")),
                    contextlib.suppress(Exception),
                ):
                    config = read_config({})
            except Exception as e:
                config = None
                LOGGER.exception("Error:", exc_info=e)

            if config and "esphome" in config:
                conf_md5 = config_md5(config)
                if conf_md5 != esphome_devices[file]["md5"]:
                    need_build = True
                    LOGGER.debug(
                        "Need build: Configuration MD5 changed %s - %s",
                        esphome_devices[file]["md5"],
                        conf_md5,
                    )
                esphome_devices[file]["md5"] = conf_md5

                if "name" in config["esphome"]:
                    esphome_devices[file]["name"] = config["esphome"]["name"]
                if "comment" in config["esphome"]:
                    esphome_devices[file]["comment"] = config["esphome"]["comment"]
                if "project" in config["esphome"]:
                    if "name" in config["esphome"]["project"]:
                        name = config["esphome"]["project"]["name"].split(".")
                        if len(name) == PROJECT_LEN:
                            esphome_devices[file]["author"] = name[0]
                            esphome_devices[file]["project"] = name[1].replace("_", " ")
                    if "version" in config["esphome"]["project"]:
                        version = config["esphome"]["project"]["version"]
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

                if "esp32" in config:
                    esphome_devices[file]["chip"] = ESP32
                    if "variant" in config["esp32"]:
                        esphome_devices[file]["chip"] = config["esp32"]["variant"]
                if "esp8266" in config:
                    esphome_devices[file]["chip"] = ESP8266

                esphome_devices[file]["zzz"] = "deep_sleep" in config

                http_update = (
                    "update" in config
                    and len(
                        [
                            item
                            for item in config["update"]
                            if "platform" in item and item["platform"] == "http_request"
                        ],
                    )
                    > 0
                )
                if http_update != esphome_devices[file]["http_ota"]:
                    need_build = True
                    LOGGER.debug("Need build: Configuration OTA status changed")
                esphome_devices[file]["http_ota"] = http_update
            else:
                esphome_devices[file]["build"] = BUILD_ERROR
                need_build = False

            if need_build and Path(MAKE_FILE).is_file():
                esphome_devices[file]["status"] = STATUS_BUILD
                if not addon_config["only_http_ota"] or (
                    addon_config["only_http_ota"] and esphome_devices[file]["http_ota"]
                ):
                    need_store = "-"
                else:
                    need_store = ""
                build = subprocess.run(  # noqa: S603
                    [
                        MAKE_FILE,
                        COMPILE,
                        file_path,
                        esphome_devices[file]["name"],
                        addon_config["esphome_domain"],
                        need_store,
                    ],
                    capture_output=True,
                    check=False,
                )
                if build.returncode == 0:
                    esphome_devices[file]["esphome"] = addon_config["esphome_version"]
                    LOGGER.debug("Build complete!")
                    if need_store == "":
                        esphome_devices[file]["build"] = BUILD_OK
                    elif move_dir(
                        ESPHOME_UPDATE,
                        ESPHOME_UPDATE_STORAGE,
                        esphome_devices[file]["name"] + "*.bin",
                    ):
                        ota = {}
                        ota["path"] = esphome_devices[file]["name"] + "-firmware.ota.bin"
                        ota["md5"] = md5(ESPHOME_UPDATE_STORAGE + ota["path"])
                        ota["summary"] = update_reason

                        build = {}
                        build["chipFamily"] = esphome_devices[file]["chip"]
                        build["ota"] = ota

                        builds = []
                        builds.append(build)

                        manifest = {}
                        manifest["name"] = esphome_devices[file]["name"]
                        manifest["version"] = esphome_devices[file]["version"]
                        manifest["home_assistant_domain"] = ESPHOME
                        manifest["new_install_prompt_erase"] = False
                        manifest["builds"] = builds

                        json_manifest = json.dumps(manifest, indent=2)
                        with Path(
                            ESPHOME_UPDATE_STORAGE
                            + esphome_devices[file]["name"]
                            + "-manifest.json",
                        ).open(mode="w") as outfile:
                            outfile.write(json_manifest)

                        esphome_devices[file]["build"] = BUILD_OK
                        LOGGER.debug("Store complete.")
                    else:
                        esphome_devices[file]["build"] = BUILD_COPY
                        LOGGER.debug("Store ERROR!")
                else:
                    esphome_devices[file]["build"] = build.returncode
                    LOGGER.debug(build.stderr.decode("utf-8"))

                esphome_devices[file]["status"] = STATUS_COMPLETE

            if (
                addon_config["auto_clean"]
                and addon_config["only_http_ota"]
                and file in esphome_devices
                and not esphome_devices[file]["http_ota"]
            ):
                delete_from_storage(esphome_devices[file]["name"])

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


def work_loop() -> None:
    """Start ESPHome Update main processing cycle."""
    while True:
        work()
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
