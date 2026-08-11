"""Test moonraker config flow."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.config_flow import CannotConnect
from custom_components.moonraker.const import (
    CONF_API_KEY,
    CONF_PORT,
    CONF_PRINTER_NAME,
    CONF_TLS,
    CONF_URL,
    CONF_OPTION_CAMERA_SNAPSHOT,
    CONF_OPTION_CAMERA_STREAM,
    DOMAIN,
)

from .const import MOCK_CONFIG, MOCK_OPTIONS

# Fake API key used only in tests; never a real credential.
FAKE_KEY = "fake-api-key"


@pytest.fixture(name="bypass_connect_client")
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


@pytest.fixture(name="error_connect_client")
def error_connect_client_fixture():
    """Throw error when trying to connect."""
    with patch(
        "custom_components.moonraker.MoonrakerApiClient.start",
        side_effect=Exception,
    ):
        yield


@pytest.mark.usefixtures("bypass_connect_client")
async def test_successful_config_flow(hass):
    """Test a successful config flow."""
    # Initialize a config flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Check that the config flow shows the user form as the first step
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_CONFIG
    )

    # Check that the config flow is complete and a new entry is created with
    # the input data
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "mainsail"
    assert result["data"] == MOCK_CONFIG
    assert result["result"]


@pytest.mark.usefixtures("bypass_connect_client")
async def test_tmp_failing_config_flow(hass):
    """Test a failed config flow due to credential validation failure."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.moonraker.config_flow.MoonrakerConfigFlow._async_test_connection",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_CONFIG
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_host_with_protocol(hass):
    """Test server host when it has protocol."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "http://1.2.3.4"}
    )

    assert result["errors"] == {CONF_URL: "host_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_host_with_trailing_slash(hass):
    """Test server host when has trailing slash."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "website.com/"}
    )

    assert result["errors"] == {CONF_URL: "host_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_host_with_incomplete_ip(hass):
    """Test server host when has incomplete ip."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3"}
    )

    assert result["errors"] == {CONF_URL: "host_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_host_when_good(hass):
    """Test server host when good."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4"}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "mainsail"
    assert result["data"] == {
        CONF_URL: "1.2.3.4",
        CONF_PORT: "7125",
        CONF_TLS: False,
        CONF_API_KEY: "",
        CONF_PRINTER_NAME: "",
    }
    assert result["result"]


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_ssl_enabled(hass):
    """Test server host with TLS."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4", CONF_TLS: True}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "mainsail"
    assert result["data"] == {
        CONF_URL: "1.2.3.4",
        CONF_PORT: "7125",
        CONF_API_KEY: "",
        CONF_TLS: True,
        CONF_PRINTER_NAME: "",
    }
    assert result["result"]


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_port_too_low(hass):
    """Test server port when it's too low."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_PORT: "-32"}
    )
    assert result["errors"] == {CONF_PORT: "port_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_port_too_high(hass):
    """Test server port when it's too high."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_PORT: "4840138103"}
    )
    assert result["errors"] == {CONF_PORT: "port_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_port_not_an_int(hass):
    """Test port when it's not an int."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_PORT: "1234wdw"}
    )
    assert result["errors"] == {CONF_PORT: "port_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_port_when_good_port(hass):
    """Test server port when it's good."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4", CONF_PORT: "7611"}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "mainsail"
    assert result["data"] == {
        CONF_URL: "1.2.3.4",
        CONF_PORT: "7611",
        CONF_TLS: False,
        CONF_API_KEY: "",
        CONF_PRINTER_NAME: "",
    }
    assert result["result"]


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_port_when_port_empty(hass):
    """Test server port is left empty."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4", CONF_PORT: ""}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "mainsail"
    assert result["data"] == {
        CONF_URL: "1.2.3.4",
        CONF_PORT: "",
        CONF_TLS: False,
        CONF_API_KEY: "",
        CONF_PRINTER_NAME: "",
    }


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_api_key_weird_char(hass):
    """Test api key when contains weird characters."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_API_KEY: "$7ylD3EuPWWxGlsshlCIJjzR$NbQzlre"}
    )
    assert result["errors"] == {CONF_API_KEY: "api_key_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_api_key_too_short(hass):
    """Test api key when it's too short."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_API_KEY: "D7ylD3EuPWWxGlsshlCIJjzRQzlre"}
    )
    assert result["errors"] == {CONF_API_KEY: "api_key_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_api_key_too_long(hass):
    """Test api key when it's too long."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_API_KEY: "D7ylD3EuPWWxGlsshlsd1CIJjzRSNbQzlre"},
    )
    assert result["errors"] == {CONF_API_KEY: "api_key_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_api_key_when_good(hass):
    """Test api key when it's good."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_URL: "1.2.3.4",
            CONF_API_KEY: "A7ylD3EuPWWxGlsshlCIJjzRBNbQzlre",
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "mainsail"
    assert result["data"] == {
        CONF_URL: "1.2.3.4",
        CONF_PORT: "7125",
        CONF_TLS: False,
        CONF_API_KEY: "A7ylD3EuPWWxGlsshlCIJjzRBNbQzlre",
        CONF_PRINTER_NAME: "",
    }
    assert result["result"]


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_api_key_when_empty(hass):
    """Test api key when it's empty."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_URL: "1.2.3.4",
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "mainsail"
    assert result["data"] == {
        CONF_URL: "1.2.3.4",
        CONF_PORT: "7125",
        CONF_TLS: False,
        CONF_API_KEY: "",
        CONF_PRINTER_NAME: "",
    }
    assert result["result"]


@pytest.mark.usefixtures("bypass_connect_client")
async def test_printer_name_when_invalid(hass):
    """Test printer name when it's invalid."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_PRINTER_NAME: "!"}
    )

    assert result["errors"] == {CONF_PRINTER_NAME: "printer_name_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_printer_name_when_good(hass):
    """Test printer name when good."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_URL: "1.2.3.4", CONF_PRINTER_NAME: "example name"},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "mainsail"
    assert result["data"] == {
        CONF_URL: "1.2.3.4",
        CONF_PORT: "7125",
        CONF_TLS: False,
        CONF_API_KEY: "",
        CONF_PRINTER_NAME: "example name",
    }
    assert result["result"]


@pytest.mark.usefixtures("error_connect_client")
async def test_bad_connection_config_flow(hass):
    """Test a config flow with a bad connection."""
    # Initialize a config flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Check that the config flow shows the user form as the first step
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_CONFIG
    )

    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_option_config_camera_services(hass):
    """Test a config flow with camera services."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init("test")
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_OPTION_CAMERA_STREAM: MOCK_OPTIONS[CONF_OPTION_CAMERA_STREAM],
            CONF_OPTION_CAMERA_SNAPSHOT: MOCK_OPTIONS[CONF_OPTION_CAMERA_SNAPSHOT],
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("bypass_connect_client")
async def test_already_configured_aborts(hass):
    """A second entry for the same printer unique id aborts."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="76ae56ef-3391-4f7a-89b4-8cc1cb4d6454",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_CONFIG
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_success_updates_api_key(hass):
    """Reauth with a valid key updates the entry and reloads it."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="reauth")
    entry.add_to_hass(hass)

    with patch(
        "custom_components.moonraker.MoonrakerApiClient.start",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_REAUTH, "entry_id": "reauth"},
        )
        assert result["type"] == FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: FAKE_KEY},
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == FAKE_KEY


