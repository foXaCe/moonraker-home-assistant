"""Tests for the websocket push subscription."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.const import (
    CONF_OPTION_POLLING_RATE,
    DOMAIN,
    METHODS,
    OBJ,
)
from custom_components.moonraker.coordinator import (
    NOTIFY_STATUS_UPDATE,
    SAFETY_NET_INTERVAL,
    MoonrakerDataUpdateCoordinator,
)

from .const import MOCK_CONFIG


def _coordinator(hass):
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="push-uuid", entry_id="push"
    )
    config_entry.add_to_hass(hass)
    return MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )


async def test_subscribe_without_objects_does_nothing(hass):
    """Nothing is subscribed while no entity has registered an object."""
    coordinator = _coordinator(hass)

    await coordinator.async_subscribe_objects()

    coordinator.moonraker.set_notification_callback.assert_not_called()


async def test_subscribe_seeds_initial_status(hass):
    """The subscription reply seeds the status without an extra query."""
    coordinator = _coordinator(hass)
    coordinator.add_query_objects("fan", "speed")

    with patch.object(
        coordinator,
        "_async_fetch_data",
        new_callable=AsyncMock,
        return_value={"status": {"fan": {"speed": 0.5}}},
    ) as fetch:
        await coordinator.async_subscribe_objects()

    fetch.assert_awaited_once_with(
        METHODS.PRINTER_OBJECTS_SUBSCRIBE, coordinator.query_obj
    )
    assert coordinator.data["status"]["fan"]["speed"] == 0.5
    coordinator.moonraker.set_notification_callback.assert_called_once()


@pytest.mark.parametrize("error", [UpdateFailed, ConfigEntryAuthFailed])
async def test_subscribe_failure_falls_back_to_polling(hass, error):
    """A printer that refuses the subscription keeps working by polling."""
    coordinator = _coordinator(hass)
    coordinator.add_query_objects("fan", "speed")

    with patch.object(
        coordinator, "_async_fetch_data", new_callable=AsyncMock, side_effect=error
    ):
        await coordinator.async_subscribe_objects()

    # The callback is registered then withdrawn, leaving no push wiring behind.
    coordinator.moonraker.set_notification_callback.assert_called_with(None)


async def test_notification_merges_into_existing_status(hass):
    """A pushed change updates one field without dropping the others."""
    coordinator = _coordinator(hass)
    coordinator.data = {
        "status": {"fan": {"speed": 0.1, "rpm": 900}, "print_stats": {"state": "idle"}}
    }

    coordinator._handle_notification(
        NOTIFY_STATUS_UPDATE, [{"fan": {"speed": 0.8}}, 1.0]
    )

    assert coordinator.data["status"]["fan"] == {"speed": 0.8, "rpm": 900}
    assert coordinator.data["status"]["print_stats"] == {"state": "idle"}


async def test_notification_adds_unknown_object(hass):
    """An object that was not in the data yet is added as-is."""
    coordinator = _coordinator(hass)
    coordinator.data = {"status": {}}

    coordinator._handle_notification(
        NOTIFY_STATUS_UPDATE, [{"toolhead": "homing"}, 1.0]
    )

    assert coordinator.data["status"]["toolhead"] == "homing"


@pytest.mark.parametrize(
    ("method", "payload"),
    [
        ("notify_gcode_response", [{"fan": {"speed": 1}}, 1.0]),
        (NOTIFY_STATUS_UPDATE, "not-a-list"),
        (NOTIFY_STATUS_UPDATE, []),
        (NOTIFY_STATUS_UPDATE, [None, 1.0]),
        (NOTIFY_STATUS_UPDATE, [{}, 1.0]),
    ],
)
async def test_irrelevant_notifications_are_ignored(hass, method, payload):
    """Only a non-empty status payload is applied."""
    coordinator = _coordinator(hass)
    coordinator.data = {"status": {"fan": {"speed": 0.1}}}

    coordinator._handle_notification(method, payload)

    assert coordinator.data["status"] == {"fan": {"speed": 0.1}}


async def test_query_obj_is_sent_on_subscribe(hass):
    """The subscription covers exactly the objects the entities registered."""
    coordinator = _coordinator(hass)
    coordinator.add_query_objects("fan", "speed")
    coordinator.add_query_objects("print_stats", "state")

    assert coordinator.query_obj[OBJ] == {"fan": ["speed"], "print_stats": ["state"]}


async def test_polling_backs_off_once_subscribed(hass):
    """Polling becomes a safety net as soon as the subscription is active."""
    coordinator = _coordinator(hass)
    coordinator.add_query_objects("fan", "speed")

    assert coordinator._target_interval(None) == timedelta(seconds=30)
    assert coordinator._target_interval("printing") == timedelta(seconds=2)

    with patch.object(
        coordinator, "_async_fetch_data", new_callable=AsyncMock, return_value={}
    ):
        await coordinator.async_subscribe_objects()

    # No more 2 s cadence while printing: Moonraker pushes those changes now.
    assert coordinator.update_interval == SAFETY_NET_INTERVAL
    assert coordinator._target_interval("printing") == SAFETY_NET_INTERVAL


async def test_longer_configured_rate_is_kept(hass):
    """A user asking for an even slower poll keeps their setting."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="slow-uuid",
        entry_id="slow",
        options={CONF_OPTION_POLLING_RATE: 900},
    )
    config_entry.add_to_hass(hass)
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )
    coordinator._subscribed = True

    assert coordinator._target_interval(None) == timedelta(seconds=900)


