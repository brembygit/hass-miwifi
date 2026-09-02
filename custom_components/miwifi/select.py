"""Select component."""

from __future__ import annotations

from .logger import _LOGGER
from typing import Any, Final

from homeassistant.components.select import (
    ENTITY_ID_FORMAT,
    SelectEntity,
    SelectEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_SELECT_SIGNAL_STRENGTH_OPTIONS,
    ATTR_SELECT_WIFI_2_4_CHANNEL,
    ATTR_SELECT_WIFI_2_4_CHANNEL_NAME,
    ATTR_SELECT_WIFI_2_4_CHANNEL_OPTIONS,
    ATTR_SELECT_WIFI_2_4_CHANNELS,
    ATTR_SELECT_WIFI_2_4_SIGNAL_STRENGTH,
    ATTR_SELECT_WIFI_2_4_SIGNAL_STRENGTH_NAME,
    ATTR_SELECT_WIFI_5_0_CHANNEL,
    ATTR_SELECT_WIFI_5_0_CHANNEL_NAME,
    ATTR_SELECT_WIFI_5_0_CHANNEL_OPTIONS,
    ATTR_SELECT_WIFI_5_0_CHANNELS,
    ATTR_SELECT_WIFI_5_0_GAME_CHANNEL,
    ATTR_SELECT_WIFI_5_0_GAME_CHANNEL_NAME,
    ATTR_SELECT_WIFI_5_0_GAME_CHANNEL_OPTIONS,
    ATTR_SELECT_WIFI_5_0_GAME_CHANNELS,
    ATTR_SELECT_WIFI_5_0_GAME_SIGNAL_STRENGTH,
    ATTR_SELECT_WIFI_5_0_GAME_SIGNAL_STRENGTH_NAME,
    ATTR_SELECT_WIFI_5_0_SIGNAL_STRENGTH,
    ATTR_SELECT_WIFI_5_0_SIGNAL_STRENGTH_NAME,
    ATTR_STATE,
    ATTR_WIFI_2_4_DATA,
    ATTR_WIFI_5_0_DATA,
    ATTR_WIFI_5_0_GAME_DATA,
    ATTR_WIFI_ADAPTER_LENGTH,
)
from .entity import MiWifiEntity
from .enum import Wifi, DeviceClass
from .exceptions import LuciError
from .updater import LuciUpdater, async_get_updater

PARALLEL_UPDATES = 0

CHANNELS_MAP: Final = {
    ATTR_SELECT_WIFI_2_4_CHANNEL: ATTR_SELECT_WIFI_2_4_CHANNELS,
    ATTR_SELECT_WIFI_5_0_CHANNEL: ATTR_SELECT_WIFI_5_0_CHANNELS,
    ATTR_SELECT_WIFI_5_0_GAME_CHANNEL: ATTR_SELECT_WIFI_5_0_GAME_CHANNELS,
}

DATA_MAP: Final = {
    ATTR_SELECT_WIFI_2_4_CHANNEL: ATTR_WIFI_2_4_DATA,
    ATTR_SELECT_WIFI_5_0_CHANNEL: ATTR_WIFI_5_0_DATA,
    ATTR_SELECT_WIFI_5_0_GAME_CHANNEL: ATTR_WIFI_5_0_GAME_DATA,
    ATTR_SELECT_WIFI_2_4_SIGNAL_STRENGTH: ATTR_WIFI_2_4_DATA,
    ATTR_SELECT_WIFI_5_0_SIGNAL_STRENGTH: ATTR_WIFI_5_0_DATA,
    ATTR_SELECT_WIFI_5_0_GAME_SIGNAL_STRENGTH: ATTR_WIFI_5_0_GAME_DATA,
}

