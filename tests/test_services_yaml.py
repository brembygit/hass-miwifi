"""services.yaml has to satisfy the schema Home Assistant validates it with.

A single bad key costs the descriptions of *every* service in the file:
`_load_services_file` returns `{}` on `vol.Invalid`, so one malformed target took
all nine miwifi services out of the UI, not just the two that carried it.
"""

# pylint: disable=no-member,protected-access

from __future__ import annotations

from pathlib import Path

import pytest
import voluptuous as vol
from homeassistant.helpers.service import _SERVICES_SCHEMA
from homeassistant.util.yaml import load_yaml_dict

import custom_components.miwifi as miwifi

# Resolved from the package, not from this file's location: it is the copy Home
# Assistant loads that has to validate.
SERVICES_YAML = Path(miwifi.__file__).resolve().parent / "services.yaml"


def _raw() -> dict:
    return load_yaml_dict(str(SERVICES_YAML))


def test_services_yaml_validates() -> None:
    """The whole file, because the whole file is what gets dropped."""

    _SERVICES_SCHEMA(_raw())


def test_every_service_keeps_its_description() -> None:
    """A parse failure is silent in the UI, so pin the count as well."""

    assert set(_raw()) == {
        "block_device",
        "calc_passwd",
        "dump_router_data",
        "get_wifis",
        "purge_inactive_devices",
        "request",
        "set_guest_wifi",
        "set_wifis",
        "test_guest_wifi",
    }


def test_device_targets_use_the_target_selector_form() -> None:
    """`filter:` belongs to a device *selector*, not to a service target.

    `TargetSelector.CONFIG_SCHEMA` validates `device` as a list of
    `DEVICE_FILTER_SELECTOR_CONFIG_SCHEMA`, which allows integration,
    manufacturer, model and model_id - and nothing else.
    """

    for name, service in _raw().items():
        device = ((service or {}).get("target") or {}).get("device")
        if device is None:
            continue

        entries = device if isinstance(device, list) else [device]
        for entry in entries:
            assert set(entry) <= {
                "integration",
                "manufacturer",
                "model",
                "model_id",
            }, f"{name} target uses keys the target selector rejects: {sorted(entry)}"


def test_the_old_shape_really_was_rejected() -> None:
    """Guards the test itself: this is the form that broke the file."""

    with pytest.raises(vol.Invalid):
        _SERVICES_SCHEMA(
            {
                "calc_passwd": {
                    "name": "Calculate passwd",
                    "target": {"device": {"filter": [{"integration": "miwifi"}]}},
                }
            }
        )
