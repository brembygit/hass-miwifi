"""Tests for the xqnetwork/mode fallback logging."""

# pylint: disable=no-member,protected-access

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from custom_components.miwifi.exceptions import LuciError
from custom_components.miwifi.luci import LuciClient


def _client_with_failing_mode() -> LuciClient:
    """Build a client whose primary mode endpoint always fails."""

    client = LuciClient(MagicMock())

    async def _get(path: str, **_kwargs):
        if path == client._api_paths["mode"]:
            raise LuciError("primary endpoint down")
        return {"netmode": 3}

    client.get = _get

    return client


@pytest.mark.asyncio
async def test_mode_falls_back_to_netmode() -> None:
    """The netmode payload is normalised to the mode field."""

    client = _client_with_failing_mode()

    assert await client.mode() == {"netmode": 3, "mode": 3}


@pytest.mark.asyncio
async def test_mode_fallback_is_logged_once(caplog) -> None:
    """The fallback is reported at debug level, and only the first time."""

    client = _client_with_failing_mode()

    with caplog.at_level(logging.DEBUG):
        await client.mode()
        await client.mode()
        await client.mode()

    messages = [rec for rec in caplog.records if "falling back to" in rec.getMessage()]

    assert len(messages) == 1
    assert messages[0].levelno == logging.DEBUG
