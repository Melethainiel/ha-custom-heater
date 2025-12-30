"""Tests for calendar event parsing."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest


class TestCalendarEventParsing:
    """Test calendar event parsing logic."""

    def test_parse_absence_event(self, coordinator, calendar_event_factory):
        """Test parsing 'Absence' event."""
        events = [
            calendar_event_factory("Absence", offset_minutes=-30, duration_minutes=120)
        ]

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result = coordinator._parse_calendar_events(events)

        assert result["absence"] is True
        assert result["confort_global"] is False
        assert len(result["confort_pieces"]) == 0

    def test_parse_confort_global(self, coordinator, calendar_event_factory):
        """Test parsing global 'Confort' event."""
        events = [
            calendar_event_factory("Confort", offset_minutes=-30, duration_minutes=120)
        ]

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result = coordinator._parse_calendar_events(events)

        assert result["absence"] is False
        assert result["confort_global"] is True
        assert len(result["confort_pieces"]) == 0

    def test_parse_confort_room_specific(self, coordinator, calendar_event_factory):
        """Test parsing room-specific 'Confort Bureau' event."""
        events = [
            calendar_event_factory("Confort Bureau", offset_minutes=-30, duration_minutes=120)
        ]

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result = coordinator._parse_calendar_events(events)

        assert result["absence"] is False
        assert result["confort_global"] is False
        assert "bureau" in result["confort_pieces"]

    def test_case_insensitive_matching(self, coordinator, calendar_event_factory):
        """Test that event matching is case-insensitive."""
        events = [
            calendar_event_factory("CONFORT BUREAU", offset_minutes=-30, duration_minutes=120)
        ]

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result = coordinator._parse_calendar_events(events)

        assert "bureau" in result["confort_pieces"]

    def test_whitespace_trimming(self, coordinator, calendar_event_factory):
        """Test that whitespace is trimmed from event summaries."""
        events = [
            calendar_event_factory("  Confort   Bureau  ", offset_minutes=-30, duration_minutes=120)
        ]

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result = coordinator._parse_calendar_events(events)

        assert "bureau" in result["confort_pieces"]

    def test_future_event_ignored(self, coordinator, calendar_event_factory):
        """Test that future events are not considered active."""
        # Event starts in 2 hours
        events = [
            calendar_event_factory("Confort", offset_minutes=120, duration_minutes=60)
        ]

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result = coordinator._parse_calendar_events(events)

        # Event is in the future, so not active
        assert result["confort_global"] is False

    def test_past_event_ignored(self, coordinator, calendar_event_factory):
        """Test that past events are not considered active."""
        # Event ended 1 hour ago
        events = [
            calendar_event_factory("Confort", offset_minutes=-120, duration_minutes=60)
        ]

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result = coordinator._parse_calendar_events(events)

        # Event has ended, so not active
        assert result["confort_global"] is False

    def test_multiple_events(self, coordinator, calendar_event_factory):
        """Test parsing multiple simultaneous events."""
        events = [
            calendar_event_factory("Confort Bureau", offset_minutes=-30, duration_minutes=120),
            calendar_event_factory("Confort Chambre", offset_minutes=-30, duration_minutes=120),
        ]

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result = coordinator._parse_calendar_events(events)

        assert "bureau" in result["confort_pieces"]
        assert "chambre" in result["confort_pieces"]
        assert result["confort_global"] is False

    def test_absence_overrides_confort(self, coordinator, calendar_event_factory):
        """Test that absence event is captured alongside comfort events."""
        events = [
            calendar_event_factory("Absence", offset_minutes=-30, duration_minutes=120),
            calendar_event_factory("Confort Bureau", offset_minutes=-30, duration_minutes=120),
        ]

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result = coordinator._parse_calendar_events(events)

        # Both should be captured; priority is handled in _resolve_mode
        assert result["absence"] is True
        assert "bureau" in result["confort_pieces"]

    def test_empty_summary(self, coordinator, calendar_event_factory):
        """Test handling of event with empty summary."""
        events = [
            calendar_event_factory("", offset_minutes=-30, duration_minutes=120)
        ]

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result = coordinator._parse_calendar_events(events)

        assert result["absence"] is False
        assert result["confort_global"] is False
        assert len(result["confort_pieces"]) == 0
