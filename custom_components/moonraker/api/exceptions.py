"""Typed exceptions for the Moonraker API client."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class MoonrakerApiError(HomeAssistantError):
    """Base exception for Moonraker API failures."""


class ApiAuthError(MoonrakerApiError):
    """Raised when the Moonraker API rejects authentication."""


class ApiConnectionError(MoonrakerApiError):
    """Raised when the Moonraker API cannot be reached."""


class ApiRateLimitError(MoonrakerApiError):
    """Raised when the Moonraker API rate-limits a request."""
