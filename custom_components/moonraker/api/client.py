"""Moonraker API client.

Wraps the third-party ``moonraker-api`` library with:
- automatic reconnection,
- retry with exponential backoff on transient failures,
- typed exceptions (``ApiAuthError``, ``ApiConnectionError``),
- explicit timeouts.

No credential is ever logged, even at DEBUG level.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any

import async_timeout
from aiohttp import ClientError
from moonraker_api import (  # type: ignore[import-not-found]
    ClientNotAuthenticatedError,
    ClientNotConnectedError,
    MoonrakerClient,
    MoonrakerListener,
)

from .exceptions import ApiAuthError, ApiConnectionError

_LOGGER = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_SECONDS = 1.0
REQUEST_TIMEOUT = 30.0


class MoonrakerApiClient(MoonrakerListener):  # type: ignore[misc]
    """Moonraker communication API."""

    def __init__(
        self,
        url: str,
        session: Any,
        port: int = 7125,
        api_key: str | None = None,
        tls: bool = False,
    ) -> None:
        """Initialize the client wrapper."""
        self.running = False
        if api_key == "":
            api_key = None
        self._client = MoonrakerClient(
            listener=self,
            host=url,
            port=port,
            session=session,
            api_key=api_key,
            ssl=tls,
        )
        self._connect_lock = asyncio.Lock()
        self._host = url
        self._port = port

    @property
    def client(self) -> MoonrakerClient:
        """Return the underlying Moonraker websocket client."""
        return self._client

    @property
    def is_connected(self) -> bool:
        """Return whether the websocket is currently connected."""
        return bool(self._client.is_connected)

    async def start(self) -> None:
        """Start the websocket connection."""
        self.running = True
        await self._connect()

    async def stop(self) -> None:
        """Stop the websocket connection."""
        self.running = False
        async with self._connect_lock:
            if self._client.state is not None:
                await self._client.disconnect()

    async def _connect(self) -> None:
        """Connect the websocket, guarded by a lock."""
        async with self._connect_lock:
            if not self._client.is_connected:
                try:
                    async with async_timeout.timeout(REQUEST_TIMEOUT):
                        await self._client.connect()
                except (TimeoutError, ClientError, OSError) as exc:
                    raise ApiConnectionError(
                        f"Cannot connect to Moonraker at {self._host}:{self._port}"
                    ) from exc

    async def call_method(self, method: str, **kwargs: Any) -> Any:
        """Call a Moonraker JSON-RPC method with retry and backoff."""
        attempt = 0
        while True:
            try:
                if not self._client.is_connected:
                    # Best-effort reconnect: if it fails, the underlying call
                    # surfaces the connection error and the retry loop handles it.
                    with suppress(Exception):
                        await self.start()
                async with async_timeout.timeout(REQUEST_TIMEOUT):
                    return await self._client.call_method(method, **kwargs)
            except ClientNotAuthenticatedError as exc:
                raise ApiAuthError("Invalid Moonraker API key") from exc
            except (TimeoutError, ClientNotConnectedError, ClientError, OSError) as exc:
                attempt += 1
                if attempt > MAX_RETRIES:
                    raise ApiConnectionError(
                        f"Connection to Moonraker at {self._host}:{self._port} failed"
                    ) from exc
                delay = BACKOFF_SECONDS * (2 ** (attempt - 1))
                _LOGGER.debug(
                    "Moonraker call %s failed (attempt %s), retrying in %ss: %s",
                    method,
                    attempt,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
                # Force a reconnect attempt before the next try.
                if self._client.is_connected:
                    async with self._connect_lock:
                        with suppress(Exception):
                            await self._client.disconnect()
