"""Handle MiWiFi Frontend panel."""

import os
import json
from datetime import timedelta

import aiohttp

from homeassistant.core import HomeAssistant, callback
from homeassistant.components.frontend import async_register_built_in_panel, async_remove_panel
from homeassistant.components.frontend import DATA_PANELS, Panel
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    PANEL_REPO_VERSION_URL,
    PANEL_REPO_FILES_URL,
    PANEL_REPO_BASE_URL,
    PANEL_LOCAL_PATH,
    PANEL_STORAGE_FILE,
    DEFAULT_PANEL_VERSION,
    MAIN_ROUTER_STORE_FILE,
    PANEL_MONITOR_INTERVAL,
    PANEL_MONITOR_UNSUB,
)
from .logger import _LOGGER


async def async_download_panel_if_needed(hass: HomeAssistant) -> str:
    """Check and download panel if needed. Return the version."""
    if hass.data.get("_miwifi_panel_updating"):
        return await read_local_version(hass)

    hass.data["_miwifi_panel_updating"] = True
    async with aiohttp.ClientSession() as session:
        try:
            remote_version = await read_remote_version(session)
            local_version = await read_local_version(hass)

            if remote_version != local_version:
                await hass.async_add_executor_job(_LOGGER.info, f"[MiWiFi] New panel version detected: {remote_version}, updating files...")
                await download_panel_files(hass, session, remote_version)
                await save_local_version(hass, remote_version)
            else:
                await hass.async_add_executor_job(_LOGGER.info, f"[MiWiFi] Version {remote_version} detected, checking files...")
                await download_panel_files(hass, session, remote_version)

            return remote_version
        except Exception as e:
            await hass.async_add_executor_job(_LOGGER.error, f"[MiWiFi] Error checking/downloading frontend panel: {e}")
            return "0.0"
        finally:
            hass.data["_miwifi_panel_updating"] = False


async def read_remote_version(session: aiohttp.ClientSession) -> str:
    async with session.get(PANEL_REPO_VERSION_URL) as resp:
        resp.raise_for_status()
        text = await resp.text()
        data = json.loads(text)
        return data.get("version", "0.0")


PANEL_VERSION_STATE: str = "miwifi_panel_version_state"
PANEL_VERSION_CACHE_TTL: timedelta = timedelta(minutes=15)
PANEL_VERSION_BACKOFF_START: timedelta = timedelta(minutes=5)
PANEL_VERSION_BACKOFF_MAX: timedelta = timedelta(hours=6)


def describe_error(err: BaseException) -> str:
    """Describe an error in a way that is never empty.

    aiohttp errors stringify to "" more often than not, which is how the panel
    version warning ended up with nothing after the colon.
    """

    status = getattr(err, "status", None)
    if status is not None:
        return f"HTTP {status} ({type(err).__name__})"

    return repr(err)


async def async_read_remote_version(
    hass: HomeAssistant, session: aiohttp.ClientSession
) -> str | None:
    """Read the published panel version, cached and backed off on failure.

    Every updater cycle of every entry asks for this version, so a rate limited
    or unreachable repository used to produce a burst of warnings. Serve a
    cached answer, back off after a failure, and report each failure window once
    with a reason that actually says what happened.

    :return str | None: the version, or None while it could not be read.
    """

    state: dict = hass.data.setdefault(PANEL_VERSION_STATE, {})
    now = dt_util.utcnow()

    valid_until = state.get("valid_until")
    if state.get("version") and valid_until and now < valid_until:
        return state["version"]

    retry_after = state.get("retry_after")
    if retry_after and now < retry_after:
        return state.get("version")

    try:
        version = await read_remote_version(session)
    except Exception as err:  # noqa: BLE001 - reported, never re-raised
        backoff = state.get("backoff") or PANEL_VERSION_BACKOFF_START
        if state.get("backoff"):
            backoff = min(backoff * 2, PANEL_VERSION_BACKOFF_MAX)

        state["backoff"] = backoff
        state["retry_after"] = now + backoff

        if not state.get("failure_logged"):
            state["failure_logged"] = True
            await hass.async_add_executor_job(
                _LOGGER.warning,
                "[MiWiFi] The frontend panel version could not be read: %s. Retrying in %s",
                describe_error(err),
                backoff,
            )

        return state.get("version")

    state.update(
        {
            "version": version,
            "valid_until": now + PANEL_VERSION_CACHE_TTL,
            "backoff": None,
            "retry_after": None,
            "failure_logged": False,
        }
    )

    return version


async def read_remote_files(session: aiohttp.ClientSession) -> list:
    async with session.get(PANEL_REPO_FILES_URL) as resp:
        resp.raise_for_status()
        text = await resp.text()
        data = json.loads(text)
        return data.get("files", [])


