"""Fixtures shared by the whole suite."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load the integration from custom_components.

    Without this fixture the component is invisible to the config entry
    machinery, and every flow test fails with UnknownHandler.
    """

    yield
