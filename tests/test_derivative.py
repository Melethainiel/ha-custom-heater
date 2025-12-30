"""Tests for temperature derivative (heating rate) calculation."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest


class TestDerivativeCalculation:
    """Test heating rate (derivative) calculation."""

    def test_no_history_returns_none(self, coordinator):
        """Test that first reading returns None (no derivative yet)."""
        # Clear any existing history
        coordinator._temp_history = {}

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result = coordinator._compute_derivative("bureau", 19.0)

        # First reading, can't compute derivative
        assert result is None

    def test_two_readings_computes_derivative(self, coordinator):
        """Test derivative computation with two readings."""
        coordinator._temp_history = {}
        now = datetime.now()

        # Simulate first reading 30 minutes ago
        with patch("homeassistant.util.dt.now", return_value=now - timedelta(minutes=30)):
            coordinator._compute_derivative("bureau", 17.0)

        # Second reading now
        with patch("homeassistant.util.dt.now", return_value=now):
            result = coordinator._compute_derivative("bureau", 18.0)

        # 1°C over 30 minutes = 2°C/h
        assert result == pytest.approx(2.0, rel=0.01)

    def test_cooling_rate_is_negative(self, coordinator):
        """Test that cooling produces negative rate."""
        coordinator._temp_history = {}
        now = datetime.now()

        # First reading 30 minutes ago at higher temp
        with patch("homeassistant.util.dt.now", return_value=now - timedelta(minutes=30)):
            coordinator._compute_derivative("bureau", 20.0)

        # Second reading now at lower temp
        with patch("homeassistant.util.dt.now", return_value=now):
            result = coordinator._compute_derivative("bureau", 19.0)

        # -1°C over 30 minutes = -2°C/h
        assert result == pytest.approx(-2.0, rel=0.01)

    def test_old_readings_are_pruned(self, coordinator):
        """Test that readings older than window are removed."""
        coordinator._temp_history = {}
        now = datetime.now()
        window = coordinator.derivative_window  # Default 30 minutes

        # Add old reading (45 minutes ago, outside window)
        coordinator._temp_history["bureau"] = [
            (now - timedelta(minutes=45), 15.0)
        ]

        # Add reading 20 minutes ago
        with patch("homeassistant.util.dt.now", return_value=now - timedelta(minutes=20)):
            coordinator._compute_derivative("bureau", 17.0)

        # Add current reading
        with patch("homeassistant.util.dt.now", return_value=now):
            result = coordinator._compute_derivative("bureau", 18.0)

        # Old reading should be pruned, derivative based on last 20 minutes
        # 1°C over 20 minutes = 3°C/h
        assert result == pytest.approx(3.0, rel=0.01)

        # Check that history doesn't include the old reading
        assert len(coordinator._temp_history["bureau"]) == 2

    def test_none_temperature_returns_none(self, coordinator):
        """Test that None temperature returns None derivative."""
        coordinator._temp_history = {}

        with patch("homeassistant.util.dt.now", return_value=datetime.now()):
            result = coordinator._compute_derivative("bureau", None)

        assert result is None

    def test_stable_temperature(self, coordinator):
        """Test stable temperature returns zero rate."""
        coordinator._temp_history = {}
        now = datetime.now()

        # First reading 30 minutes ago
        with patch("homeassistant.util.dt.now", return_value=now - timedelta(minutes=30)):
            coordinator._compute_derivative("bureau", 19.0)

        # Same temperature now
        with patch("homeassistant.util.dt.now", return_value=now):
            result = coordinator._compute_derivative("bureau", 19.0)

        assert result == pytest.approx(0.0, abs=0.01)

    def test_multiple_pieces_independent(self, coordinator):
        """Test that different rooms have independent histories."""
        coordinator._temp_history = {}
        now = datetime.now()

        # Bureau readings
        with patch("homeassistant.util.dt.now", return_value=now - timedelta(minutes=30)):
            coordinator._compute_derivative("bureau", 17.0)

        with patch("homeassistant.util.dt.now", return_value=now):
            result_bureau = coordinator._compute_derivative("bureau", 18.0)

        # Salon readings (different rate)
        with patch("homeassistant.util.dt.now", return_value=now - timedelta(minutes=30)):
            coordinator._compute_derivative("salon", 15.0)

        with patch("homeassistant.util.dt.now", return_value=now):
            result_salon = coordinator._compute_derivative("salon", 18.0)

        # Bureau: 1°C/30min = 2°C/h
        # Salon: 3°C/30min = 6°C/h
        assert result_bureau == pytest.approx(2.0, rel=0.01)
        assert result_salon == pytest.approx(6.0, rel=0.01)

    def test_same_time_readings(self, coordinator):
        """Test handling of readings at same timestamp."""
        coordinator._temp_history = {}
        now = datetime.now()

        # Two readings at exact same time
        with patch("homeassistant.util.dt.now", return_value=now):
            coordinator._compute_derivative("bureau", 17.0)
            result = coordinator._compute_derivative("bureau", 18.0)

        # Should return None (can't compute derivative with 0 time diff)
        assert result is None
