"""Persistent storage for Chauffage Intelligent schedules.

Schedules live outside the config entry: they are edited frequently from the
panel and we do not want every save to reload the integration.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .schedule import normalize_slots

_LOGGER = logging.getLogger(__name__)

DATA_SCHEDULES = "schedules"


class ScheduleStore:
    """Read/write access to the per-room weekly schedules."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store."""
        self.backend: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._schedules: dict[str, list[dict[str, Any]]] = {}
        self._loaded = False

    async def async_load(self) -> None:
        """Load schedules from disk."""
        data = await self.backend.async_load() or {}
        raw = data.get(DATA_SCHEDULES, {})

        schedules: dict[str, list[dict[str, Any]]] = {}
        for piece_id, slots in raw.items():
            try:
                schedules[piece_id] = normalize_slots(slots)
            except ValueError as err:
                _LOGGER.warning("Discarding invalid schedule for %s: %s", piece_id, err)
                schedules[piece_id] = []

        self._schedules = schedules
        self._loaded = True

    async def async_save(self) -> None:
        """Persist schedules to disk."""
        await self.backend.async_save({DATA_SCHEDULES: self._schedules})

    def get(self, piece_id: str) -> list[dict[str, Any]]:
        """Return the schedule for a room (empty list if unset)."""
        return self._schedules.get(piece_id, [])

    def has(self, piece_id: str) -> bool:
        """Return True if a schedule is stored for this room."""
        return piece_id in self._schedules

    def all(self) -> dict[str, list[dict[str, Any]]]:
        """Return every stored schedule."""
        return dict(self._schedules)

    async def async_set(self, piece_id: str, slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize, store and persist a room schedule. Returns the stored slots."""
        normalized = normalize_slots(slots)
        self._schedules[piece_id] = normalized
        await self.async_save()
        return normalized

    async def async_remove(self, piece_id: str) -> None:
        """Drop the schedule of a removed room."""
        if self._schedules.pop(piece_id, None) is not None:
            await self.async_save()

    async def async_prune(self, known_piece_ids: set[str]) -> None:
        """Drop schedules belonging to rooms that no longer exist."""
        stale = set(self._schedules) - known_piece_ids
        if stale:
            for piece_id in stale:
                del self._schedules[piece_id]
            await self.async_save()
