"""Tests for the guards that stop a sensor set being added twice."""

# pylint: disable=no-member,protected-access

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.miwifi.const import (
    DEVICE_SENSORS_ADDED,
    DOMAIN,
    SENSORS_ADDED,
)
from custom_components.miwifi.sensor import (
    _async_add_all_sensors_later,
    _claim_device,
)

ENTRY_ID: str = "01KEJ60BBTGP0G8XXTZ1CPH4T4"
OTHER_ENTRY_ID: str = "01KEJ63V8T6QKP69MDQC7HB1R8"
MAC: str = "AA:BB:CC:DD:EE:FF"


def _hass(*entry_ids: str) -> SimpleNamespace:
    """A hass shell holding entry data for the given entries."""

    return SimpleNamespace(data={DOMAIN: {entry_id: {} for entry_id in entry_ids}})


def test_a_device_is_claimed_once() -> None:
    """The first caller wins; the second is told to stand down."""

    hass = _hass(ENTRY_ID)
    entry = SimpleNamespace(entry_id=ENTRY_ID)

    assert _claim_device(hass, entry, MAC) is True
    assert _claim_device(hass, entry, MAC) is False
    assert hass.data[DOMAIN][ENTRY_ID][DEVICE_SENSORS_ADDED] == {MAC}


def test_the_claim_ignores_mac_casing() -> None:
    """The two add paths do not agree on casing, the claim has to."""

    hass = _hass(ENTRY_ID)
    entry = SimpleNamespace(entry_id=ENTRY_ID)

    assert _claim_device(hass, entry, MAC.lower()) is True
    assert _claim_device(hass, entry, MAC.upper()) is False


def test_each_entry_claims_separately() -> None:
    """Entries own their entities, so one claiming must not block another."""

    hass = _hass(ENTRY_ID, OTHER_ENTRY_ID)

    assert _claim_device(hass, SimpleNamespace(entry_id=ENTRY_ID), MAC) is True
    assert _claim_device(hass, SimpleNamespace(entry_id=OTHER_ENTRY_ID), MAC) is True


def test_nothing_is_claimed_for_an_unloaded_entry() -> None:
    """Unloading drops the entry data; a late dispatch must not resurrect it."""

    hass = _hass()

    assert _claim_device(hass, SimpleNamespace(entry_id=ENTRY_ID), MAC) is False


@pytest.mark.asyncio
async def test_the_router_set_is_not_added_twice() -> None:
    """The leftover task of a previous setup has to find the set taken."""

    hass = _hass(ENTRY_ID)
    hass.data[DOMAIN][ENTRY_ID][SENSORS_ADDED] = True
    entry = SimpleNamespace(entry_id=ENTRY_ID, options={}, data={})

    updater = MagicMock()
    updater.data = {"topo_graph": {"graph": {"is_main": True}}}
    updater.async_request_refresh = AsyncMock()

    async_add_entities = MagicMock()

    with patch(
        "custom_components.miwifi.sensor.async_get_updater", return_value=updater
    ):
        await _async_add_all_sensors_later(hass, entry, async_add_entities)

    async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_nothing_is_added_for_an_unloaded_entry() -> None:
    """A reload can retire the entry while this task waits for the topology."""

    hass = _hass()
    entry = SimpleNamespace(entry_id=ENTRY_ID, options={}, data={})

    updater = MagicMock()
    updater.data = {"topo_graph": {"graph": {"is_main": True}}}
    updater.async_request_refresh = AsyncMock()

    async_add_entities = MagicMock()

    with patch(
        "custom_components.miwifi.sensor.async_get_updater", return_value=updater
    ):
        await _async_add_all_sensors_later(hass, entry, async_add_entities)

    async_add_entities.assert_not_called()