OPTIONS_MAP: Final = {
    ATTR_SELECT_WIFI_2_4_CHANNEL: ATTR_SELECT_WIFI_2_4_CHANNEL_OPTIONS,
    ATTR_SELECT_WIFI_5_0_CHANNEL: ATTR_SELECT_WIFI_5_0_CHANNEL_OPTIONS,
    ATTR_SELECT_WIFI_5_0_GAME_CHANNEL: ATTR_SELECT_WIFI_5_0_GAME_CHANNEL_OPTIONS,
    ATTR_SELECT_WIFI_2_4_SIGNAL_STRENGTH: ATTR_SELECT_SIGNAL_STRENGTH_OPTIONS,
    ATTR_SELECT_WIFI_5_0_SIGNAL_STRENGTH: ATTR_SELECT_SIGNAL_STRENGTH_OPTIONS,
    ATTR_SELECT_WIFI_5_0_GAME_SIGNAL_STRENGTH: ATTR_SELECT_SIGNAL_STRENGTH_OPTIONS,
}

ICONS: Final = {
    f"{ATTR_SELECT_WIFI_2_4_SIGNAL_STRENGTH}_min": "mdi:wifi-strength-1",
    f"{ATTR_SELECT_WIFI_2_4_SIGNAL_STRENGTH}_mid": "mdi:wifi-strength-2",
    f"{ATTR_SELECT_WIFI_2_4_SIGNAL_STRENGTH}_max": "mdi:wifi-strength-4",
    f"{ATTR_SELECT_WIFI_5_0_SIGNAL_STRENGTH}_min": "mdi:wifi-strength-1",
    f"{ATTR_SELECT_WIFI_5_0_SIGNAL_STRENGTH}_mid": "mdi:wifi-strength-2",
    f"{ATTR_SELECT_WIFI_5_0_SIGNAL_STRENGTH}_max": "mdi:wifi-strength-4",
    f"{ATTR_SELECT_WIFI_5_0_GAME_SIGNAL_STRENGTH}_min": "mdi:wifi-strength-1",
    f"{ATTR_SELECT_WIFI_5_0_GAME_SIGNAL_STRENGTH}_mid": "mdi:wifi-strength-2",
    f"{ATTR_SELECT_WIFI_5_0_GAME_SIGNAL_STRENGTH}_max": "mdi:wifi-strength-4",
}

