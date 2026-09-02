"""Channel and signal controls follow band steering, like the switches do.

`switch.py` takes the 5 GHz switches out of service when the router merges the
two bands into one network. The selects for the same band were left behind, so a
node offered a 5 GHz channel to set while declaring that band's on/off
unavailable - and on the RA82 leaves the control read `unknown`, because the
merged firmware reports no channel for it.
"""

# pylint: disable=no-member,protected-access

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.miwifi.const import (
    ATTR_BINARY_SENSOR_DUAL_BAND,
    ATTR_SELECT_WIFI_2_4_CHANNEL,
    ATTR_SELECT_WIFI_2_4_SIGNAL_STRENGTH,
    ATTR_SELECT_WIFI_5_0_CHANNEL,
    ATTR_SELECT_WIFI_5_0_GAME_CHANNEL,
    ATTR_SELECT_WIFI_5_0_GAME_SIGNAL_STRENGTH,
    ATTR_SELECT_WIFI_5_0_SIGNAL_STRENGTH,
    ATTR_STATE,
    ATTR_WIFI_2_4_DATA,
    ATTR_WIFI_5_0_DATA,
    ATTR_WIFI_5_0_GAME_DATA,
)
from custom_components.miwifi.select import MIWIFI_SELECTS, MiWifiSelect

FIVE_GHZ_CONTROLS = (
    ATTR_SELECT_WIFI_5_0_CHANNEL,
    ATTR_SELECT_WIFI_5_0_SIGNAL_STRENGTH,
    ATTR_SELECT_WIFI_5_0_GAME_CHANNEL,
    ATTR_SELECT_WIFI_5_0_GAME_SIGNAL_STRENGTH,
)


def _select(key: str, dual_band: bool) -> MiWifiSelect:
    """Build a select shell holding a node with the given band steering state."""

    select = MiWifiSelect.__new__(MiWifiSelect)
    select.entity_description = next(d for d in MIWIFI_SELECTS if d.key == key)
    select._attr_entity_registry_enabled_default = (
        select.entity_description.entity_registry_enabled_default
    )
    select._attr_options = ["1", "36", "100", "mid"]
    select._attr_current_option = None
    select._wifi_data = {}

    updater = MagicMock()
    updater.data = {
        ATTR_STATE: True,
        ATTR_BINARY_SENSOR_DUAL_BAND: dual_band,
        # A merged node still reports data for the band: on the live mesh the
        # main answers with a 5 GHz channel of 100 while its 5 GHz switch is
        # unavailable, which is why "no data" was never the right test.
        ATTR_WIFI_2_4_DATA: {"channel": "1"},
        ATTR_WIFI_5_0_DATA: {"channel": "100"},
        ATTR_WIFI_5_0_GAME_DATA: {"channel": "149"},
    }
    select._updater = updater
    select.async_write_ha_state = MagicMock()

    return select


@pytest.mark.parametrize("key", FIVE_GHZ_CONTROLS)
def test_the_5g_controls_go_unavailable_when_the_bands_are_merged(key: str) -> None:
    """Even with data present: the band is not separately controllable."""

    select = _select(key, dual_band=True)

    assert select._merged_by_band_steering() is True

    select._handle_coordinator_update()

    assert select._attr_available is False


@pytest.mark.parametrize("key", FIVE_GHZ_CONTROLS)
def test_they_come_back_when_band_steering_goes_off(key: str) -> None:
    """Nothing here is permanent; the router can un-merge at any time."""

    select = _select(key, dual_band=False)

    select._handle_coordinator_update()

    assert select._attr_available is True


@pytest.mark.parametrize(
    "key", (ATTR_SELECT_WIFI_2_4_CHANNEL, ATTR_SELECT_WIFI_2_4_SIGNAL_STRENGTH)
)
def test_the_2_4_controls_are_untouched(key: str) -> None:
    """The merged network keeps the 2.4 GHz half as the one that is settable."""

    select = _select(key, dual_band=True)

    assert select._merged_by_band_steering() is False

    select._handle_coordinator_update()

    assert select._attr_available is True


def test_registration_does_not_depend_on_band_steering() -> None:
    """The 3.6.7 lesson: a registry default may not be taken from live data."""

    for key in FIVE_GHZ_CONTROLS:
        for dual_band in (True, False):
            select = _select(key, dual_band=dual_band)
            select._handle_coordinator_update()

            assert (
                select._attr_entity_registry_enabled_default
                is select.entity_description.entity_registry_enabled_default
            ), f"{key} with dual_band={dual_band} changed its registry default"
