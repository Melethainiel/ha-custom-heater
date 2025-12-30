"""Tests for mode resolution logic."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from custom_components.chauffage_intelligent.const import (
    MODE_CONFORT,
    MODE_ECO,
    MODE_HORS_GEL,
    SOURCE_CALENDAR,
    SOURCE_PRESENCE,
    SOURCE_DEFAULT,
    SOURCE_OVERRIDE,
)


class TestModeResolution:
    """Test mode resolution logic."""

    def test_absence_event_returns_hors_gel(self, coordinator):
        """Test that 'Absence' calendar event returns hors_gel mode."""
        parsed_events = {
            "absence": True,
            "confort_global": False,
            "confort_pieces": set(),
        }
        maison_occupee = True  # Even with people home

        mode, source = coordinator._resolve_mode("bureau", parsed_events, maison_occupee)

        assert mode == MODE_HORS_GEL
        assert source == SOURCE_CALENDAR

    def test_nobody_home_returns_eco(self, coordinator):
        """Test that nobody home returns eco mode."""
        parsed_events = {
            "absence": False,
            "confort_global": True,  # Calendar says comfort
            "confort_pieces": set(),
        }
        maison_occupee = False  # But nobody home

        mode, source = coordinator._resolve_mode("bureau", parsed_events, maison_occupee)

        assert mode == MODE_ECO
        assert source == SOURCE_PRESENCE

    def test_confort_global_with_presence(self, coordinator):
        """Test global comfort with someone home."""
        parsed_events = {
            "absence": False,
            "confort_global": True,
            "confort_pieces": set(),
        }
        maison_occupee = True

        mode, source = coordinator._resolve_mode("bureau", parsed_events, maison_occupee)

        assert mode == MODE_CONFORT
        assert source == SOURCE_CALENDAR

    def test_confort_specific_room(self, coordinator):
        """Test room-specific comfort event."""
        parsed_events = {
            "absence": False,
            "confort_global": False,
            "confort_pieces": {"bureau"},  # Only bureau in comfort
        }
        maison_occupee = True

        # Bureau should be in comfort
        mode, source = coordinator._resolve_mode("bureau", parsed_events, maison_occupee)
        assert mode == MODE_CONFORT
        assert source == SOURCE_CALENDAR

        # Salon should be in eco (default)
        mode, source = coordinator._resolve_mode("salon", parsed_events, maison_occupee)
        assert mode == MODE_ECO
        assert source == SOURCE_DEFAULT

    def test_no_events_returns_eco(self, coordinator):
        """Test that no events returns eco mode by default."""
        parsed_events = {
            "absence": False,
            "confort_global": False,
            "confort_pieces": set(),
        }
        maison_occupee = True

        mode, source = coordinator._resolve_mode("bureau", parsed_events, maison_occupee)

        assert mode == MODE_ECO
        assert source == SOURCE_DEFAULT

    def test_override_takes_priority(self, coordinator):
        """Test that manual override takes priority over everything."""
        from datetime import datetime, timedelta
        from homeassistant.util import dt as dt_util

        # Set an override that doesn't expire
        coordinator._mode_overrides["bureau"] = (MODE_CONFORT, None)

        parsed_events = {
            "absence": True,  # Would normally force hors_gel
            "confort_global": False,
            "confort_pieces": set(),
        }
        maison_occupee = True

        mode, source = coordinator._resolve_mode("bureau", parsed_events, maison_occupee)

        assert mode == MODE_CONFORT
        assert source == SOURCE_OVERRIDE

    def test_expired_override_is_ignored(self, coordinator):
        """Test that expired override is removed and ignored."""
        from datetime import datetime, timedelta
        from unittest.mock import patch
        from homeassistant.util import dt as dt_util

        # Set an override that expired
        past = datetime.now() - timedelta(hours=1)
        coordinator._mode_overrides["bureau"] = (MODE_CONFORT, past)

        parsed_events = {
            "absence": False,
            "confort_global": False,
            "confort_pieces": set(),
        }
        maison_occupee = True

        with patch.object(dt_util, "now", return_value=datetime.now()):
            mode, source = coordinator._resolve_mode("bureau", parsed_events, maison_occupee)

        assert mode == MODE_ECO
        assert source == SOURCE_DEFAULT
        # Override should have been removed
        assert "bureau" not in coordinator._mode_overrides


class TestPresenceComputation:
    """Test presence computation logic."""

    def test_one_tracker_home(self, coordinator, mock_hass, mock_state):
        """Test that one tracker home means house is occupied."""
        mock_hass.states.get.side_effect = lambda entity_id: {
            "device_tracker.phone_1": mock_state("home"),
            "device_tracker.phone_2": mock_state("not_home"),
        }.get(entity_id)

        coordinator.hass = mock_hass
        result = coordinator._compute_presence()

        assert result is True

    def test_all_trackers_away(self, coordinator, mock_hass, mock_state):
        """Test that all trackers away means house is unoccupied."""
        mock_hass.states.get.side_effect = lambda entity_id: {
            "device_tracker.phone_1": mock_state("not_home"),
            "device_tracker.phone_2": mock_state("not_home"),
        }.get(entity_id)

        coordinator.hass = mock_hass
        result = coordinator._compute_presence()

        assert result is False

    def test_all_trackers_home(self, coordinator, mock_hass, mock_state):
        """Test that all trackers home means house is occupied."""
        mock_hass.states.get.side_effect = lambda entity_id: {
            "device_tracker.phone_1": mock_state("home"),
            "device_tracker.phone_2": mock_state("home"),
        }.get(entity_id)

        coordinator.hass = mock_hass
        result = coordinator._compute_presence()

        assert result is True

    def test_unavailable_tracker(self, coordinator, mock_hass, mock_state):
        """Test handling of unavailable trackers."""
        mock_hass.states.get.side_effect = lambda entity_id: {
            "device_tracker.phone_1": mock_state("unavailable"),
            "device_tracker.phone_2": mock_state("home"),
        }.get(entity_id)

        coordinator.hass = mock_hass
        result = coordinator._compute_presence()

        # Should still be occupied because phone_2 is home
        assert result is True

    def test_no_trackers_available(self, coordinator, mock_hass):
        """Test when no tracker returns valid state."""
        mock_hass.states.get.return_value = None

        coordinator.hass = mock_hass
        result = coordinator._compute_presence()

        assert result is False