async def test_reauth_invalid_key_shows_error(hass):
    """Reauth with a rejected key shows invalid_auth."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="reauth_bad")
    entry.add_to_hass(hass)

    with patch(
        "custom_components.moonraker.MoonrakerApiClient.start",
        side_effect=Exception,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_REAUTH, "entry_id": "reauth_bad"},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: FAKE_KEY},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_zeroconf_creates_entry(hass):
    """A zeroconf discovery creates a config entry."""
    with patch(
        "custom_components.moonraker.MoonrakerApiClient.start",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=MagicZeroconfInfo(host="1.2.3.4", port=7125),
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "mainsail"
    assert result["data"][CONF_URL] == "1.2.3.4"


class MagicZeroconfInfo:
    """Minimal discovery info stand-in."""

    def __init__(self, host, port):
        """Initialize the discovery info stand-in."""
        self.host = host
        self.port = port
        self.hostname = "mainsail"


@pytest.mark.usefixtures("bypass_connect_client")
async def test_invalid_auth_config_flow(hass):
    """An authentication failure surfaces invalid_auth to the user."""
    from custom_components.moonraker.config_flow import InvalidAuth

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.moonraker.config_flow.MoonrakerConfigFlow._async_test_connection",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_CONFIG
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_invalid_auth_shows_error(hass):
    """Reauth with a rejected key shows invalid_auth."""
    from custom_components.moonraker.config_flow import InvalidAuth

    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="reauth_bad_auth")
    entry.add_to_hass(hass)

    with patch(
        "custom_components.moonraker.config_flow.MoonrakerConfigFlow._async_test_connection",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": "reauth_bad_auth",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: FAKE_KEY},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_zeroconf_invalid_host_aborts(hass):
    """A zeroconf discovery with an invalid host aborts."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=MagicZeroconfInfo(host="1.2.3", port=7125),
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "invalid_host"


