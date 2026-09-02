"""A leaf's clients must reach the leaf's entry, whichever MAC the main names it by.

A mesh node answers to two MACs: the one its own `misystem/status` reports, which
the config entry is keyed on, and the one the main writes into every client's
`parent`. `_async_prepare_device_list` only ever knew the first, so the test that
routes a client to its leaf never fired and every client stayed attributed to the
main - one flat list under the main's entry, and nothing under the leaves.

The pairing is in the same response that needs it: mesh nodes are listed flagged
`isap`, carrying the parent-side MAC next to their LAN address. The payloads here
have the shape a four node mesh really answers with, with the addresses replaced.
"""

# pylint: disable=no-member,protected-access

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.miwifi.const import (
    ATTR_DEVICE_MAC_ADDRESS,
    ATTR_TRACKER_ENTRY_ID,
    UPDATER,
)
from custom_components.miwifi.updater import LuciUpdater, _ap_macs_by_ip

# The two MACs a mesh node answers to: A_ is what its own status reports and the
# config entry is keyed on, B_ is what the main writes into a client's `parent`.
MAIN_ENTRY_MAC: str = "00:00:00:00:00:A1"
LEAF_ENTRY_MAC: str = "00:00:00:00:00:A2"
LEAF_PARENT_MAC: str = "00:00:00:00:00:B2"
NODE_3_PARENT_MAC: str = "00:00:00:00:00:B3"
NODE_4_PARENT_MAC: str = "00:00:00:00:00:B4"

MAIN_IP: str = "192.168.1.101"
LEAF_IP: str = "192.168.1.102"

# The client the leaf really serves, which used to be listed under the main.
PARENTED_CLIENT: str = "00:00:00:00:00:16"


def _node(mac: str, ip: str) -> dict:
    """A mesh node as the main lists it: flagged `isap`, parented to nothing."""

    return {
        "mac": mac,
        "isap": 8,
        "parent": "",
        "online": 1,
        "ip": [{"ip": ip, "active": 1}],
    }


def _client(mac: str, ip: str, parent: str = "") -> dict:
    """A client as the main lists it."""

    return {
        "mac": mac,
        "isap": 0,
        "parent": parent,
        "online": 1,
        "authority": {"wan": 1},
        "ip": [{"ip": ip, "active": 1}],
    }


# The main's own list, in the order it answers with: three mesh nodes carrying
# the MAC their clients are parented to, five clients the main is named on, and
# one client parented to the MAC the main knows 192.168.1.102 by.
MAIN_DEVICE_LIST: dict = {
    # Not the router's MAC: misystem/devicelist answers with the MAC of whoever
    # asked. Every node on a mesh returns the same one here, the caller's.
    "mac": "00:00:00:00:00:15",
    "code": 0,
    "list": [
        _node(LEAF_PARENT_MAC, LEAF_IP),
        _client("00:00:00:00:00:11", "192.168.1.254"),
        _node(NODE_3_PARENT_MAC, "192.168.1.103"),
        _client("00:00:00:00:00:12", "192.168.1.112"),
        _client("00:00:00:00:00:13", "192.168.1.113"),
        _client("00:00:00:00:00:14", "192.168.1.114"),
        _client("00:00:00:00:00:15", "192.168.1.115"),
        _client(PARENTED_CLIENT, "192.168.1.116", parent=LEAF_PARENT_MAC),
        _node(NODE_4_PARENT_MAC, "192.168.1.104"),
    ],
}

# What every leaf on such a mesh answers: it enumerates nothing for itself.
LEAF_DEVICE_LIST: dict = {"mac": "00:00:00:00:00:15", "list": [], "code": 0}

# The clients the main is named on - everything above bar the parented one.
MAIN_OWN_CLIENTS: list = [
    "00:00:00:00:00:11",
    "00:00:00:00:00:12",
    "00:00:00:00:00:13",
    "00:00:00:00:00:14",
    "00:00:00:00:00:15",
]


def test_the_nodes_the_main_lists_become_an_alias_table() -> None:
    """The pairing the routing needs, taken from the response itself."""

    assert _ap_macs_by_ip(MAIN_DEVICE_LIST) == {
        LEAF_IP: LEAF_PARENT_MAC,
        "192.168.1.103": NODE_3_PARENT_MAC,
        "192.168.1.104": NODE_4_PARENT_MAC,
    }


def test_a_client_is_never_mistaken_for_a_node() -> None:
    """`isap` is the whole test: a client's address must not alias anything."""

    macs = _ap_macs_by_ip(MAIN_DEVICE_LIST)

    assert "192.168.1.116" not in macs, "a client became a router"
    assert "192.168.1.254" not in macs, "the ISP gateway became a router"


def test_a_node_that_lists_nothing_contributes_nothing() -> None:
    """A leaf answers with an empty list; that has to stay a no-op."""

    assert _ap_macs_by_ip(LEAF_DEVICE_LIST) == {}


def test_a_stale_address_beats_no_address() -> None:
    """A wired leaf can sit idle long enough for its entry to go inactive."""

    response = {
        "list": [
            {
                "mac": NODE_3_PARENT_MAC,
                "isap": 8,
                "ip": [{"ip": "192.168.1.103", "active": 0}],
            }
        ]
    }

    assert _ap_macs_by_ip(response) == {"192.168.1.103": NODE_3_PARENT_MAC}


