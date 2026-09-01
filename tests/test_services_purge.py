"""Tests for purge_inactive_devices identifier handling."""

# pylint: disable=no-member,protected-access

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.miwifi.const import DOMAIN
from custom_components.miwifi.services import (
    MiWifiPurgeInactiveDevicesServiceCall,
    _domain_identifier_values,
    _has_domain_identifier,
)

RANDOMIZED_MAC: str = "FE:CA:54:D4:FC:A3"

MOCK_MAC: str = "AA:BB:CC:DD:EE:FF"


class _FakeDevice:
    """Minimal stand-in for a device registry entry."""

    def __init__(self, device_id: str, identifiers: set, config_entries: set | None = None):
        self.id = device_id
        self.identifiers = identifiers
        self.config_entries = config_entries or {"mock-entry"}


class _FakeDeviceRegistry:
    """Device registry holding only what the purge service touches."""

    def __init__(self, devices: list[_FakeDevice]):
        self.devices = {device.id: device for device in devices}
        self.removed: list[str] = []

    def async_get(self, device_id: str) -> _FakeDevice | None:
        return self.devices.get(device_id)

    def async_remove_device(self, device_id: str) -> None:
        self.removed.append(device_id)
        self.devices.pop(device_id, None)


class _FakeEntityRegistry:
    """Entity registry with no miwifi entities left."""

    def __init__(self):
        self.entities: dict = {}

    def async_get(self, entity_id: str):
        return None


async def _async_purge(devices: list[_FakeDevice], **data) -> tuple[dict, _FakeDeviceRegistry]:
    """Run the purge service against a fake registry pair."""

    dev_reg = _FakeDeviceRegistry(devices)
    ent_reg = _FakeEntityRegistry()

    notifier = MagicMock()
    notifier.get_translations = AsyncMock(return_value={})
    notifier.notify = AsyncMock()

    service = MiWifiPurgeInactiveDevicesServiceCall(MagicMock())
    call = SimpleNamespace(
        data={"only_randomized": False, "apply": True, "verbose": False, **data}
    )

    with patch(
        "custom_components.miwifi.services.er",
        SimpleNamespace(
            async_get=lambda _hass: ent_reg,
            async_entries_for_device=lambda *_args, **_kwargs: [],
        ),
    ), patch(
        "custom_components.miwifi.services.dr",
        SimpleNamespace(async_get=lambda _hass: dev_reg),
    ), patch(
        "custom_components.miwifi.services.async_get_integrations", return_value={}
    ), patch(
        "custom_components.miwifi.services.async_dispatcher_send"
    ), patch(
        "custom_components.miwifi.services.MiWiFiNotifier", return_value=notifier
    ):
        result = await service.async_call_service(call)

    return result, dev_reg


def test_has_domain_identifier_any_arity() -> None:
    """Identifiers of any length are matched on their domain element."""

    assert _has_domain_identifier({(DOMAIN, MOCK_MAC)})
    assert _has_domain_identifier({(DOMAIN, MOCK_MAC, "leaf", "extra")})
    assert _has_domain_identifier({(DOMAIN,)})
    assert not _has_domain_identifier({("other", MOCK_MAC)})
    assert not _has_domain_identifier(set())
    assert not _has_domain_identifier({()})


def test_domain_identifier_values_skips_malformed() -> None:
    """Only miwifi identifiers carrying an id are yielded."""

    identifiers = [
        (DOMAIN, MOCK_MAC, "leaf", "extra"),
        (DOMAIN,),
        (),
        ("other", "11:22:33:44:55:66"),
    ]

    assert list(_domain_identifier_values(identifiers)) == [MOCK_MAC]


@pytest.mark.asyncio
async def test_purge_with_multi_element_identifier() -> None:
    """A 4-element identifier must not abort the service (ValueError)."""

    device = _FakeDevice("dev-4-tuple", {(DOMAIN, MOCK_MAC, "leaf", "extra")})

    result, dev_reg = await _async_purge([device])

    assert result["applied"] is True
    assert dev_reg.removed == ["dev-4-tuple"]


@pytest.mark.asyncio
async def test_purge_ignores_malformed_and_foreign_identifiers() -> None:
    """Domain-less and foreign identifiers are skipped, not unpacked."""

    devices = [
        _FakeDevice("dev-foreign", {("other", MOCK_MAC)}),
        _FakeDevice("dev-empty", {()}),
        _FakeDevice("dev-domain-only", {(DOMAIN,)}),
    ]

    result, dev_reg = await _async_purge(devices)

    assert result["applied"] is True
    assert dev_reg.removed == ["dev-domain-only"]


@pytest.mark.asyncio
async def test_purge_keeps_devices_shared_with_other_entries() -> None:
    """Devices owned by more than one config entry are never removed."""

    device = _FakeDevice(
        "dev-shared",
        {(DOMAIN, MOCK_MAC, "leaf", "extra")},
        config_entries={"entry-a", "entry-b"},
    )

    _result, dev_reg = await _async_purge([device])

    assert dev_reg.removed == []


def test_mac_is_read_from_every_unique_id_scheme() -> None:
    """The tracker scheme "miwifi-<mac>" has only two segments."""

    read = MiWifiPurgeInactiveDevicesServiceCall._mac_from_unique_id

    assert read("miwifi-d8:fb:d6:76:a1:7d") == "D8:FB:D6:76:A1:7D"
    assert read("d8:fb:d6:76:a1:7d") == "D8:FB:D6:76:A1:7D"
    assert read("miwifi-dev-d8:fb:d6:76:a1:7d-signal") == "D8:FB:D6:76:A1:7D"
    assert read("miwifi-01KEJ60BBTGP0G8XXTZ1CPH4T4-d8:fb:d6:76:a1:7d") == "D8:FB:D6:76:A1:7D"
    assert read("miwifi-d8-fb-d6-76-a1-7d_2") == "D8:FB:D6:76:A1:7D"

    assert read("miwifi-01KEJ60BBTGP0G8XXTZ1CPH4T4-devices_iot") is None
    assert read("") is None
    assert read(None) is None


@pytest.mark.asyncio
async def test_only_randomized_keeps_a_real_device() -> None:
    """A factory MAC is never purged while only_randomized is on."""

    device = _FakeDevice("dev-real", {(DOMAIN, "dc:a6:32:f1:72:dd")})

    _result, dev_reg = await _async_purge([device], only_randomized=True)

    assert dev_reg.removed == []


@pytest.mark.asyncio
async def test_only_randomized_still_purges_a_randomized_device() -> None:
    """A locally administered MAC is what the option is meant to catch."""

    device = _FakeDevice("dev-random", {(DOMAIN, RANDOMIZED_MAC)})

    _result, dev_reg = await _async_purge([device], only_randomized=True)

    assert dev_reg.removed == ["dev-random"]


@pytest.mark.asyncio
async def test_only_randomized_keeps_an_unreadable_mac() -> None:
    """An unknown MAC is not evidence of a randomized one."""

    device = _FakeDevice("dev-unknown", {(DOMAIN, "not-a-mac")})

    _result, dev_reg = await _async_purge([device], only_randomized=True)

    assert dev_reg.removed == []
