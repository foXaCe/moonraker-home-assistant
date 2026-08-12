"""Tests for the batched discovery query."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.const import DOMAIN, METHODS, OBJ
from custom_components.moonraker.coordinator import MoonrakerDataUpdateCoordinator

from .const import MOCK_CONFIG


def _coordinator(hass):
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, unique_id="batch-uuid", entry_id="batch"
    )
    config_entry.add_to_hass(hass)
    return MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )


async def test_nothing_to_discover_makes_no_request(hass):
    """An empty request never reaches the printer."""
    coordinator = _coordinator(hass)

    with patch.object(coordinator, "async_fetch_data", new_callable=AsyncMock) as fetch:
        assert await coordinator.async_discover_objects({}) == {}

    fetch.assert_not_awaited()


async def test_concurrent_callers_share_one_request(hass):
    """Builders started together are merged into a single query."""
    coordinator = _coordinator(hass)
    queries = []

    async def _fetch(_method, query_obj=None, **_kwargs):
        queries.append(query_obj)
        return {"status": {"fan": {"rpm": 10}, "bme280 x": {"temperature": 20}}}

    with patch.object(coordinator, "async_fetch_data", _fetch):
        first, second = await asyncio.gather(
            coordinator.async_discover_objects({"fan": ["rpm"]}),
            coordinator.async_discover_objects({"bme280 x": None}),
        )

    assert len(queries) == 1, f"expected one batched query, got {queries}"
    assert queries[0] == {OBJ: {"fan": ["rpm"], "bme280 x": None}}
    assert first == second
    assert first["fan"]["rpm"] == 10


async def test_field_lists_are_merged(hass):
    """Two callers wanting different fields of one object get both."""
    coordinator = _coordinator(hass)
    queries = []

    async def _fetch(_method, query_obj=None, **_kwargs):
        queries.append(query_obj)
        return {"status": {}}

    with patch.object(coordinator, "async_fetch_data", _fetch):
        await asyncio.gather(
            coordinator.async_discover_objects({"fan": ["rpm"]}),
            coordinator.async_discover_objects({"fan": ["speed"]}),
        )

    assert queries[0] == {OBJ: {"fan": ["rpm", "speed"]}}


async def test_all_fields_wins_over_a_field_list(hass):
    """Asking for the whole object supersedes a narrower request."""
    coordinator = _coordinator(hass)
    queries = []

    async def _fetch(_method, query_obj=None, **_kwargs):
        queries.append(query_obj)
        return {"status": {}}

    with patch.object(coordinator, "async_fetch_data", _fetch):
        await asyncio.gather(
            coordinator.async_discover_objects({"fan": None}),
            coordinator.async_discover_objects({"fan": ["rpm"]}),
        )

    assert queries[0] == {OBJ: {"fan": None}}


async def test_later_caller_gets_its_own_request(hass):
    """A builder arriving after the batch left issues its own query."""
    coordinator = _coordinator(hass)
    queries = []

    async def _fetch(_method, query_obj=None, **_kwargs):
        queries.append(query_obj)
        return {"status": {}}

    with patch.object(coordinator, "async_fetch_data", _fetch):
        await coordinator.async_discover_objects({"fan": ["rpm"]})
        await coordinator.async_discover_objects({"bme280 x": None})

    assert len(queries) == 2
    assert coordinator._discovery_batch == {}


async def test_batch_uses_the_objects_query_method(hass):
    """The batch goes out as printer.objects.query."""
    coordinator = _coordinator(hass)

    with patch.object(
        coordinator, "async_fetch_data", new_callable=AsyncMock, return_value={}
    ) as fetch:
        assert await coordinator.async_discover_objects({"fan": ["rpm"]}) == {}

    assert fetch.await_args.args[0] == METHODS.PRINTER_OBJECTS_QUERY
