"""Tests for the schedule store."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.chauffage_intelligent.storage import DATA_SCHEDULES, ScheduleStore


@pytest.fixture
def store(mock_hass):
    """A store whose underlying HA Store is mocked out."""
    with patch("custom_components.chauffage_intelligent.storage.Store") as store_cls:
        instance = store_cls.return_value
        instance.async_load = AsyncMock(return_value=None)
        instance.async_save = AsyncMock()
        schedule_store = ScheduleStore(mock_hass)
        schedule_store.backend = instance
        yield schedule_store


async def test_load_empty_storage(store):
    """A fresh install starts with no schedules."""
    await store.async_load()

    assert store.all() == {}
    assert store.get("bureau") == []
    assert store.has("bureau") is False


async def test_load_normalizes_stored_slots(store):
    """Slots read back from disk are normalized."""
    store.backend.async_load.return_value = {
        DATA_SCHEDULES: {
            "bureau": [
                {"day": 0, "start": "07:00", "end": "09:00", "temperature": 20},
                {"day": 0, "start": "09:00", "end": "11:00", "temperature": 20},
            ]
        }
    }

    await store.async_load()

    assert store.get("bureau") == [
        {"day": 0, "start": "07:00", "end": "11:00", "temperature": 20.0}
    ]


async def test_load_discards_a_corrupt_schedule(store):
    """A room whose stored planning is unreadable starts empty instead of failing."""
    store.backend.async_load.return_value = {
        DATA_SCHEDULES: {
            "bureau": [{"day": 99, "start": "07:00", "end": "09:00", "temperature": 20}],
            "salon": [{"day": 1, "start": "08:00", "end": "09:00", "temperature": 20}],
        }
    }

    await store.async_load()

    assert store.get("bureau") == []
    assert len(store.get("salon")) == 1


async def test_set_persists(store):
    """Saving a schedule writes it out."""
    await store.async_load()

    slots = await store.async_set(
        "bureau", [{"day": 0, "start": "07:00", "end": "09:00", "temperature": 20}]
    )

    assert slots == [{"day": 0, "start": "07:00", "end": "09:00", "temperature": 20.0}]
    store.backend.async_save.assert_awaited_once_with(
        {DATA_SCHEDULES: {"bureau": slots}}
    )


async def test_remove(store):
    """Removing a room's schedule persists the deletion."""
    await store.async_load()
    await store.async_set("bureau", [{"day": 0, "start": "07:00", "end": "09:00",
                                     "temperature": 20}])
    store.backend.async_save.reset_mock()

    await store.async_remove("bureau")

    assert store.has("bureau") is False
    store.backend.async_save.assert_awaited_once()


async def test_remove_unknown_room_does_not_write(store):
    """Removing something that was never stored writes nothing."""
    await store.async_load()

    await store.async_remove("cave")

    store.backend.async_save.assert_not_awaited()


async def test_prune_drops_stale_rooms(store):
    """Schedules of deleted rooms are cleaned up."""
    await store.async_load()
    await store.async_set("bureau", [])
    await store.async_set("cave", [])
    store.backend.async_save.reset_mock()

    await store.async_prune({"bureau"})

    assert set(store.all()) == {"bureau"}
    store.backend.async_save.assert_awaited_once()


async def test_prune_without_stale_rooms_does_not_write(store):
    """Nothing to prune means no disk write."""
    await store.async_load()
    await store.async_set("bureau", [])
    store.backend.async_save.reset_mock()

    await store.async_prune({"bureau"})

    store.backend.async_save.assert_not_awaited()
