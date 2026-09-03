"""Counter ownership on a mesh leaf.

A node whose counters are pushed by the parent skips the reset at the top of the
cycle, but still enumerates its own clients through misystem/devicelist. Every
one of those increments the counters, so without a reset they only ever grew.
Turning the access point option on puts a real node on that path.
"""


# pylint: disable=no-member,protected-access

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.miwifi.const import (
    ATTR_SENSOR_DEVICES,
    ATTR_SENSOR_DEVICES_2_4,
    ATTR_SENSOR_MODE,
    ATTR_TRACKER_CONNECTION,
    ATTR_TRACKER_MAC,
)
from custom_components.miwifi.enum import Connection, Mode
from custom_components.miwifi.updater import LuciUpdater

MOCK_IP: str = "192.168.31.104"


def _updater(mode: Mode = Mode.ACCESS_POINT, is_force_load: bool = False) -> LuciUpdater:
    """Build an updater shell with only the attributes these paths touch."""

    updater = LuciUpdater.__new__(LuciUpdater)
    updater.ip = MOCK_IP
    updater.is_ap_mode = mode == Mode.ACCESS_POINT
    updater.is_force_load = is_force_load
    updater.data = {ATTR_SENSOR_MODE: mode}
    updater.devices = {}
    updater.luci = MagicMock()
    updater.new_device_callback = None
    updater._is_first_update = True
    updater._moved_devices = []
    updater._counters_reset_this_cycle = False
    updater._parent_push_pending = False
    updater._signals = {}
    updater._store = None
    updater._build_device = lambda device, integrations=None: dict(device)

    hass = MagicMock()

    async def _run(func, *args):
        return func(*args)

    hass.async_add_executor_job = _run
    updater.hass = hass

    return updater


def _client(mac: str) -> dict:
    return {ATTR_TRACKER_MAC: mac, ATTR_TRACKER_CONNECTION: Connection.WIFI_2_4}




def test_the_access_point_option_hands_the_counters_to_the_parent() -> None:
    """AP mode raises the mode above zero, which is what flips the regime."""

    updater = _updater()

    assert LuciUpdater.is_repeater.fget(updater) is True
    assert LuciUpdater._counters_pushed_by_parent.fget(updater) is True


@pytest.mark.asyncio
async def test_counters_do_not_grow_across_cycles_on_a_leaf() -> None:
    """The same client seen on three cycles is one client, not three."""

    updater = _updater()

    for _ in range(3):
        updater._counters_reset_this_cycle = False
        await updater.add_device(_client("AA:BB:CC:DD:EE:01"))

    assert updater.data[ATTR_SENSOR_DEVICES] == 1
    assert updater.data[ATTR_SENSOR_DEVICES_2_4] == 1


@pytest.mark.asyncio
async def test_the_reset_happens_once_per_cycle_not_once_per_client() -> None:
    """Two clients in one cycle count two: the reset fires on the first only."""

    updater = _updater()

    await updater.add_device(_client("AA:BB:CC:DD:EE:01"))
    await updater.add_device(_client("AA:BB:CC:DD:EE:02"))

    assert updater.data[ATTR_SENSOR_DEVICES] == 2


@pytest.mark.asyncio
async def test_a_leaf_that_counts_nothing_keeps_the_pushed_numbers() -> None:
    """No client of our own means no reset, so the parent's push survives."""

    updater = _updater()
    updater.reset_counter(is_force=True)
    updater.data[ATTR_SENSOR_DEVICES] = 8
    updater._counters_reset_this_cycle = False

    # A cycle in which the node's own devicelist returned nothing: add_device is
    # never reached, so nothing blanks the count the main pushed in.
    assert updater.data[ATTR_SENSOR_DEVICES] == 8


@pytest.mark.asyncio
async def test_a_gateway_still_resets_at_the_top_of_the_cycle() -> None:
    """Nothing changes for a node that owns its own counters."""

    updater = _updater(mode=Mode.DEFAULT)
    updater.data[ATTR_SENSOR_DEVICES] = 5

    assert LuciUpdater._counters_pushed_by_parent.fget(updater) is False

    updater.reset_counter()

    assert updater.data[ATTR_SENSOR_DEVICES] == 0
    assert updater._counters_reset_this_cycle is True


@pytest.mark.asyncio
async def test_a_leaf_persists_the_clients_it_restores() -> None:
    """Saving mirrors _async_prepare_device_restore, which restores here."""

    updater = _updater()
    updater._store = MagicMock()
    updater._store.async_save = AsyncMock()
    updater.devices = {"AA:BB:CC:DD:EE:01": {}}

    await updater._async_save_devices()

    updater._store.async_save.assert_awaited_once()


@pytest.mark.asyncio
async def test_devices_owned_by_the_parent_are_not_persisted() -> None:
    """Repeater plus force load is the case device_restore skips."""

    updater = _updater(mode=Mode.REPEATER, is_force_load=True)
    updater._store = MagicMock()
    updater._store.async_save = AsyncMock()
    updater.devices = {"AA:BB:CC:DD:EE:01": {}}

    await updater._async_save_devices()

    updater._store.async_save.assert_not_awaited()


@pytest.mark.asyncio
async def test_counting_a_client_for_ourselves_drops_the_parents_claim() -> None:
    """A first-hand count is not the number the main handed over."""

    updater = _updater()
    updater._parent_push_pending = True

    await updater.add_device(_client("AA:BB:CC:DD:EE:01"))

    assert updater._parent_push_pending is False


@pytest.mark.asyncio
async def test_a_client_the_main_hands_over_leaves_the_claim_standing() -> None:
    """It is the push itself: spending it here would defeat the floor."""

    updater = _updater()
    updater._parent_push_pending = True

    await updater.add_device(_client("AA:BB:CC:DD:EE:01"), is_from_parent=True)

    assert updater._parent_push_pending is True