def _read_json_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_file(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _read_binary_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _write_binary_file(path: str, content: bytes) -> None:
    with open(path, "wb") as f:
        f.write(content)


async def save_local_version(hass: HomeAssistant, version: str) -> None:
    path = hass.config.path(PANEL_STORAGE_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    await hass.async_add_executor_job(_write_json_file, path, {"version": version})
    hass.data.pop("miwifi_cached_panel_version", None)



async def read_local_version(hass: HomeAssistant) -> str:

    if "miwifi_cached_panel_version" in hass.data:
        return hass.data["miwifi_cached_panel_version"]

    path = hass.config.path(PANEL_STORAGE_FILE)
    if not os.path.exists(path):
        await hass.async_add_executor_job(_LOGGER.info, "[MiWiFi] First installation detected, fetching latest frontend panel version...")
        os.makedirs(os.path.dirname(path), exist_ok=True)

        async with aiohttp.ClientSession() as session:
            try:
                latest_version = await read_remote_version(session)
                await download_panel_files(hass, session, latest_version)
                await hass.async_add_executor_job(_write_json_file, path, {"version": latest_version})
                await hass.async_add_executor_job(_LOGGER.info, f"[MiWiFi] Downloaded and saved latest panel version {latest_version}")
                hass.data["miwifi_cached_panel_version"] = latest_version
                return latest_version
            except Exception as e:
                await hass.async_add_executor_job(_LOGGER.error, f"[MiWiFi] Error downloading panel on first installation: {e}")
                hass.data["miwifi_cached_panel_version"] = DEFAULT_PANEL_VERSION
                return DEFAULT_PANEL_VERSION

    data = await hass.async_add_executor_job(_read_json_file, path)
    version = data.get("version", DEFAULT_PANEL_VERSION)
    hass.data["miwifi_cached_panel_version"] = version
    await hass.async_add_executor_job(_LOGGER.debug, f"[MiWiFi] Loaded local panel version: {version}")
    return version



async def download_panel_files(hass: HomeAssistant, session: aiohttp.ClientSession, remote_version: str) -> None:
    try:
        files = await read_remote_files(session)
    except Exception as e:
        await hass.async_add_executor_job(_LOGGER.error, f"[MiWiFi] Error reading files.json: {e}")
        return

    for file in files:
        remote_url = f"{PANEL_REPO_BASE_URL}{file}"
        local_path = hass.config.path(PANEL_LOCAL_PATH, file)

        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        async with session.get(remote_url) as resp:
            if resp.status != 200:
                await hass.async_add_executor_job(_LOGGER.warning, f"[MiWiFi] Could not download {file} (status {resp.status})")
                continue

            remote_content = await resp.read()

            if file.endswith(".js"):
                content = remote_content.decode("utf-8").replace("__MIWIFI_VERSION__", remote_version)
                remote_content = content.encode("utf-8")

            if os.path.exists(local_path):
                existing_content = await hass.async_add_executor_job(_read_binary_file, local_path)
                if remote_content == existing_content:
                    continue

            await hass.async_add_executor_job(_write_binary_file, local_path, remote_content)
            await hass.async_add_executor_job(_LOGGER.debug, f"[MiWiFi] File updated: {file}")



async def async_register_panel(hass: HomeAssistant, version: str) -> None:
    """Register the MiWiFi panel in Home Assistant, only if needed."""
    panel_data = hass.data.get(DATA_PANELS, {}).get("miwifi")
    expected_url = f"/local/miwifi/panel-frontend.js?v={version}"

    if isinstance(panel_data, Panel):
        config = getattr(panel_data, "config", {})
        current_url = config.get("_panel_custom", {}).get("module_url", "")
        if current_url == expected_url:
            await hass.async_add_executor_job(
                _LOGGER.debug,
                "[MiWiFi] Panel already registered with current version, skipping."
            )
            return

    # Remove old panel if exists
    if "miwifi" in hass.data.get(DATA_PANELS, {}):
        try:
            await async_remove_panel(hass, "miwifi")
            hass.data[DATA_PANELS].pop("miwifi", None)
            await hass.async_add_executor_job(
                _LOGGER.debug,
                "[MiWiFi] Existing panel 'miwifi' removed before re-registering."
            )
        except Exception as e:
            await hass.async_add_executor_job(
                _LOGGER.warning,
                f"[MiWiFi] Failed to remove existing panel before re-registering: {e}"
            )

    # Register new panel
    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="MiWiFi",
        sidebar_icon="mdi:router-network",
        frontend_url_path="miwifi",
        config={
            "_panel_custom": {
                "name": "miwifi-panel",
                "module_url": expected_url,
                "embed_iframe": False,
                "trust_external_script": False,
            }
        },
        require_admin=True,
    )
    await hass.async_add_executor_job(
        _LOGGER.info,
        f"[MiWiFi] Panel successfully registered with version: {version}"
    )


async def async_remove_miwifi_panel(hass: HomeAssistant) -> None:
    """Remove the MiWiFi panel if it exists."""
    panels = hass.data.get(DATA_PANELS)

    if not panels or "miwifi" not in panels:
        await hass.async_add_executor_job(
            _LOGGER.debug,
            "[MiWiFi] Panel 'miwifi' not registered — skipping removal."
        )
        return

    try:
        await async_remove_panel(hass, "miwifi")
        hass.data[DATA_PANELS].pop("miwifi", None)
        await hass.async_add_executor_job(
            _LOGGER.info,
            "[MiWiFi] Panel successfully removed."
        )
    except Exception as e:
        await hass.async_add_executor_job(
            _LOGGER.warning,
            f"[MiWiFi] Error deleting panel: {e}"
        )

        

async def async_start_panel_monitor(hass) -> None:
    """Start periodic panel version monitoring, at most one per instance.

    Every entry setup and every options save used to start another one and
    throw the unsubscribe away, so the timers piled up and outlived the
    entries that started them.
    """

    if hass.data.get(PANEL_MONITOR_UNSUB) is not None:
        return

    async def _check_panel_version(now):
        try:
            local = await read_local_version(hass)
            async with aiohttp.ClientSession() as session:
                remote = await async_read_remote_version(hass, session)

            if remote is None:
                return

            if local != remote:
                await hass.async_add_executor_job(_LOGGER.warning, f"[MiWiFi] New panel version available: {remote} (local: {local})")
            else:
                last_logged = hass.data.get("miwifi_last_checked_version")
                if last_logged != local:
                    await hass.async_add_executor_job(_LOGGER.debug, f"[MiWiFi] Panel up-to-date: {local}")
                    hass.data["miwifi_last_checked_version"] = local

        except Exception as e:
            await hass.async_add_executor_job(
                _LOGGER.warning, "[MiWiFi] Panel monitor error: %s", describe_error(e)
            )

    hass.data[PANEL_MONITOR_UNSUB] = async_track_time_interval(
        hass, _check_panel_version, PANEL_MONITOR_INTERVAL
    )


@callback
def async_stop_panel_monitor(hass) -> None:
    """Cancel the monitor, if this instance has one running."""

    unsub = hass.data.pop(PANEL_MONITOR_UNSUB, None)
    if unsub is not None:
        unsub()



# ------- Persistence for Main Router Manual -------

async def async_save_manual_main_mac(hass: HomeAssistant, mac: str):
    """Save manually selected MAC to a JSON file."""
    path = hass.config.path(MAIN_ROUTER_STORE_FILE)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        await hass.async_add_executor_job(_write_json_file, path, {"manual_main_mac": mac})
        await hass.async_add_executor_job(_LOGGER.info, "[MiWiFi] ✅ MAC Manual saved correctly in %s", path)
        
        from .updater import async_get_integrations
        integrations = async_get_integrations(hass)
        for integ in integrations.values():
            try:
                await integ["updater"].coordinator.async_request_refresh()
            except Exception:
                pass

    except Exception as e:
        await hass.async_add_executor_job(_LOGGER.error, "[MiWiFi] ❌ Error saving file from manual MAC: %s", e)


async def async_load_manual_main_mac(hass: HomeAssistant) -> str | None:
    """Load manually selected MAC from file."""
    path = hass.config.path(MAIN_ROUTER_STORE_FILE)
    if not os.path.exists(path):
        await hass.async_add_executor_job(_LOGGER.debug, "[MiWiFi] No manual MAC file found at %s", path)
        return None
    try:
        data = await hass.async_add_executor_job(_read_json_file, path)
        if isinstance(data, dict):
            mac = data.get("manual_main_mac")
            await hass.async_add_executor_job(_LOGGER.debug, "[MiWiFi] ✅ MAC loaded from file: %s", mac)
            return mac
        else:
            await hass.async_add_executor_job(_LOGGER.warning, "[MiWiFi] ❌ Unexpected format in file: %s (expected: dict, received: %s)", path, type(data).__name__)
            return None
    except Exception as e:
        await hass.async_add_executor_job(_LOGGER.error, "[MiWiFi] ❌ Error reading manual MAC: %s", e)
        return None


async def async_clear_manual_main_mac(hass: HomeAssistant):
    """Remove stored MAC file."""
    path = hass.config.path(MAIN_ROUTER_STORE_FILE)
    try:
        if os.path.exists(path):
            await hass.async_add_executor_job(os.remove, path)
            await hass.async_add_executor_job(_LOGGER.info, "[MiWiFi] 🗑️Manual MAC file deleted: %s", path)
    except Exception as e:
        await hass.async_add_executor_job(_LOGGER.error, "[MiWiFi] ❌ Error deleting file from MAC manually: %s", e)

