"""A refused write must not look like an accepted one, and a reverted one must say so.

`_async_update_wifi_adapter` logged a `LuciError` at debug and returned, while
`async_select_option` went on to write the requested value into the entity. A
router that refused the change was therefore indistinguishable from one that took
it - and a mesh controller that answers `code: 0` and restores its own value at
the next sync was indistinguishable from both.
"""

# pylint: disable=no-member,protected-access

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.miwifi.const import (
    ATTR_SELECT_WIFI_2_4_CHANNEL,
    ATTR_STATE,
    ATTR_WIFI_2_4_DATA,
)
from custom_components.miwifi.exceptions import LuciRequestError
from custom_components.miwifi.select import MIWIFI_SELECTS, MiWifiSelect


def _select(key: str = ATTR_SELECT_WIFI_2_4_CHANNEL) -> MiWifiSelect:
    """Build a select shell with only the attributes these paths touch."""

    select = MiWifiSelect.__new__(MiWifiSelect)
    select.entity_description = next(d for d in MIWIFI_SELECTS if d.key == key)
    select._attr_options = ["1", "6", "11"]
    select._attr_current_option = "1"
    select._attr_available = True
    select._wifi_data = {"ssid": "net", "channel": "1"}
    select._pending_option = None
    select._pending_mismatches = 0

    updater = MagicMock()
    updater.ip = "192.168.1.104"
    updater.data = {
        ATTR_STATE: True,
        key: "1",
        ATTR_WIFI_2_4_DATA: {"ssid": "net", "channel": "1"},
    }
    updater.luci.set_wifi = AsyncMock()
    select._updater = updater
    select.async_write_ha_state = MagicMock()

    return select


def _report(select: MiWifiSelect, channel: str) -> None:
    """Let a refresh land carrying what the router says now."""

    key = select.entity_description.key
    select._updater.data[key] = channel
    select._updater.data[ATTR_WIFI_2_4_DATA] = {"ssid": "net", "channel": channel}
    select._handle_coordinator_update()


@pytest.mark.asyncio
async def test_a_refused_write_surfaces_and_does_not_move_the_entity() -> None:
    """It used to log at debug and show the value anyway."""

    select = _select()
    select._updater.luci.set_wifi = AsyncMock(
        side_effect=LuciRequestError("Invalid value")
    )

    with pytest.raises(HomeAssistantError, match="refused the change"):
        await select.async_select_option("6")

    assert select._attr_current_option == "1"
    assert select._pending_option is None
    select.async_write_ha_state.assert_not_called()


@pytest.mark.asyncio
async def test_an_accepted_write_is_shown_and_then_confirmed() -> None:
    """The happy path stays exactly as it was."""

    select = _select()

    await select.async_select_option("6")

    assert select._attr_current_option == "6"
    assert select._pending_option == "6"

    _report(select, "6")

    assert select._pending_option is None
    assert select._pending_mismatches == 0


@pytest.mark.asyncio
async def test_a_reverted_write_is_reported(caplog) -> None:
    """`code: 0` and then the old value back is what a mesh controller does."""

    select = _select()

    await select.async_select_option("6")

    with caplog.at_level(logging.WARNING):
        # A poll already in flight when the write landed reports the old value
        # once through no fault of the router, so one disagreement is not enough.
        _report(select, "1")
        assert "reverted" not in caplog.text
        assert select._pending_option == "6"

        _report(select, "1")

    assert "reverted wifi_2_4_channel to 1 after accepting 6" in caplog.text
    assert select._pending_option is None


@pytest.mark.asyncio
async def test_nothing_is_reported_when_nothing_was_asked(caplog) -> None:
    """A value changing on its own is the router's business, not a revert."""

    select = _select()

    with caplog.at_level(logging.WARNING):
        _report(select, "11")
        _report(select, "1")

    assert "reverted" not in caplog.text