async def test_zeroconf_connection_failure_aborts(hass):
    """A zeroconf discovery that cannot be reached aborts."""
    from custom_components.moonraker.config_flow import CannotConnect

    with patch(
        "custom_components.moonraker.config_flow.MoonrakerConfigFlow._async_test_connection",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=MagicZeroconfInfo(host="1.2.3.4", port=7125),
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


@pytest.mark.usefixtures("bypass_connect_client")
async def test_async_test_connection_raises_invalid_auth(hass):
    """A rejected API key surfaces as InvalidAuth."""
    from custom_components.moonraker.config_flow import (
        InvalidAuth,
        MoonrakerConfigFlow,
    )
    from moonraker_api import ClientNotAuthenticatedError

    flow = MoonrakerConfigFlow()
    flow.hass = hass

    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=ClientNotAuthenticatedError,
        ),
        pytest.raises(InvalidAuth),
    ):
        await flow._async_test_connection(MOCK_CONFIG)


@pytest.mark.usefixtures("bypass_connect_client")
async def test_async_test_connection_raises_cannot_connect_without_identifier(hass):
    """A response without uuid or hostname surfaces as CannotConnect."""
    from custom_components.moonraker.config_flow import (
        CannotConnect,
        MoonrakerConfigFlow,
    )

    flow = MoonrakerConfigFlow()
    flow.hass = hass

    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            return_value={"state": "ready"},
        ),
        pytest.raises(CannotConnect),
    ):
        await flow._async_test_connection(MOCK_CONFIG)


@pytest.mark.usefixtures("bypass_connect_client")
async def test_reconfigure_updates_entry(hass):
    """Reconfiguring an entry updates its data and reloads it."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="reconf")
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": "reconf"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    new_config = {**MOCK_CONFIG, CONF_PORT: "7777"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=new_config
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PORT] == "7777"


@pytest.mark.usefixtures("bypass_connect_client")
async def test_reconfigure_invalid_port_shows_error(hass):
    """Reconfiguring with an invalid port shows a field error."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="reconf2")
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": "reconf2"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={**MOCK_CONFIG, CONF_PORT: "99999"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_PORT: "port_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_reconfigure_invalid_host_shows_error(hass):
    """Reconfiguring with an invalid host shows a field error."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="rch")
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": "rch"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={**MOCK_CONFIG, CONF_URL: "http://bad"}
    )
    assert result["errors"] == {CONF_URL: "host_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_reconfigure_invalid_api_key_shows_error(hass):
    """Reconfiguring with a malformed API key shows a field error."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="rck")
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": "rck"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={**MOCK_CONFIG, CONF_API_KEY: "short"}
    )
    assert result["errors"] == {CONF_API_KEY: "api_key_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_reconfigure_invalid_printer_name_shows_error(hass):
    """Reconfiguring with an invalid printer name shows a field error."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="rcn")
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": "rcn"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={**MOCK_CONFIG, CONF_PRINTER_NAME: "unknown"}
    )
    assert result["errors"] == {CONF_PRINTER_NAME: "printer_name_error"}


@pytest.mark.usefixtures("error_connect_client")
async def test_reconfigure_cannot_connect_shows_error(hass):
    """Reconfiguring when the printer is unreachable shows cannot_connect."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="rcc")
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": "rcc"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_CONFIG
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reconfigure_invalid_auth_shows_error(hass):
    """Reconfiguring with a rejected API key shows invalid_auth."""
    from custom_components.moonraker.config_flow import InvalidAuth

    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="rci")
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": "rci"}
    )
    with patch(
        "custom_components.moonraker.config_flow.MoonrakerConfigFlow._async_test_connection",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_CONFIG
        )
    assert result["errors"] == {"base": "invalid_auth"}
