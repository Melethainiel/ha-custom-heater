"""Pytest fixtures for Chauffage Intelligent tests."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.chauffage_intelligent.const import (
    CONF_CALENDAR,
    CONF_DERIVATIVE_WINDOW,
    CONF_MIN_PREHEAT_TIME,
    CONF_PIECE_NAME,
    CONF_PIECE_RADIATEUR,
    CONF_PIECE_SONDE,
    CONF_PIECE_TEMPERATURES,
    CONF_PIECE_TYPE,
    CONF_PIECES,
    CONF_PRESENCE_TRACKERS,
    CONF_SECURITY_FACTOR,
    DEFAULT_DERIVATIVE_WINDOW,
    DEFAULT_MIN_PREHEAT_TIME,
    DEFAULT_SECURITY_FACTOR,
    MODE_CONFORT,
    MODE_ECO,
    MODE_HORS_GEL,
)
from custom_components.chauffage_intelligent.coordinator import (
    ChauffageIntelligentCoordinator,
)


@pytest.fixture
def mock_hass(tmp_path):
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.states = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    # Mock config path for learner storage
    hass.config.path.return_value = str(tmp_path / ".storage")
    return hass


@pytest.fixture
def basic_config():
    """Create a basic configuration."""
    return {
        CONF_CALENDAR: "calendar.google_home",
        CONF_PRESENCE_TRACKERS: ["device_tracker.phone_1", "device_tracker.phone_2"],
        CONF_PIECES: {
            "bureau": {
                CONF_PIECE_NAME: "Bureau",
                CONF_PIECE_TYPE: "bureau",
                CONF_PIECE_RADIATEUR: "climate.bilbao_bureau",
                CONF_PIECE_SONDE: "sensor.temperature_bureau",
                CONF_PIECE_TEMPERATURES: {
                    MODE_CONFORT: 19,
                    MODE_ECO: 17,
                    MODE_HORS_GEL: 7,
                },
            },
            "salon": {
                CONF_PIECE_NAME: "Salon",
                CONF_PIECE_TYPE: "salon",
                CONF_PIECE_RADIATEUR: "climate.bilbao_salon",
                CONF_PIECE_SONDE: "sensor.temperature_salon",
                CONF_PIECE_TEMPERATURES: {
                    MODE_CONFORT: 20,
                    MODE_ECO: 17,
                    MODE_HORS_GEL: 7,
                },
            },
            "chambre": {
                CONF_PIECE_NAME: "Chambre",
                CONF_PIECE_TYPE: "chambre",
                CONF_PIECE_RADIATEUR: "climate.bilbao_chambre",
                CONF_PIECE_SONDE: "sensor.temperature_chambre",
                CONF_PIECE_TEMPERATURES: {
                    MODE_CONFORT: 18,
                    MODE_ECO: 16,
                    MODE_HORS_GEL: 7,
                },
            },
        },
        CONF_SECURITY_FACTOR: DEFAULT_SECURITY_FACTOR,
        CONF_MIN_PREHEAT_TIME: DEFAULT_MIN_PREHEAT_TIME,
        CONF_DERIVATIVE_WINDOW: DEFAULT_DERIVATIVE_WINDOW,
    }


@pytest.fixture
def coordinator(mock_hass, basic_config):
    """Create a coordinator instance for testing."""
    with patch.object(
        ChauffageIntelligentCoordinator,
        "_async_update_data",
        new_callable=AsyncMock,
    ):
        coord = ChauffageIntelligentCoordinator(
            mock_hass,
            basic_config,
            update_interval=timedelta(minutes=5),
        )
        return coord


@pytest.fixture
def mock_state():
    """Create a factory for mock states."""
    def _create_state(state: str, attributes: dict[str, Any] | None = None):
        mock = MagicMock()
        mock.state = state
        mock.attributes = attributes or {}
        return mock
    return _create_state


@pytest.fixture
def calendar_event_factory():
    """Create a factory for calendar events."""
    def _create_event(
        summary: str,
        start: datetime | None = None,
        end: datetime | None = None,
        offset_minutes: int = 0,
        duration_minutes: int = 60,
    ) -> dict[str, Any]:
        if start is None:
            start = datetime.now() + timedelta(minutes=offset_minutes)
        if end is None:
            end = start + timedelta(minutes=duration_minutes)
        return {
            "summary": summary,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
    return _create_event
