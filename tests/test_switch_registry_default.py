"""Registration of the wifi switches must not depend on live data.

`_additional_prepare()` used to set `entity_registry_enabled_default = False`
whenever band steering was on. It runs from `__init__`, and the registry keeps
whatever it was told the first time an entity was registered - so the same node
ended up with a 5 GHz switch or without one depending on whether the coordinator
had already fetched `bsd`, and on whether Smart connect was on the day the entry
was added. On the live mesh three nodes have the entity and one does not, with
band steering on for all of them.
"""

# pylint: disable=no-member,protected-access

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.miwifi.const import (
    ATTR_BINARY_SENSOR_DUAL_BAND,
    ATTR_STATE,
    ATTR_SWITCH_WIFI_2_4,
    ATTR_SWITCH_WIFI_5_0,
    ATTR_SWITCH_WIFI_5_0_GAME,
)
from custom_components.miwifi.switch import MIWIFI_SWITCHES, MiWifiSwitch


def _switch(key: str, dual_band: bool) -> MiWifiSwitch:
    """Build a switch shell holding a node with the given band steering state."""

    switch = MiWifiSwitch.__new__(MiWifiSwitch)
    switch.entity_description = next(d for d in MIWIFI_SWITCHES if d.key == key)
    switch._attr_entity_registry_enabled_default = (
        switch.entity_description.entity_registry_enabled_default
    )

    updater = MagicMock()
    updater.data = {
        ATTR_STATE: True,
        ATTR_BINARY_SENSOR_DUAL_BAND: dual_band,
        ATTR_SWITCH_WIFI_2_4: True,
        ATTR_SWITCH_WIFI_5_0: False,
        ATTR_SWITCH_WIFI_5_0_GAME: False,
    }
    switch._updater = updater

    return switch


def test_band_steering_still_takes_the_5g_switches_out_of_service() -> None:
    """The merged half is not separately controllable, so it is unavailable."""

    assert _switch(ATTR_SWITCH_WIFI_5_0, dual_band=True)._additional_prepare() is False
    assert _switch(ATTR_SWITCH_WIFI_5_0_GAME, dual_band=True)._additional_prepare() is False


def test_the_2_4_switch_is_untouched_by_band_steering() -> None:
    """Only the 5 GHz half merges into the other."""

    assert _switch(ATTR_SWITCH_WIFI_2_4, dual_band=True)._additional_prepare() is True


def test_availability_comes_back_when_band_steering_goes_off() -> None:
    """Nothing about this is permanent, unlike a registry decision."""

    assert _switch(ATTR_SWITCH_WIFI_5_0, dual_band=False)._additional_prepare() is True


def test_registration_does_not_depend_on_band_steering() -> None:
    """The whole point: two identical nodes must register the same entities."""

    for key in (ATTR_SWITCH_WIFI_5_0, ATTR_SWITCH_WIFI_5_0_GAME, ATTR_SWITCH_WIFI_2_4):
        for dual_band in (True, False):
            switch = _switch(key, dual_band=dual_band)
            switch._additional_prepare()

            assert (
                switch._attr_entity_registry_enabled_default
                is switch.entity_description.entity_registry_enabled_default
            ), f"{key} with dual_band={dual_band} changed its registry default"


def test_the_5g_switches_are_registered_enabled_by_description() -> None:
    """A node with band steering on shows the switch, unavailable and explained."""

    for key in (ATTR_SWITCH_WIFI_5_0, ATTR_SWITCH_WIFI_5_0_GAME):
        description = next(d for d in MIWIFI_SWITCHES if d.key == key)
        assert description.entity_registry_enabled_default is True
