"""Tests for preheat calculation logic."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from custom_components.chauffage_intelligent.const import (
    DEFAULT_HEATING_RATE,
    DEFAULT_MIN_PREHEAT_TIME,
    DEFAULT_SECURITY_FACTOR,
)


class TestPreheatTimeCalculation:
    """Test preheat time calculation."""

    def test_already_at_temperature(self, coordinator):
        """Test when already at target temperature."""
        result = coordinator.compute_preheat_time(
            current_temp=20.0,
            target_temp=19.0,
            heating_rate=1.5,
        )

        assert result == 0

    def test_exactly_at_temperature(self, coordinator):
        """Test when exactly at target temperature."""
        result = coordinator.compute_preheat_time(
            current_temp=19.0,
            target_temp=19.0,
            heating_rate=1.5,
        )

        assert result == 0

    def test_normal_preheat_calculation(self, coordinator):
        """Test normal preheat time calculation."""
        # 3°C delta with 1.5°C/h rate = 2h = 120min
        # With 1.3 safety factor = 156min
        result = coordinator.compute_preheat_time(
            current_temp=17.0,
            target_temp=20.0,
            heating_rate=1.5,
        )

        expected = int((3.0 / 1.5) * 60 * DEFAULT_SECURITY_FACTOR)
        assert result == expected

    def test_minimum_preheat_time(self, coordinator):
        """Test that minimum preheat time is enforced."""
        # 0.5°C delta with 2°C/h rate = 15min
        # But minimum is 30min
        result = coordinator.compute_preheat_time(
            current_temp=19.5,
            target_temp=20.0,
            heating_rate=2.0,
        )

        assert result == DEFAULT_MIN_PREHEAT_TIME

    def test_no_heating_rate_uses_default(self, coordinator):
        """Test that missing heating rate uses default."""
        # 3°C delta with default 1.0°C/h rate = 3h = 180min
        # With 1.3 safety factor = 234min
        result = coordinator.compute_preheat_time(
            current_temp=17.0,
            target_temp=20.0,
            heating_rate=None,
        )

        expected = int((3.0 / DEFAULT_HEATING_RATE) * 60 * DEFAULT_SECURITY_FACTOR)
        assert result == expected

    def test_negative_heating_rate_uses_default(self, coordinator):
        """Test that negative (cooling) rate uses default."""
        # Room is cooling, so use default heating rate
        result = coordinator.compute_preheat_time(
            current_temp=17.0,
            target_temp=20.0,
            heating_rate=-0.5,
        )

        expected = int((3.0 / DEFAULT_HEATING_RATE) * 60 * DEFAULT_SECURITY_FACTOR)
        assert result == expected

    def test_zero_heating_rate_uses_default(self, coordinator):
        """Test that zero heating rate uses default."""
        result = coordinator.compute_preheat_time(
            current_temp=17.0,
            target_temp=20.0,
            heating_rate=0.0,
        )

        expected = int((3.0 / DEFAULT_HEATING_RATE) * 60 * DEFAULT_SECURITY_FACTOR)
        assert result == expected

    def test_no_current_temp_returns_minimum(self, coordinator):
        """Test that missing current temp returns minimum time."""
        result = coordinator.compute_preheat_time(
            current_temp=None,
            target_temp=20.0,
            heating_rate=1.5,
        )

        assert result == DEFAULT_MIN_PREHEAT_TIME


class TestPreheatTrigger:
    """Test preheat trigger logic."""

    def test_event_far_in_future_no_trigger(self, coordinator, calendar_event_factory):
        """Test that distant event doesn't trigger preheat."""
        # Event in 2 hours, estimated time 1 hour
        events = [
            calendar_event_factory("Confort", offset_minutes=120)
        ]

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result = coordinator._check_preheat_trigger(
                "bureau",
                events,
                preheat_time=60,  # 1 hour
            )

        assert result is False

    def test_event_soon_triggers_preheat(self, coordinator, calendar_event_factory):
        """Test that imminent event triggers preheat."""
        # Event in 1 hour, estimated time 1.5 hours
        events = [
            calendar_event_factory("Confort", offset_minutes=60)
        ]

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result = coordinator._check_preheat_trigger(
                "bureau",
                events,
                preheat_time=90,  # 1.5 hours
            )

        assert result is True

    def test_no_comfort_event_no_trigger(self, coordinator, calendar_event_factory):
        """Test that non-comfort events don't trigger preheat."""
        events = [
            calendar_event_factory("Absence", offset_minutes=30)
        ]

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result = coordinator._check_preheat_trigger(
                "bureau",
                events,
                preheat_time=60,
            )

        assert result is False

    def test_room_specific_event_triggers_only_that_room(
        self, coordinator, calendar_event_factory
    ):
        """Test that room-specific event only triggers for that room."""
        events = [
            calendar_event_factory("Confort Bureau", offset_minutes=30)
        ]

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            # Bureau should trigger
            result_bureau = coordinator._check_preheat_trigger(
                "bureau",
                events,
                preheat_time=60,
            )

            # Salon should not trigger
            result_salon = coordinator._check_preheat_trigger(
                "salon",
                events,
                preheat_time=60,
            )

        assert result_bureau is True
        assert result_salon is False

    def test_global_comfort_triggers_all_rooms(
        self, coordinator, calendar_event_factory
    ):
        """Test that global comfort event triggers all rooms."""
        events = [
            calendar_event_factory("Confort", offset_minutes=30)
        ]

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result_bureau = coordinator._check_preheat_trigger(
                "bureau",
                events,
                preheat_time=60,
            )

            result_salon = coordinator._check_preheat_trigger(
                "salon",
                events,
                preheat_time=60,
            )

        assert result_bureau is True
        assert result_salon is True

    def test_current_event_not_triggered(self, coordinator, calendar_event_factory):
        """Test that already-started events don't trigger anticipation."""
        # Event started 30 minutes ago
        events = [
            calendar_event_factory("Confort", offset_minutes=-30, duration_minutes=120)
        ]

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result = coordinator._check_preheat_trigger(
                "bureau",
                events,
                preheat_time=60,
            )

        # Event already started, so no anticipation needed
        assert result is False
