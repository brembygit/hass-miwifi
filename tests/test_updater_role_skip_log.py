"""A step skipped because of a node's role is a state, not an event.

Three steps do not apply to a node sitting inside somebody else's network -
`mode`, `wan` and `macfilter_info` - and each announced itself at debug on every
poll cycle. On a four node mesh at thirty seconds a cycle that came to roughly a
fifth of the log: three hundred and fifty six lines in one two thousand line
window, all saying the same thing about a configuration that had not moved.

The condition is worth stating once. What is worth repeating is a role that
changes, and `_async_prepare_mode` already reports that.
"""

# pylint: disable=no-member,protected-access

from __future__ import annotations

import logging

from unittest.mock import MagicMock

import pytest

from custom_components.miwifi.const import ATTR_SENSOR_MODE
from custom_components.miwifi.enum import Mode
from custom_components.miwifi.updater import LuciUpdater

SKIPPED = "AP mode: skipping"


def _updater(ip: str = "192.168.1.101") -> LuciUpdater:
    """Build an updater shell with only the attributes these paths touch."""

    updater = LuciUpdater.__new__(LuciUpdater)
    updater.ip = ip
    updater.is_ap_mode = False
    updater.data = {}
    updater._role_skips_logged = set()

    hass = MagicMock()

    async def _run(func, *args):
        return func(*args)

    hass.async_add_executor_job = _run
    updater.hass = hass

    return updater


@pytest.mark.asyncio
async def test_a_skip_is_reported_once_however_many_cycles_run(caplog) -> None:
    """Thirty seconds a cycle, for as long as the node keeps its role."""

    updater = _updater()

    with caplog.at_level(logging.DEBUG):
        for _ in range(10):
            await updater._log_role_skip("'wan'")

    assert caplog.text.count(SKIPPED) == 1


@pytest.mark.asyncio
async def test_each_step_speaks_for_itself(caplog) -> None:
    """Three different steps are three different pieces of news."""

    updater = _updater()

    with caplog.at_level(logging.DEBUG):
        for _ in range(3):
            for step in ("'mode'", "'wan'", "macfilter_info"):
                await updater._log_role_skip(step)

    assert caplog.text.count(SKIPPED) == 3
    for step in ("'mode'", "'wan'", "macfilter_info"):
        assert f"skipping {step} for 192.168.1.101" in caplog.text


@pytest.mark.asyncio
async def test_the_wording_is_unchanged(caplog) -> None:
    """People grep their logs for this; the latch must not rename anything."""

    updater = _updater("192.168.1.103")

    with caplog.at_level(logging.DEBUG):
        await updater._log_role_skip("macfilter_info")

    assert (
        "[MiWiFi] AP mode: skipping macfilter_info for 192.168.1.103" in caplog.text
    )


@pytest.mark.asyncio
async def test_one_nodes_silence_is_not_anothers(caplog) -> None:
    """Four entries, four updaters: the latch cannot be shared between them."""

    nodes = [_updater(f"192.168.1.10{n}") for n in (1, 2, 3, 4)]

    with caplog.at_level(logging.DEBUG):
        for _ in range(3):
            for node in nodes:
                await node._log_role_skip("'wan'")

    assert caplog.text.count(SKIPPED) == 4


@pytest.mark.asyncio
async def test_the_wan_step_goes_through_the_latch(caplog) -> None:
    """The call site, not just the helper: a leaf has no WAN to prepare."""

    updater = _updater()
    updater.data[ATTR_SENSOR_MODE] = Mode.MESH_NODE

    with caplog.at_level(logging.DEBUG):
        await updater._async_prepare_wan({})
        await updater._async_prepare_wan({})

    assert caplog.text.count(SKIPPED) == 1
    assert "skipping 'wan'" in caplog.text


@pytest.mark.asyncio
async def test_the_mode_step_goes_through_the_latch(caplog) -> None:
    """Same for the manual access point override."""

    updater = _updater()
    updater.is_ap_mode = True

    data: dict = {}

    with caplog.at_level(logging.DEBUG):
        await updater._async_prepare_mode(data)
        await updater._async_prepare_mode(data)

    assert caplog.text.count(SKIPPED) == 1
    assert "skipping 'mode'" in caplog.text
    # The skip still has to do its job, not just stay quiet about it.
    assert data[ATTR_SENSOR_MODE] == Mode.ACCESS_POINT
