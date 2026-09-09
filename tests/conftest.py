"""Pytest fixtures for Chauffage Intelligent tests."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.chauffage_intelligent.const import (
    CONF_PIECE_AREA_ID,
    CONF_PIECE_NAME,
    CONF_PIECE_OFFSET,
    CONF_PIECE_RADIATEURS,
    CONF_PIECE_SONDE,
    CONF_PIECE_TEMPERATURES,
    CONF_PIECE_TYPE,
    CONF_PIECES,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    TEMP_CONFORT,
    TEMP_ECO,
    TEMP_HORS_GEL,
)
from custom_components.chauffage_intelligent.coordinator import (
    ChauffageIntelligentCoordinator,
)


class FakeState:
    """Minimal stand-in for a Home Assistant State."""

    def __init__(self, state: str, attributes: dict[str, Any] | None = None) -> None:
        """Initialize the fake state."""
        self.state = state
        self.attributes = attributes or {}


class FakeScheduleStore:
    """In-memory replacement for ScheduleStore."""

    def __init__(self, schedules: dict[str, list[dict[str, Any]]] | None = None) -> None:
        """Initialize with optional pre-seeded schedules."""
        from custom_components.chauffage_intelligent.schedule import normalize_slots

        self._normalize = normalize_slots
        self._schedules = {
            piece_id: normalize_slots(slots) for piece_id, slots in (schedules or {}).items()
        }
        self.saved = 0

    def get(self, piece_id: str) -> list[dict[str, Any]]:
        """Return a room's schedule."""
        return self._schedules.get(piece_id, [])

    def has(self, piece_id: str) -> bool:
        """Return True if a schedule exists."""
        return piece_id in self._schedules

    def all(self) -> dict[str, list[dict[str, Any]]]:
        """Return every schedule."""
        return dict(self._schedules)

    async def async_set(
        self, piece_id: str, slots: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Store a normalized schedule."""
        normalized = self._normalize(slots)
        self._schedules[piece_id] = normalized
        self.saved += 1
        return normalized

    async def async_remove(self, piece_id: str) -> None:
        """Drop a schedule."""
        self._schedules.pop(piece_id, None)


@pytest.fixture
def mock_hass(tmp_path):
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.states = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    # Close the coroutine we are handed so tests do not emit 'never awaited'.
    hass.async_create_task = MagicMock(side_effect=lambda coro, *a, **k: coro.close())
    # The coordinator's debouncer would try to await a MagicMock; returning None
    # keeps async_request_refresh a no-op in these unit tests.
    hass.async_run_hass_job = MagicMock(return_value=None)
    hass.config.path.return_value = str(tmp_path / ".storage")
    return hass


@pytest.fixture
def basic_config():
    """Create a basic configuration with two rooms."""
    return {
        CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
        CONF_PIECES: {
            "bureau": {
                CONF_PIECE_NAME: "Bureau",
                CONF_PIECE_AREA_ID: "bureau",
                CONF_PIECE_TYPE: "bureau",
                CONF_PIECE_RADIATEURS: ["climate.bilbao_bureau"],
                CONF_PIECE_SONDE: "sensor.temperature_bureau",
                CONF_PIECE_TEMPERATURES: {
                    TEMP_CONFORT: 19,
                    TEMP_ECO: 17,
                    TEMP_HORS_GEL: 7,
                },
                CONF_PIECE_OFFSET: 0.0,
            },
            "salon": {
                CONF_PIECE_NAME: "Salon",
                CONF_PIECE_AREA_ID: "salon",
                CONF_PIECE_TYPE: "salon",
                CONF_PIECE_RADIATEURS: ["climate.bilbao_salon"],
                CONF_PIECE_SONDE: "sensor.temperature_salon",
                CONF_PIECE_TEMPERATURES: {
                    TEMP_CONFORT: 20,
                    TEMP_ECO: 17,
                    TEMP_HORS_GEL: 7,
                },
                CONF_PIECE_OFFSET: 0.0,
            },
        },
    }


@pytest.fixture
def schedules():
    """A weekday morning comfort slot for the office."""
    return {
        "bureau": [
            {"day": day, "start": "07:00", "end": "09:00", "temperature": 19.0}
            for day in range(5)
        ],
        "salon": [],
    }


@pytest.fixture
def store(schedules):
    """An in-memory schedule store."""
    return FakeScheduleStore(schedules)


@pytest.fixture
def coordinator(mock_hass, basic_config, store):
    """A coordinator wired to the mock hass and in-memory store."""
    return ChauffageIntelligentCoordinator(
        mock_hass,
        basic_config,
        store,
        update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
    )


@pytest.fixture
def radiator_state():
    """Factory building a plausible radiator state."""

    def _build(
        temperature: float | None = 17.0,
        state: str = "heat",
        current_temperature: float = 18.0,
        min_temp: float = 7.0,
        max_temp: float = 30.0,
    ) -> FakeState:
        return FakeState(
            state,
            {
                "temperature": temperature,
                "current_temperature": current_temperature,
                "min_temp": min_temp,
                "max_temp": max_temp,
            },
        )

    return _build


@pytest.fixture
def hass_with_coordinator(mock_hass, coordinator):
    """A hass whose data holds a coordinator under a fake entry id."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    mock_hass.data = {"chauffage_intelligent": {"test_entry": coordinator}}
    return mock_hass, entry, coordinator
