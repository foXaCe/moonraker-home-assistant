"""Config flow for the Moonraker integration."""

from __future__ import annotations

import logging
from typing import Any

import async_timeout
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)
from homeassistant.util import network, slugify
from moonraker_api import ClientNotAuthenticatedError  # type: ignore[import-not-found]

from .api import MoonrakerApiClient
from .const import (
    CONF_API_KEY,
    CONF_OPTION_CAMERA_PORT,
    CONF_OPTION_CAMERA_SNAPSHOT,
    CONF_OPTION_CAMERA_STREAM,
    CONF_OPTION_POLLING_RATE,
    CONF_OPTION_QUIET_UNREACHABLE,
    CONF_OPTION_THUMBNAIL_PORT,
    CONF_PORT,
    CONF_PRINTER_NAME,
    CONF_TLS,
    CONF_URL,
    DEFAULT_PORT,
    DOMAIN,
    HOSTNAME,
    METHODS,
    SERVER_INFO_UUID,
    TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid authentication."""


def _validate_port(port: Any) -> bool:
    """Return whether the configured port is valid."""
    if port in (None, ""):
        return True
    try:
        value = int(port)
    except (TypeError, ValueError):
        return False
    return 1 < value <= 65535


def _validate_api_key(api_key: Any) -> bool:
    """Return whether the configured API key looks valid."""
    if api_key in (None, ""):
        return True
    return isinstance(api_key, str) and api_key.isalnum() and len(api_key) == 32


def _validate_printer_name(printer_name: Any) -> bool:
    """Return whether the configured printer name is acceptable."""
    if printer_name in (None, ""):
        return True
    return slugify(str(printer_name)) != "unknown"


class MoonrakerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Moonraker."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not network.is_host_valid(user_input[CONF_URL]):
                errors[CONF_URL] = "host_error"
            elif not _validate_port(user_input[CONF_PORT]):
                errors[CONF_PORT] = "port_error"
            elif not _validate_api_key(user_input[CONF_API_KEY]):
                errors[CONF_API_KEY] = "api_key_error"
            elif not _validate_printer_name(user_input[CONF_PRINTER_NAME]):
                errors[CONF_PRINTER_NAME] = "printer_name_error"
            else:
                try:
                    info = await self._async_test_connection(user_input)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                else:
                    unique_id, hostname = info
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=hostname or DOMAIN,
                        data=user_input,
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self._user_schema(user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None

        errors: dict[str, str] = {}
        if user_input is not None:
            if not network.is_host_valid(user_input[CONF_URL]):
                errors[CONF_URL] = "host_error"
            elif not _validate_port(user_input[CONF_PORT]):
                errors[CONF_PORT] = "port_error"
            elif not _validate_api_key(user_input[CONF_API_KEY]):
                errors[CONF_API_KEY] = "api_key_error"
            elif not _validate_printer_name(user_input[CONF_PRINTER_NAME]):
                errors[CONF_PRINTER_NAME] = "printer_name_error"
            else:
                try:
                    await self._async_test_connection(user_input)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                else:
                    self.hass.config_entries.async_update_entry(entry, data=user_input)
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._user_schema({**entry.data, **entry.options}),
            errors=errors,
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauthentication when the API key is rejected."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        assert self._reauth_entry is not None
        return await self.async_step_reauth_confirm(user_input)

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the new API key during reauthentication."""
        errors: dict[str, str] = {}
        if user_input is not None and self._reauth_entry is not None:
            data = {**self._reauth_entry.data, CONF_API_KEY: user_input[CONF_API_KEY]}
            try:
                await self._async_test_connection(data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            else:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry, data=data
                )
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self._reauth_schema(),
            errors=errors,
        )

    async def async_step_zeroconf(self, discovery_info: Any) -> ConfigFlowResult:
        """Handle a discovered Moonraker instance via zeroconf."""
        host = discovery_info.host
        port = discovery_info.port or DEFAULT_PORT
        hostname = discovery_info.hostname or host

        if not network.is_host_valid(host):
            return self.async_abort(reason="invalid_host")

        data = {
            CONF_URL: host,
            CONF_PORT: str(port),
            CONF_TLS: False,
            CONF_API_KEY: "",
            CONF_PRINTER_NAME: "",
        }
        try:
            unique_id, printer_hostname = await self._async_test_connection(data)
        except (CannotConnect, InvalidAuth):
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        self.context.update(
            {
                "title_placeholders": {
                    "name": printer_hostname or hostname,
                }
            }
        )
        return self.async_create_entry(
            title=printer_hostname or hostname,
            data=data,
        )

    def _user_schema(self, user_input: dict[str, Any] | None = None) -> Any:
        """Build the user step schema with modern selectors."""
        from voluptuous import Schema, Optional

        values = user_input or {}
        return Schema(
            {
                Optional(
                    CONF_URL,
                    default=values.get(CONF_URL, "192.168.1.123"),
                ): TextSelector(),
                Optional(
                    CONF_PORT,
                    default=values.get(CONF_PORT, str(DEFAULT_PORT)),
                ): TextSelector(),
                Optional(
                    CONF_TLS,
                    default=values.get(CONF_TLS, False),
                ): BooleanSelector(),
                Optional(
                    CONF_API_KEY,
                    default=values.get(CONF_API_KEY, ""),
                ): TextSelector(),
                Optional(
                    CONF_PRINTER_NAME,
                    default=values.get(CONF_PRINTER_NAME, ""),
                ): TextSelector(),
            }
        )

    def _reauth_schema(self) -> Any:
        """Build the reauth step schema."""
        from voluptuous import Optional, Schema

        return Schema(
            {
                Optional(CONF_API_KEY, default=""): TextSelector(),
            }
        )

    async def _async_test_connection(self, data: dict[str, Any]) -> tuple[str, str]:
        """Probe a Moonraker instance and return its stable unique id + hostname."""
        api = MoonrakerApiClient(
            data[CONF_URL],
            async_get_clientsession(self.hass, verify_ssl=False),
            port=data.get(CONF_PORT) or DEFAULT_PORT,
            api_key=data.get(CONF_API_KEY),
            tls=data.get(CONF_TLS, False),
        )
        try:
            await api.start()
            async with async_timeout.timeout(TIMEOUT):
                printer_info = await api.client.call_method(METHODS.PRINTER_INFO.value)
                server_info = await api.client.call_method(METHODS.SERVER_INFO.value)
        except ClientNotAuthenticatedError as exc:
            raise InvalidAuth from exc
        except Exception as exc:
            raise CannotConnect from exc
        finally:
            await api.stop()

        unique_id = (server_info.get(SERVER_INFO_UUID) if server_info else None) or (
            printer_info.get(HOSTNAME) if printer_info else None
        )
        if not unique_id:
            raise CannotConnect("Moonraker reported no instance identifier")
        hostname = printer_info.get(HOSTNAME) if printer_info else None
        return str(unique_id), str(hostname) if hostname else DOMAIN

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return MoonrakerOptionsFlowHandler(config_entry)