MIWIFI_SELECTS: tuple[SelectEntityDescription, ...] = (
    SelectEntityDescription(
        key=ATTR_SELECT_WIFI_2_4_CHANNEL,
        name=ATTR_SELECT_WIFI_2_4_CHANNEL_NAME,
        icon="mdi:format-list-numbered",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    SelectEntityDescription(
        key=ATTR_SELECT_WIFI_5_0_CHANNEL,
        name=ATTR_SELECT_WIFI_5_0_CHANNEL_NAME,
        icon="mdi:format-list-numbered",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    SelectEntityDescription(
        key=ATTR_SELECT_WIFI_5_0_GAME_CHANNEL,
        name=ATTR_SELECT_WIFI_5_0_GAME_CHANNEL_NAME,
        icon="mdi:format-list-numbered",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    SelectEntityDescription(
        key=ATTR_SELECT_WIFI_2_4_SIGNAL_STRENGTH,
        name=ATTR_SELECT_WIFI_2_4_SIGNAL_STRENGTH_NAME,
        icon=ICONS[f"{ATTR_SELECT_WIFI_2_4_SIGNAL_STRENGTH}_max"],
        device_class=DeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    SelectEntityDescription(
        key=ATTR_SELECT_WIFI_5_0_SIGNAL_STRENGTH,
        name=ATTR_SELECT_WIFI_5_0_SIGNAL_STRENGTH_NAME,
        icon=ICONS[f"{ATTR_SELECT_WIFI_5_0_SIGNAL_STRENGTH}_max"],
        device_class=DeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    SelectEntityDescription(
        key=ATTR_SELECT_WIFI_5_0_GAME_SIGNAL_STRENGTH,
        name=ATTR_SELECT_WIFI_5_0_GAME_SIGNAL_STRENGTH_NAME,
        icon=ICONS[f"{ATTR_SELECT_WIFI_5_0_GAME_SIGNAL_STRENGTH}_max"],
        device_class=DeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)




async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    updater: LuciUpdater = async_get_updater(hass, config_entry.entry_id)

    entities: list[MiWifiSelect] = [
        MiWifiSelect(
            f"{config_entry.entry_id}-{description.key}",
            description,
            updater,
        )
        for description in MIWIFI_SELECTS
        if description.key
        not in [
            ATTR_SELECT_WIFI_5_0_GAME_CHANNEL,
            ATTR_SELECT_WIFI_5_0_GAME_SIGNAL_STRENGTH,
        ]
        or updater.supports_game
    ]

    async_add_entities(entities)


class MiWifiSelect(MiWifiEntity, SelectEntity):
    def __init__(
        self,
        unique_id: str,
        description: SelectEntityDescription,
        updater: LuciUpdater,
    ) -> None:
        super().__init__(unique_id, description, updater, ENTITY_ID_FORMAT)

        self._attr_current_option = updater.data.get(description.key, None)

        self._attr_options = []
        if description.key in CHANNELS_MAP:
            self._attr_options = updater.data.get(CHANNELS_MAP[description.key], [])

        if description.key in OPTIONS_MAP and len(self._attr_options) == 0:
            if (
                updater.data.get(ATTR_WIFI_ADAPTER_LENGTH, 2) > 2
                and description.key == ATTR_SELECT_WIFI_5_0_CHANNEL
            ):
                self._attr_options = [
                    option
                    for option in OPTIONS_MAP[description.key]
                    if option not in OPTIONS_MAP[ATTR_SELECT_WIFI_5_0_GAME_CHANNEL]
                ]
            else:
                self._attr_options = OPTIONS_MAP[description.key]

        self._wifi_data: dict = {}
        if description.key in DATA_MAP:
            self._wifi_data = updater.data.get(DATA_MAP[description.key], {})

        # What we last asked the router for, and how many refreshes have come
        # back disagreeing with it. See _check_pending_option.
        self._pending_option: str | None = None
        self._pending_mismatches: int = 0

        self._attr_available: bool = (
            updater.data.get(ATTR_STATE, False)
            and len(self._attr_options) > 0
            and self._channel_is_reported()
        )

    def _channel_is_reported(self) -> bool:
        """Does the router tell us which channel this band is on?

        Band steering was the first suspect - it is what takes the 5 GHz
        switches out of service in switch.py - but it is the wrong test here.
        Under the same merged network the RD28 pair answers with a real 5 GHz
        channel while the RA82 pair answers with nothing, so keying on the
        merge hid a working control on half the fleet, and with it the only
        per-node view of the channel: the panel's own wifi endpoint is
        main-only (`ws_api._pick_updater`), so it shows one router's numbers on
        every node's card.

        What is actually broken is a channel picker for a band whose channel
        the router will not state. That is the condition, and it needs no
        knowledge of why the router is quiet.

        Signal strength is not covered: it is reported everywhere, on both
        bands, merged or not.

        Availability only. Registration must not depend on this: the value
        changes, a registry default does not.

        :return bool: not a channel control, or one the router reports
        """

        if self.entity_description.key not in CHANNELS_MAP:
            return True

        channel = self._updater.data.get(self.entity_description.key)

        # "0" is how a firmware says "unset" where it says anything at all.
        return str(channel or "").strip() not in ("", "0")

    @property
    def icon(self) -> str | None:
        option = self._attr_current_option
        return ICONS.get(f"{self.entity_description.key}_{option}")

    def _handle_coordinator_update(self) -> None:
        current_option: str = self._updater.data.get(self.entity_description.key, False)

        wifi_data: dict = {}
        if self.entity_description.key in DATA_MAP:
            wifi_data = self._updater.data.get(
                DATA_MAP[self.entity_description.key], {}
            )

        is_available: bool = (
            self._updater.data.get(ATTR_STATE, False)
            and len(self._attr_options) > 0
            and len(wifi_data) > 0
            and self._channel_is_reported()
        )

        self._check_pending_option(current_option)

        data_changed: list = [
            key
            for key, value in wifi_data.items()
            if key not in self._wifi_data or value != self._wifi_data[key]
        ]

        if (
            self._attr_current_option == current_option
            and self._attr_available == is_available
            and not data_changed
        ):
            return

        self._attr_available = is_available
        self._attr_current_option = current_option
        self._wifi_data = wifi_data

        self.async_write_ha_state()

    async def _wifi_2_4_channel_change(self, option: str) -> None:
        await self._async_update_wifi_adapter({"wifiIndex": Wifi.ADAPTER_2_4.value, "channel": option})

    async def _wifi_5_0_channel_change(self, option: str) -> None:
        await self._async_update_wifi_adapter({"wifiIndex": Wifi.ADAPTER_5_0.value, "channel": option})

    async def _wifi_5_0_game_channel_change(self, option: str) -> None:
        await self._async_update_wifi_adapter({"wifiIndex": Wifi.ADAPTER_5_0_GAME.value, "channel": option})

    async def _wifi_2_4_signal_strength_change(self, option: str) -> None:
        await self._async_update_wifi_adapter({"wifiIndex": Wifi.ADAPTER_2_4.value, "txpwr": option})

    async def _wifi_5_0_signal_strength_change(self, option: str) -> None:
        await self._async_update_wifi_adapter({"wifiIndex": Wifi.ADAPTER_5_0.value, "txpwr": option})

    async def _wifi_5_0_game_signal_strength_change(self, option: str) -> None:
        await self._async_update_wifi_adapter({"wifiIndex": Wifi.ADAPTER_5_0_GAME.value, "txpwr": option})

    async def _async_update_wifi_adapter(self, data: dict) -> None:
        new_data: dict = self._wifi_data | data

        try:
            await self._updater.luci.set_wifi(new_data)
        except LuciError as _e:
            # This used to be swallowed at debug level while the entity went on
            # to show the new value anyway, so a router that refused the change
            # looked exactly like one that accepted it.
            _LOGGER.debug("WiFi update error: %r", _e)

            raise HomeAssistantError(
                f"{self._updater.ip} refused the change to"
                f" {self.entity_description.key}: {_e}"
            ) from _e

        self._wifi_data = new_data

    async def async_select_option(self, option: str) -> None:
        if action := getattr(self, f"_{self.entity_description.key}_change"):
            # Raises if the router refused it, and then nothing below runs.
            await action(option)

            self._pending_option = option
            self._pending_mismatches = 0

            self._updater.data[self.entity_description.key] = option
            self._attr_current_option = option

            self.async_write_ha_state()

    def _check_pending_option(self, reported: Any) -> None:
        """Say so when the router quietly puts the old value back.

        A mesh controller owns the radio settings of the nodes it manages: it
        answers `code: 0` to a channel change and restores its own value at the
        next sync. Accepted-then-reverted and accepted-and-kept are identical in
        the interface, and telling them apart meant reading the debug log.

        Two disagreeing refreshes are required, because a poll already in flight
        when the write landed reports the old value once through no fault of the
        router.
        """

        if self._pending_option is None:
            return

        if str(reported) == str(self._pending_option):
            self._pending_option = None
            self._pending_mismatches = 0
            return

        self._pending_mismatches += 1
        if self._pending_mismatches < 2:
            return

        _LOGGER.warning(
            "[MiWiFi] %s reverted %s to %s after accepting %s."
            " On a mesh the controller owns the radio settings of its nodes:"
            " change them where the controller can see it, not per node",
            self._updater.ip,
            self.entity_description.key,
            reported,
            self._pending_option,
        )

        self._pending_option = None
        self._pending_mismatches = 0