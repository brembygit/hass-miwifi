"""Tests for the panel version cache and failure backoff."""

# pylint: disable=no-member,protected-access

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.miwifi import frontend
from custom_components.miwifi.frontend import (
    PANEL_VERSION_BACKOFF_START,
    PANEL_VERSION_STATE,
    async_read_remote_version,
    describe_error,
)


def _hass() -> MagicMock:
    """Build a hass double whose executor job runs the callable inline."""

    hass = MagicMock()
    hass.data = {}

    async def _run(func, *args):
        return func(*args)

    hass.async_add_executor_job = _run

    return hass


def test_describe_error_is_never_empty() -> None:
    """An empty str() must not end up as the logged reason."""

    silent = aiohttp.ClientError()

    assert str(silent) == ""
    assert describe_error(silent) == "ClientError()"

    rate_limited = aiohttp.ClientResponseError(
        SimpleNamespace(real_url="", url=""), (), status=429
    )

    assert describe_error(rate_limited) == "HTTP 429 (ClientResponseError)"


@pytest.mark.asyncio
async def test_version_is_cached_between_calls(monkeypatch) -> None:
    """The repository is queried once per cache window, not once per cycle."""

    hass = _hass()
    reader = AsyncMock(return_value="1.2.3")
    monkeypatch.setattr(frontend, "read_remote_version", reader)

    assert await async_read_remote_version(hass, MagicMock()) == "1.2.3"
    assert await async_read_remote_version(hass, MagicMock()) == "1.2.3"
    assert await async_read_remote_version(hass, MagicMock()) == "1.2.3"

    assert reader.await_count == 1


@pytest.mark.asyncio
async def test_failure_warns_once_and_backs_off(monkeypatch, caplog) -> None:
    """A 429 burst yields one informative warning, then a quiet backoff."""

    hass = _hass()
    reader = AsyncMock(
        side_effect=aiohttp.ClientResponseError(
            SimpleNamespace(real_url="", url=""), (), status=429
        )
    )
    monkeypatch.setattr(frontend, "read_remote_version", reader)

    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            assert await async_read_remote_version(hass, MagicMock()) is None

    warnings = [rec for rec in caplog.records if "panel version could not be read" in rec.getMessage()]

    assert len(warnings) == 1
    assert "HTTP 429" in warnings[0].getMessage()

    # Only the first attempt reached the network; the rest hit the backoff.
    assert reader.await_count == 1
    assert hass.data[PANEL_VERSION_STATE]["backoff"] == PANEL_VERSION_BACKOFF_START


@pytest.mark.asyncio
async def test_failure_keeps_serving_the_last_known_version(monkeypatch) -> None:
    """A later failure must not wipe a version that was read successfully."""

    hass = _hass()
    monkeypatch.setattr(frontend, "read_remote_version", AsyncMock(return_value="1.2.3"))
    assert await async_read_remote_version(hass, MagicMock()) == "1.2.3"

    # Expire the cache, then make the repository fail.
    hass.data[PANEL_VERSION_STATE]["valid_until"] = None
    monkeypatch.setattr(
        frontend, "read_remote_version", AsyncMock(side_effect=aiohttp.ClientError())
    )

    assert await async_read_remote_version(hass, MagicMock()) == "1.2.3"


@pytest.mark.asyncio
async def test_backoff_grows_and_resets_on_success(monkeypatch) -> None:
    """Consecutive failures widen the window; a success clears it."""

    hass = _hass()
    monkeypatch.setattr(
        frontend, "read_remote_version", AsyncMock(side_effect=aiohttp.ClientError())
    )

    await async_read_remote_version(hass, MagicMock())
    state = hass.data[PANEL_VERSION_STATE]
    assert state["backoff"] == PANEL_VERSION_BACKOFF_START

    state["retry_after"] = None
    await async_read_remote_version(hass, MagicMock())
    assert state["backoff"] == PANEL_VERSION_BACKOFF_START * 2

    state["retry_after"] = None
    monkeypatch.setattr(frontend, "read_remote_version", AsyncMock(return_value="2.0.0"))
    assert await async_read_remote_version(hass, MagicMock()) == "2.0.0"
    assert state["backoff"] is None
    assert state["failure_logged"] is False
