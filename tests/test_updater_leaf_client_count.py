"""Per-leaf client count sourced from the main's topology graph.

A wired-backhaul leaf answers misystem/devicelist with an empty list, so its
`devices` sensor sat at whatever the main last pushed - or at zero while the
main's graph reported eight clients on it. The graph's `leafs[].onlines` is the
reliable per-node number and is fetched every cycle anyway.

A count the main pushes in is a weaker claim than one the node made for
itself: the main can only name the clients its own device list carries,
which on a mesh bridged onto the ISP's LAN is a fraction of what the node
serves. It is a floor, and the graph outranks it while it knows about more.
"""

# pylint: disable=no-member,protected-access

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.miwifi.const import ATTR_SENSOR_DEVICES, ATTR_SENSOR_MODE, UPDATER
from custom_components.miwifi.enum import Mode
from custom_components.miwifi.updater import LuciUpdater

LEAF_IP: str = "192.168.1.102"
MAIN_IP: str = "192.168.1.101"


def _updater(ip: str = LEAF_IP, mode: Mode = Mode.MESH_NODE) -> LuciUpdater:
    """Build an updater shell with only the attributes this path touches."""

    updater = LuciUpdater.__new__(LuciUpdater)
    updater.ip = ip
    updater.is_ap_mode = False
    updater.is_force_load = False
    updater.data = {ATTR_SENSOR_MODE: mode}
    updater._counters_reset_this_cycle = False
    updater._counters_pushed_this_cycle = False

    hass = MagicMock()

    async def _run(func, *args):
        return func(*args)

    hass.async_add_executor_job = _run
    updater.hass = hass

    return updater


def _main(**leaf_fields) -> LuciUpdater:
    """A main whose graph lists the leaf with the given fields."""

    main = _updater(ip=MAIN_IP, mode=Mode.DEFAULT)
    main.data["topo_graph"] = {
        "graph": {
            "ip": MAIN_IP,
            "is_main": True,
            "leafs": [{"ip": LEAF_IP, "hardware": "RD28", "mode": 1, **leaf_fields}],
        }
    }

    return main


def _patch_integrations(*updaters: LuciUpdater):
    return patch(
        "custom_components.miwifi.updater.async_get_integrations",
        return_value={up.ip: {UPDATER: up} for up in updaters},
    )


@pytest.mark.asyncio
async def test_the_leaf_takes_the_count_the_main_reports() -> None:
    """The case on the live mesh: graph says 8, the leaf's own sensor said 1."""

    leaf = _updater()
    leaf.data[ATTR_SENSOR_DEVICES] = 1

    with _patch_integrations(leaf, _main(onlines=8)):
        await leaf._async_apply_leaf_client_count()

    assert leaf.data[ATTR_SENSOR_DEVICES] == 8


@pytest.mark.asyncio
async def test_zero_steered_clients_is_a_real_answer() -> None:
    """A leaf nothing is steered to reports 0, not unknown and not stale."""

    leaf = _updater()
    leaf.data[ATTR_SENSOR_DEVICES] = 4

    with _patch_integrations(leaf, _main(onlines=0)):
        await leaf._async_apply_leaf_client_count()

    assert leaf.data[ATTR_SENSOR_DEVICES] == 0


@pytest.mark.asyncio
async def test_counting_our_own_clients_wins() -> None:
    """The reset flag marks a cycle in which we produced real numbers."""

    leaf = _updater()
    leaf.data[ATTR_SENSOR_DEVICES] = 3
    leaf._counters_reset_this_cycle = True

    with _patch_integrations(leaf, _main(onlines=8)):
        await leaf._async_apply_leaf_client_count()

    assert leaf.data[ATTR_SENSOR_DEVICES] == 3


@pytest.mark.asyncio
async def test_a_count_the_main_pushed_in_is_only_a_floor() -> None:
    """One client of seven is what the main could name, not what the node serves."""

    leaf = _updater()
    leaf.data[ATTR_SENSOR_DEVICES] = 1
    leaf._counters_reset_this_cycle = True
    leaf._counters_pushed_this_cycle = True

    with _patch_integrations(leaf, _main(onlines=7)):
        await leaf._async_apply_leaf_client_count()

    assert leaf.data[ATTR_SENSOR_DEVICES] == 7


@pytest.mark.asyncio
async def test_a_pushed_count_the_graph_cannot_beat_stands() -> None:
    """The graph must never talk a real enumeration downwards."""

    leaf = _updater()
    leaf.data[ATTR_SENSOR_DEVICES] = 9
    leaf._counters_reset_this_cycle = True
    leaf._counters_pushed_this_cycle = True

    with _patch_integrations(leaf, _main(onlines=7)):
        await leaf._async_apply_leaf_client_count()

    assert leaf.data[ATTR_SENSOR_DEVICES] == 9


@pytest.mark.asyncio
async def test_the_two_agreeing_is_not_a_change() -> None:
    """The ordinary case, where the main did carry the whole list."""

    leaf = _updater()
    leaf.data[ATTR_SENSOR_DEVICES] = 7
    leaf._counters_reset_this_cycle = True
    leaf._counters_pushed_this_cycle = True

    with _patch_integrations(leaf, _main(onlines=7)):
        await leaf._async_apply_leaf_client_count()

    assert leaf.data[ATTR_SENSOR_DEVICES] == 7


@pytest.mark.asyncio
async def test_a_gateway_never_takes_a_count_from_anyone() -> None:
    """Only a node that sits inside someone else's network qualifies."""

    node = _updater(mode=Mode.DEFAULT)
    node.data[ATTR_SENSOR_DEVICES] = 38

    with _patch_integrations(node, _main(onlines=8)):
        await node._async_apply_leaf_client_count()

    assert node.data[ATTR_SENSOR_DEVICES] == 38


@pytest.mark.asyncio
async def test_a_graph_without_onlines_changes_nothing() -> None:
    """Older firmwares do not carry the field; malformed values are ignored."""

    leaf = _updater()
    leaf.data[ATTR_SENSOR_DEVICES] = 2

    with _patch_integrations(leaf, _main()):
        await leaf._async_apply_leaf_client_count()

    with _patch_integrations(leaf, _main(onlines="")):
        await leaf._async_apply_leaf_client_count()

    assert leaf.data[ATTR_SENSOR_DEVICES] == 2


@pytest.mark.asyncio
async def test_an_unlisted_leaf_changes_nothing() -> None:
    """No entry in anyone's graph means no number to take."""

    leaf = _updater(ip="192.168.1.199")
    leaf.data[ATTR_SENSOR_DEVICES] = 5

    with _patch_integrations(leaf, _main(onlines=8)):
        await leaf._async_apply_leaf_client_count()

    assert leaf.data[ATTR_SENSOR_DEVICES] == 5
