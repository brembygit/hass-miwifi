"""Tests for the sensor registry cleanup and unique_id diagnostics."""

# pylint: disable=no-member,protected-access

from __future__ import annotations

import logging
from types import SimpleNamespace

from custom_components.miwifi.const import DOMAIN
from custom_components.miwifi.sensor import (
    _cleanup_registry,
    _log_unique_id_shapes,
    _unique_id_shape,
)

ENTRY_ID: str = "01KEJ60BBTGP0G8XXTZ1CPH4T4"
OTHER_ENTRY_ID: str = "01KEJ63V8T6QKP69MDQC7HB1R8"


class _FakeRegistryEntry:
    """Minimal stand-in for an entity registry entry."""

    def __init__(self, entity_id: str, unique_id: str, config_entry_id: str, domain: str = "sensor"):
        self.entity_id = entity_id
        self.unique_id = unique_id
        self.config_entry_id = config_entry_id
        self.domain = domain
        self.platform = DOMAIN


class _FakeRegistry:
    """Entity registry exposing only what the cleanup needs."""

    def __init__(self, entries: list[_FakeRegistryEntry]):
        self.entities = {entry.entity_id: entry for entry in entries}

    def async_remove(self, entity_id: str) -> None:
        self.entities.pop(entity_id, None)


def test_unique_id_shape_classification() -> None:
    """Every scheme in the registry maps to its own readable label."""

    assert _unique_id_shape(f"{DOMAIN}-dev-aa:bb:cc:dd:ee:ff-signal", ENTRY_ID) == (
        f"{DOMAIN}-dev-<mac>-<key>"
    )
    assert _unique_id_shape(f"{DOMAIN}-{ENTRY_ID}-mode", ENTRY_ID) == (
        f"{DOMAIN}-<entry_id>-<key> (legacy)"
    )
    assert _unique_id_shape(f"{ENTRY_ID}-mode", ENTRY_ID) == "<entry_id>-<key> (router sensor)"
    assert _unique_id_shape(f"{ENTRY_ID}_config", ENTRY_ID) == "<entry_id>_<singleton>"
    assert _unique_id_shape(f"{OTHER_ENTRY_ID}-mode", ENTRY_ID) == "other"


def test_cleanup_removes_only_own_legacy_entries() -> None:
    """Legacy ids are dropped, current ids and other entries are untouched."""

    registry = _FakeRegistry(
        [
            _FakeRegistryEntry("sensor.own_legacy", f"{DOMAIN}-{ENTRY_ID}-mode", ENTRY_ID),
            _FakeRegistryEntry("sensor.own_current", f"{ENTRY_ID}-mode", ENTRY_ID),
            _FakeRegistryEntry("sensor.own_singleton", f"{ENTRY_ID}_config", ENTRY_ID),
            _FakeRegistryEntry(
                "sensor.other_legacy", f"{DOMAIN}-{OTHER_ENTRY_ID}-mode", OTHER_ENTRY_ID
            ),
        ]
    )

    removed = _cleanup_registry(registry, SimpleNamespace(entry_id=ENTRY_ID), True)

    assert removed == ["sensor.own_legacy"]
    assert set(registry.entities) == {
        "sensor.own_current",
        "sensor.own_singleton",
        "sensor.other_legacy",
    }


def test_cleanup_keeps_device_sensors_of_other_entries() -> None:
    """Disabling per-device sensors must not purge another entry's sensors."""

    registry = _FakeRegistry(
        [
            _FakeRegistryEntry(
                "sensor.own_device", f"{DOMAIN}-dev-aa:bb:cc:dd:ee:ff-signal", ENTRY_ID
            ),
            _FakeRegistryEntry(
                "sensor.other_device", f"{DOMAIN}-dev-11:22:33:44:55:66-signal", OTHER_ENTRY_ID
            ),
        ]
    )

    removed = _cleanup_registry(registry, SimpleNamespace(entry_id=ENTRY_ID), False)

    assert removed == ["sensor.own_device"]
    assert set(registry.entities) == {"sensor.other_device"}


def test_cleanup_ignores_foreign_platforms() -> None:
    """Entries of another platform or domain are never removed."""

    foreign_platform = _FakeRegistryEntry(
        "sensor.foreign", f"{DOMAIN}-{ENTRY_ID}-mode", ENTRY_ID
    )
    foreign_platform.platform = "other_integration"

    registry = _FakeRegistry(
        [
            foreign_platform,
            _FakeRegistryEntry(
                "binary_sensor.own", f"{DOMAIN}-{ENTRY_ID}-mode", ENTRY_ID, domain="binary_sensor"
            ),
        ]
    )

    assert _cleanup_registry(registry, SimpleNamespace(entry_id=ENTRY_ID), True) == []
    assert len(registry.entities) == 2


def test_log_unique_id_shapes_reports_counts(caplog) -> None:
    """The debug dump names every shape and the entries owning the rest."""

    registry = _FakeRegistry(
        [
            _FakeRegistryEntry("sensor.own_current", f"{ENTRY_ID}-mode", ENTRY_ID),
            _FakeRegistryEntry("sensor.own_legacy", f"{DOMAIN}-{ENTRY_ID}-mode", ENTRY_ID),
            _FakeRegistryEntry("sensor.other", f"{OTHER_ENTRY_ID}-mode", OTHER_ENTRY_ID),
        ]
    )

    with caplog.at_level(logging.DEBUG):
        _log_unique_id_shapes(registry, SimpleNamespace(entry_id=ENTRY_ID))

    assert "<entry_id>-<key> (router sensor)" in caplog.text
    assert f"{DOMAIN}-<entry_id>-<key> (legacy)" in caplog.text
    assert OTHER_ENTRY_ID in caplog.text