async def test_out_of_band_events_trigger_a_refresh(hass):
    """An event the subscription does not carry re-reads the slow endpoints."""
    coordinator = _coordinator(hass)
    coordinator._updater_times = {"some_updater": 123.0}

    with patch.object(
        coordinator, "async_request_refresh", new_callable=AsyncMock
    ) as refresh:
        coordinator._handle_notification("notify_power_changed", [{"device": "psu"}])
        await hass.async_block_till_done()

    assert coordinator._updater_times == {}
    refresh.assert_awaited_once()


async def test_subscription_is_restored_after_reconnect(hass):
    """A replaced websocket session gets its subscription back."""
    coordinator = _coordinator(hass)
    coordinator.add_query_objects("fan", "speed")
    coordinator.moonraker.connection_epoch = 1

    with patch.object(
        coordinator, "_async_fetch_data", new_callable=AsyncMock, return_value={}
    ) as fetch:
        await coordinator.async_subscribe_objects()
        assert coordinator._subscribed is True

        # Same session: nothing to redo.
        await coordinator._async_resubscribe_if_reconnected()
        assert fetch.await_count == 1

        # The client reconnected, so Moonraker dropped the subscription.
        coordinator.moonraker.connection_epoch = 2
        await coordinator._async_resubscribe_if_reconnected()

    assert fetch.await_count == 2
    assert coordinator._subscription_epoch == 2


async def test_no_resubscribe_when_never_subscribed(hass):
    """Polling-only setups are left alone."""
    coordinator = _coordinator(hass)
    coordinator.moonraker.connection_epoch = 5

    with patch.object(
        coordinator, "_async_fetch_data", new_callable=AsyncMock
    ) as fetch:
        await coordinator._async_resubscribe_if_reconnected()

    fetch.assert_not_awaited()


async def test_failed_optional_fetch_marks_discovery_degraded(hass):
    """An endpoint that could not answer flags the discovery as incomplete."""
    coordinator = _coordinator(hass)
    assert coordinator.discovery_degraded is False

    async def _failing(*_args, **_kwargs):
        raise UpdateFailed

    with patch.object(coordinator, "_async_fetch_data", _failing):
        assert (
            await coordinator.async_fetch_data(
                METHODS.SERVER_SPOOLMAN_ID, offline_ok=True
            )
            == {}
        )

    assert coordinator.discovery_degraded is True


async def test_error_payload_marks_discovery_degraded(hass):
    """Moonraker answering an error in-band counts as a failed discovery."""
    coordinator = _coordinator(hass)

    async def _error(*_args, **_kwargs):
        return {"error": {"code": -32601, "message": "Method not found"}}

    with patch.object(coordinator, "_async_fetch_data", _error):
        await coordinator.async_fetch_data(
            METHODS.MACHINE_UPDATE_STATUS, offline_ok=True
        )

    assert coordinator.discovery_degraded is True