class MoonrakerOptionsFlowHandler(OptionsFlow):
    """Handle Moonraker options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        from voluptuous import Optional, Schema

        current = self._entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=Schema(
                {
                    Optional(
                        CONF_OPTION_POLLING_RATE,
                        default=current.get(CONF_OPTION_POLLING_RATE, 30),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=3600,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    Optional(
                        CONF_OPTION_QUIET_UNREACHABLE,
                        default=current.get(CONF_OPTION_QUIET_UNREACHABLE, False),
                    ): BooleanSelector(),
                    Optional(
                        CONF_OPTION_CAMERA_STREAM,
                        default=current.get(CONF_OPTION_CAMERA_STREAM, ""),
                    ): TextSelector(),
                    Optional(
                        CONF_OPTION_CAMERA_SNAPSHOT,
                        default=current.get(CONF_OPTION_CAMERA_SNAPSHOT, ""),
                    ): TextSelector(),
                    Optional(
                        CONF_OPTION_CAMERA_PORT,
                        default=current.get(CONF_OPTION_CAMERA_PORT, ""),
                    ): TextSelector(),
                    Optional(
                        CONF_OPTION_THUMBNAIL_PORT,
                        default=current.get(CONF_OPTION_THUMBNAIL_PORT, ""),
                    ): TextSelector(),
                }
            ),
        )
