"""API Tests."""

from unittest.mock import patch

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.moonraker.api import MoonrakerApiClient


async def test_connect_client():
    """Test connect client."""
    with (
        patch("moonraker_api.MoonrakerClient"),
        patch("moonraker_api.websockets.websocketclient.WebsocketClient.connect"),
        patch("moonraker_api.websockets.websocketclient.WebsocketClient.disconnect"),
    ):
        moonraker_api = MoonrakerApiClient("notaURL", None, port=7125, api_key="1dd2")
        assert not moonraker_api.running
        await moonraker_api.start()
        assert moonraker_api.running
        await moonraker_api.stop()
        assert not moonraker_api.running


async def test_none_port_connect_client():
    """Test connect client."""
    with (
        patch("moonraker_api.MoonrakerClient"),
        patch("moonraker_api.websockets.websocketclient.WebsocketClient.connect"),
        patch("moonraker_api.websockets.websocketclient.WebsocketClient.disconnect"),
    ):
        moonraker_api = MoonrakerApiClient("notaURL", None, port=7125, api_key="1dd2")
        assert not moonraker_api.running
        await moonraker_api.start()
        assert moonraker_api.running
        await moonraker_api.stop()
        assert not moonraker_api.running


async def test_on_notification_forwards_to_callback(hass):
    """Websocket notifications reach the registered callback."""
    client = MoonrakerApiClient("1.2.3.4", async_get_clientsession(hass))
    received = []

    client.set_notification_callback(
        lambda method, data: received.append((method, data))
    )
    await client.on_notification("notify_status_update", [{"fan": {"speed": 1}}, 12.0])

    assert received == [("notify_status_update", [{"fan": {"speed": 1}}, 12.0])]


async def test_on_notification_without_callback_is_a_noop(hass):
    """A notification arriving before any subscription is simply dropped."""
    client = MoonrakerApiClient("1.2.3.4", async_get_clientsession(hass))

    await client.on_notification("notify_status_update", [{}, 1.0])