def test_the_active_address_is_the_one_that_counts() -> None:
    """An old lease listed first must not shadow the address in use."""

    response = {
        "list": [
            {
                "mac": NODE_3_PARENT_MAC,
                "isap": 8,
                "ip": [
                    {"ip": "192.168.1.199", "active": 0},
                    {"ip": "192.168.1.103", "active": 1},
                ],
            }
        ]
    }

    assert _ap_macs_by_ip(response) == {"192.168.1.103": NODE_3_PARENT_MAC}


@pytest.mark.parametrize(
    "entry",
    (
        "not a dict",
        {"isap": 8},
        {"mac": "", "isap": 8, "ip": [{"ip": "192.168.1.103"}]},
        {"mac": NODE_3_PARENT_MAC, "isap": "nonsense", "ip": []},
        {"mac": NODE_3_PARENT_MAC, "isap": 8, "ip": "192.168.1.103"},
        {"mac": NODE_3_PARENT_MAC, "isap": 8, "ip": []},
        {"mac": NODE_3_PARENT_MAC, "isap": 8, "ip": [{"ip": ""}]},
    ),
)
def test_a_malformed_entry_is_skipped_not_raised(entry) -> None:
    """This runs inside the poll loop; raising there costs the whole cycle."""

    assert _ap_macs_by_ip({"list": [entry]}) == {}


def _updater(ip: str, entry_id: str, mac: str, response: dict) -> LuciUpdater:
    """Build an updater shell with only what this path touches."""

    updater = LuciUpdater.__new__(LuciUpdater)
    updater.ip = ip
    updater._entry_id = entry_id
    updater.data = {ATTR_DEVICE_MAC_ADDRESS: mac}
    updater.devices = {}
    updater._filter_macs = {}
    updater._logged_backhaul_macs = set()

    updater.hass = MagicMock()
    updater.hass.async_add_executor_job = AsyncMock()
    updater.luci = MagicMock()
    updater.luci.device_list = AsyncMock(return_value=response)

    updater.add_device = AsyncMock()
    updater.reset_counter = MagicMock()
    updater._mass_update_device = MagicMock(return_value=False)

    return updater


def _mesh() -> tuple:
    """The main and the one leaf a client is parented to, plus the registry."""

    main = _updater(MAIN_IP, "main", MAIN_ENTRY_MAC, MAIN_DEVICE_LIST)
    # Keyed on the MAC its own status reports, which is not the one the main
    # writes into `parent`. That mismatch is the whole defect.
    leaf = _updater(LEAF_IP, "leaf", LEAF_ENTRY_MAC, LEAF_DEVICE_LIST)

    return main, leaf, {MAIN_IP: {UPDATER: main}, LEAF_IP: {UPDATER: leaf}}


def _added_macs(updater: LuciUpdater) -> list:
    """Every MAC this updater was asked to take, in no particular order."""

    return sorted(call.args[0].get("mac") for call in updater.add_device.await_args_list)


@pytest.mark.asyncio
async def test_a_client_parented_to_a_leaf_reaches_that_leafs_updater() -> None:
    """The defect, in one client: listed by the main, served by the leaf."""

    main, leaf, integrations = _mesh()

    with patch(
        "custom_components.miwifi.updater.async_get_integrations",
        return_value=integrations,
    ):
        await main._async_prepare_device_list({})

    assert _added_macs(leaf) == [PARENTED_CLIENT]

    pushed = leaf.add_device.await_args_list[0]
    assert pushed.kwargs.get("is_from_parent") is True
    assert pushed.args[0][ATTR_TRACKER_ENTRY_ID] == "leaf", "it lands under the main"


@pytest.mark.asyncio
async def test_the_mains_own_clients_stay_with_the_main() -> None:
    """Widening the match must not start handing the main's clients away."""

    main, _leaf, integrations = _mesh()

    with patch(
        "custom_components.miwifi.updater.async_get_integrations",
        return_value=integrations,
    ):
        await main._async_prepare_device_list({})

    assert _added_macs(main) == MAIN_OWN_CLIENTS


@pytest.mark.asyncio
async def test_the_nodes_themselves_are_never_tracked_as_clients() -> None:
    """They are in the list too, and reading their MACs must not enrol them."""

    main, leaf, integrations = _mesh()

    with patch(
        "custom_components.miwifi.updater.async_get_integrations",
        return_value=integrations,
    ):
        await main._async_prepare_device_list({})

    for mac in (LEAF_PARENT_MAC, NODE_3_PARENT_MAC, NODE_4_PARENT_MAC):
        assert mac not in _added_macs(main) + _added_macs(leaf)


@pytest.mark.asyncio
async def test_a_leaf_polling_its_own_empty_list_pushes_nothing() -> None:
    """Every node runs this. On a leaf it must stay a no-op, not a reshuffle."""

    main, leaf, integrations = _mesh()

    with patch(
        "custom_components.miwifi.updater.async_get_integrations",
        return_value=integrations,
    ):
        await leaf._async_prepare_device_list({})

    leaf.add_device.assert_not_awaited()
    main.add_device.assert_not_awaited()
    main.reset_counter.assert_not_called()
