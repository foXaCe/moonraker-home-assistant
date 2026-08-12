"""Guard the number of API round-trips performed during a config entry setup.

Setup latency on a real printer is dominated by serialized JSON-RPC round-trips,
so the call count is the metric worth protecting against regressions. Run with
``-s`` to print the full profile:

    pytest tests/test_boot_perf.py -s
"""

import asyncio
import time
from collections import Counter
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.moonraker.const import DOMAIN, METHODS
from custom_components.moonraker.coordinator import (
    SLOW_UPDATER_TTL,
    MoonrakerDataUpdateCoordinator,
)

from .const import MOCK_CONFIG

# Budget for a full setup against the reference printer fixture. Lowering it is
# always welcome; raising it means setup got slower for every user. One call of
# the budget is printer.objects.subscribe, which buys push updates afterwards.
MAX_SETUP_CALLS = 18

# No method should be queried more than this during a single setup.
MAX_CALLS_PER_METHOD = 5


@pytest.mark.asyncio
async def test_setup_stays_within_api_call_budget(hass, get_default_api_response):
    """A full setup must stay within its round-trip budget."""
    calls: Counter[str] = Counter()

    async def _counting_call_method(_self, method, **_kwargs):
        calls[method] += 1
        return get_default_api_response

    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="boot_perf")
    entry.add_to_hass(hass)

    with (
        patch("moonraker_api.MoonrakerClient.call_method", _counting_call_method),
        patch("custom_components.moonraker.MoonrakerApiClient.start"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    profile = "\n".join(f"  {n:>3}x  {m}" for m, n in calls.most_common())
    total = sum(calls.values())

    # Unload before asserting: a loaded entry left behind by a failing assert
    # would leak its polling into the next test.
    await hass.config_entries.async_unload(entry.entry_id)

    assert total <= MAX_SETUP_CALLS, (
        f"setup made {total} API calls (budget {MAX_SETUP_CALLS}):\n{profile}"
    )
    for method, count in calls.items():
        assert count <= MAX_CALLS_PER_METHOD, (
            f"{method} queried {count} times during setup:\n{profile}"
        )


@pytest.mark.asyncio
async def test_gcode_metadata_is_cached_per_file(hass, get_default_api_response):
    """Metadata of the printing file is fetched once, not on every refresh."""
    calls: Counter[str] = Counter()

    async def _counting_call_method(_self, method, **_kwargs):
        calls[method] += 1
        return get_default_api_response

    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="gcode_cache")
    entry.add_to_hass(hass)

    with (
        patch("moonraker_api.MoonrakerClient.call_method", _counting_call_method),
        patch("custom_components.moonraker.MoonrakerApiClient.start"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        before = calls["server.files.metadata"]
        coordinator = entry.runtime_data.coordinator
        await coordinator.async_refresh()
        await coordinator.async_refresh()

    assert calls["server.files.metadata"] == before

    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.asyncio
async def test_seeded_updaters_refresh_after_ttl(hass, get_default_api_response):
    """Data seeded at setup is refreshed again once its TTL expires."""
    calls: Counter[str] = Counter()

    async def _counting_call_method(_self, method, **_kwargs):
        calls[method] += 1
        return get_default_api_response

    slow_methods = (
        "server.history.totals",
        "server.job_queue.status",
        "server.spoolman.status",
        "machine.update.status",
        "machine.device_power.devices",
        "machine.system_info",
    )

    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="ttl")
    entry.add_to_hass(hass)

    with (
        patch("moonraker_api.MoonrakerClient.call_method", _counting_call_method),
        patch("custom_components.moonraker.MoonrakerApiClient.start"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Within the TTL window nothing slow is polled again.
        calls.clear()
        await entry.runtime_data.coordinator.async_refresh()
        assert [m for m in slow_methods if calls[m]] == []

        # Past the TTL every slow endpoint is polled once more.
        calls.clear()
        with patch(
            "custom_components.moonraker.coordinator.time.monotonic",
            return_value=time.monotonic() + SLOW_UPDATER_TTL + 1,
        ):
            await entry.runtime_data.coordinator.async_refresh()

    for method in slow_methods:
        assert calls[method] == 1, f"{method} polled {calls[method]}x after its TTL"

    await hass.config_entries.async_unload(entry.entry_id)


async def test_seed_on_coordinator_without_data(hass):
    """Seeding a coordinator that never completed a refresh creates its data."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="seed"
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )

    async def _updater(_coordinator):
        return {}

    assert coordinator.data is None
    coordinator.add_data_updater(_updater, ttl=SLOW_UPDATER_TTL, seed={"history": {}})

    assert coordinator.data == {"history": {}}


async def test_shared_fetch_is_issued_once(hass, get_default_api_response):
    """Concurrent callers of a shared endpoint trigger a single request."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="shared"
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )

    calls = 0

    async def _fetch(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return get_default_api_response

    with patch.object(coordinator, "async_fetch_data", _fetch):
        first, second = await asyncio.gather(
            coordinator.async_fetch_shared(METHODS.MACHINE_SYSTEM_INFO),
            coordinator.async_fetch_shared(METHODS.MACHINE_SYSTEM_INFO),
        )
        assert first == second
        assert calls == 1

        # Still cached within the TTL, fetched again once it expires.
        await coordinator.async_fetch_shared(METHODS.MACHINE_SYSTEM_INFO)
        assert calls == 1

        with patch(
            "custom_components.moonraker.coordinator.time.monotonic",
            return_value=time.monotonic() + SLOW_UPDATER_TTL + 1,
        ):
            await coordinator.async_fetch_shared(METHODS.MACHINE_SYSTEM_INFO)
        assert calls == 2


async def test_shared_fetch_failure_is_not_cached(hass):
    """A failed shared fetch must not be replayed for the whole TTL."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="shared_fail"
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )

    async def _failing(*_args, **_kwargs):
        raise UpdateFailed

    with (
        patch.object(coordinator, "async_fetch_data", _failing),
        pytest.raises(UpdateFailed),
    ):
        await coordinator.async_fetch_shared(METHODS.MACHINE_SYSTEM_INFO)

    assert coordinator._shared_fetches == {}


async def test_fetch_or_none_swallows_update_failure(hass):
    """The discovery cache tolerates an endpoint the printer cannot answer."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="test-uuid", entry_id="fetch_or_none"
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )

    async def _failing(*_args, **_kwargs):
        raise UpdateFailed

    with patch.object(coordinator, "_async_fetch_data", _failing):
        assert (
            await coordinator._fetch_or_none(METHODS.PRINTER_OBJECTS_LIST, None) is None
        )
