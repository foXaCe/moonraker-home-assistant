"""Tests for the Moonraker API client robustness."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientError
from custom_components.moonraker.api.client import MAX_RETRIES, MoonrakerApiClient
from custom_components.moonraker.api.exceptions import (
    ApiAuthError,
    ApiConnectionError,
)
from moonraker_api import ClientNotAuthenticatedError, ClientNotConnectedError


def _make_client():
    """Build a client whose underlying MoonrakerClient is a mock."""
    with patch("custom_components.moonraker.api.client.MoonrakerClient") as mock_cls:
        instance = mock_cls.return_value
        instance.is_connected = False
        instance.state = None
        client = MoonrakerApiClient("1.2.3.4", None, port=7125, api_key=None)
        return client, instance


async def test_call_method_success():
    """A successful call returns the API result."""
    client, instance = _make_client()
    instance.call_method = AsyncMock(return_value={"result": "ok"})
    result = await client.call_method("printer.info")
    assert result == {"result": "ok"}
    instance.call_method.assert_awaited_once_with("printer.info")


async def test_call_method_retries_on_connection_error():
    """Transient connection failures are retried before succeeding."""
    client, instance = _make_client()
    instance.call_method = AsyncMock(
        side_effect=[ClientNotConnectedError(), ClientNotConnectedError(), "ok"]
    )
    with patch("custom_components.moonraker.api.client.asyncio.sleep", new=AsyncMock()):
        result = await client.call_method("printer.info")
    assert result == "ok"
    assert instance.call_method.await_count == 3


async def test_call_method_raises_auth_error():
    """Authentication failures surface as ApiAuthError immediately."""
    client, instance = _make_client()
    instance.call_method = AsyncMock(side_effect=ClientNotAuthenticatedError())
    with pytest.raises(ApiAuthError):
        await client.call_method("printer.info")
    assert instance.call_method.await_count == 1


async def test_call_method_raises_connection_error_after_retries():
    """Persistent connection failures raise ApiConnectionError."""
    client, instance = _make_client()
    instance.call_method = AsyncMock(side_effect=ClientNotConnectedError())
    with (
        patch("custom_components.moonraker.api.client.asyncio.sleep", new=AsyncMock()),
        pytest.raises(ApiConnectionError),
    ):
        await client.call_method("printer.info")
    assert instance.call_method.await_count == MAX_RETRIES + 1


async def test_call_method_uses_backoff():
    """Backoff sleeps grow between retries."""
    client, instance = _make_client()
    instance.call_method = AsyncMock(side_effect=ClientNotConnectedError())
    sleep_mock = AsyncMock()
    with (
        patch("custom_components.moonraker.api.client.asyncio.sleep", new=sleep_mock),
        pytest.raises(ApiConnectionError),
    ):
        await client.call_method("printer.info")
    delays = [c.args[0] for c in sleep_mock.await_args_list]
    assert delays == [1.0, 2.0, 4.0]


async def test_start_sets_running_and_connects():
    """start() marks the client as running and opens the connection."""
    client, instance = _make_client()
    instance.connect = AsyncMock()
    await client.start()
    assert client.running is True
    instance.connect.assert_awaited_once()


async def test_stop_disconnects():
    """stop() disconnects the underlying client."""
    client, instance = _make_client()
    instance.state = MagicMock()
    instance.connect = AsyncMock()
    instance.disconnect = AsyncMock()
    await client.start()
    await client.stop()
    assert client.running is False
    instance.disconnect.assert_awaited_once()


async def test_start_raises_connection_error_on_connect_failure():
    """A transport failure while connecting surfaces as ApiConnectionError."""
    client, instance = _make_client()
    instance.connect = AsyncMock(side_effect=ClientError)
    with pytest.raises(ApiConnectionError):
        await client.start()


async def test_call_method_disconnects_connected_client_after_retry_failure():
    """A connected client is torn down before retrying after a failure."""
    client, instance = _make_client()
    instance.is_connected = True
    instance.call_method = AsyncMock(side_effect=ClientNotConnectedError())
    instance.disconnect = AsyncMock()
    with (
        patch("custom_components.moonraker.api.client.asyncio.sleep", new=AsyncMock()),
        pytest.raises(ApiConnectionError),
    ):
        await client.call_method("printer.info")
    assert instance.disconnect.await_count == MAX_RETRIES
