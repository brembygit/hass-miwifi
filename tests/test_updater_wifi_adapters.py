"""Visibility of the wifi adapters a node reports.

Only wl0/wl1/wl2/wl14 are mapped to an IfName. Anything else was dropped with no
trace, taking the switch, the channel and the signal of a radio the node has -
which is exactly the shape of "this node shows no 5G switch and the others do".
"""

# pylint: disable=no-member,protected-access

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.miwifi.const import ATTR_WIFI_ADAPTER_LENGTH
from custom_components.miwifi.updater import LuciUpdater

MOCK_IP: str = "192.168.1.102"


def _updater() -> LuciUpdater:
    """Build an updater shell with only the attributes this path touches."""

    updater = LuciUpdater.__new__(LuciUpdater)
    updater.ip = MOCK_IP
    updater.data = {}
    updater.luci = MagicMock()
    updater.supports_guest = False
    updater._wifi_adapters_logged = None

    hass = MagicMock()

    async def _run(func, *args):
        return func(*args)

    hass.async_add_executor_job = _run
    updater.hass = hass

    return updater


def _adapter(ifname: str) -> dict:
    return {"ifname": ifname, "status": "1", "channelInfo": {"channel": 1}}


@pytest.mark.asyncio
async def test_mapped_and_skipped_adapters_are_reported(caplog) -> None:
    """The unknown ifname is named, not swallowed."""

    updater = _updater()
    updater.luci.wifi_detail_all = AsyncMock(
        return_value={"bsd": 1, "info": [_adapter("wl1"), _adapter("wl9")]}
    )
    data: dict = {}

    with caplog.at_level(logging.DEBUG):
        await updater._async_prepare_wifi(data)

    reported = [rec.getMessage() for rec in caplog.records if "wifi adapters" in rec.getMessage()]

    assert len(reported) == 1
    assert "wl1" in reported[0]
    assert "wl9" in reported[0]
    # The unknown radio is still not counted as an adapter.
    assert data[ATTR_WIFI_ADAPTER_LENGTH] == 1


@pytest.mark.asyncio
async def test_the_picture_is_reported_once_while_it_holds(caplog) -> None:
    """Per-cycle repetition would be noise; a change is worth a line."""

    updater = _updater()
    updater.luci.wifi_detail_all = AsyncMock(
        return_value={"bsd": 1, "info": [_adapter("wl1")]}
    )

    with caplog.at_level(logging.DEBUG):
        await updater._async_prepare_wifi({})
        await updater._async_prepare_wifi({})

        updater.luci.wifi_detail_all = AsyncMock(
            return_value={"bsd": 1, "info": [_adapter("wl1"), _adapter("wl0")]}
        )
        await updater._async_prepare_wifi({})

    reported = [rec.getMessage() for rec in caplog.records if "wifi adapters" in rec.getMessage()]

    assert len(reported) == 2
    assert "wl0" in reported[1]
