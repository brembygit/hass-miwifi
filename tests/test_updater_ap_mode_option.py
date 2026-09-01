"""Tests for the access point / mesh node option."""

# pylint: disable=no-member,protected-access

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.miwifi.const import (
    ATTR_BINARY_SENSOR_WAN_STATE,
    ATTR_SENSOR_MODE,
    CONF_IS_AP_MODE,
    DEFAULT_IS_AP_MODE,
)
from custom_components.miwifi.enum import Mode
from custom_components.miwifi.exceptions import LuciConnectionError
from custom_components.miwifi.updater import AP_MODE_SKIP_METHODS, PREPARE_METHODS, LuciUpdater


def _updater(is_ap_mode: bool) -> LuciUpdater:
    """Build an updater shell with only the attributes these paths touch."""

    updater = LuciUpdater.__new__(LuciUpdater)
    updater.is_ap_mode = is_ap_mode
    updater.ip = "192.168.31.104"
    updater.data = {}
    updater._is_cb0401v2 = False
    updater.luci = MagicMock()

    hass = MagicMock()

    async def _run(func, *args):
        return func(*args)

    hass.async_add_executor_job = _run
    updater.hass = hass

    return updater


def test_option_defaults_to_off() -> None:
    """Gateways keep today's behaviour unless the option is turned on."""

    assert CONF_IS_AP_MODE == "is_ap_mode"
    assert DEFAULT_IS_AP_MODE is False


def test_skipped_methods_are_gateway_only() -> None:
    """The skip list names real prepare steps and leaves client data alone."""

    assert set(AP_MODE_SKIP_METHODS) == {"mode", "wan"}
    assert set(AP_MODE_SKIP_METHODS).issubset(set(PREPARE_METHODS))
    for method in ("devices", "device_list", "ap", "status"):
        assert method not in AP_MODE_SKIP_METHODS


@pytest.mark.asyncio
async def test_mode_probe_skipped_in_ap_mode() -> None:
    """The gateway mode probe is not sent, and mode stays at the default."""

    updater = _updater(True)
    updater.luci.mode = AsyncMock()
    data: dict = {}

    await updater._async_prepare_mode(data)

    updater.luci.mode.assert_not_awaited()
    assert data[ATTR_SENSOR_MODE] == Mode.DEFAULT


@pytest.mark.asyncio
async def test_mode_probe_still_runs_for_a_gateway() -> None:
    """With the option off the endpoint is queried exactly as before."""

    updater = _updater(False)
    updater.luci.mode = AsyncMock(return_value={"mode": 0})
    data: dict = {}

    await updater._async_prepare_mode(data)

    updater.luci.mode.assert_awaited_once()
    assert data[ATTR_SENSOR_MODE] == Mode.DEFAULT


@pytest.mark.asyncio
async def test_wan_info_skipped_in_ap_mode() -> None:
    """An access point has no WAN, so the endpoint is never asked."""

    updater = _updater(True)
    updater.luci.wan_info = AsyncMock()
    data: dict = {}

    await updater._async_prepare_wan(data)

    updater.luci.wan_info.assert_not_awaited()
    assert data == {}


@pytest.mark.asyncio
async def test_wan_connection_error_does_not_abort_the_cycle() -> None:
    """LuciError derives from BaseException and used to escape this handler."""

    updater = _updater(False)
    updater.luci.wan_info = AsyncMock(side_effect=LuciConnectionError("Connection error"))
    data: dict = {}

    await updater._async_prepare_wan(data)

    assert data[ATTR_BINARY_SENSOR_WAN_STATE] is False


@pytest.mark.asyncio
async def test_macfilter_skipped_in_ap_mode() -> None:
    """MAC filtering lives on the gateway; the leaf must not poll it."""

    updater = _updater(True)
    updater.luci.wifi_connect_devices = AsyncMock(return_value={"list": []})
    updater.luci.macfilter_info = AsyncMock()
    updater.reset_counter = MagicMock()
    updater._filter_macs = {}
    updater.devices = {}

    await updater._async_prepare_devices({})

    updater.luci.macfilter_info.assert_not_awaited()
