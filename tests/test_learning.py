"""Tests for heating rate learning."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
import tempfile

import pytest

from custom_components.chauffage_intelligent.coordinator import (
    HeatingRateLearner,
    LEARNING_MIN_SAMPLES,
    LEARNING_RATE_MIN,
    LEARNING_RATE_MAX,
)


@pytest.fixture
def temp_storage_path():
    """Create a temporary storage path for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_learned_rates.json"


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    return hass


@pytest.fixture
def learner(mock_hass, temp_storage_path):
    """Create a HeatingRateLearner instance for testing."""
    return HeatingRateLearner(mock_hass, temp_storage_path)


class TestHeatingRateLearner:
    """Test the HeatingRateLearner class."""

    def test_initial_state_empty(self, learner):
        """Test that learner starts with no data."""
        stats = learner.get_stats("bureau")
        assert stats["samples"] == 0
        assert stats["avg_rate"] is None

    def test_record_valid_observation(self, learner):
        """Test recording a valid observation."""
        learner.record_observation("bureau", 1.5, outdoor_temp=5.0, hour=10)

        stats = learner.get_stats("bureau")
        assert stats["samples"] == 1
        assert stats["avg_rate"] == 1.5

    def test_ignore_too_low_rate(self, learner):
        """Test that very low heating rates are ignored."""
        learner.record_observation("bureau", 0.1, outdoor_temp=5.0, hour=10)

        stats = learner.get_stats("bureau")
        assert stats["samples"] == 0

    def test_ignore_too_high_rate(self, learner):
        """Test that unrealistically high rates are ignored."""
        learner.record_observation("bureau", 10.0, outdoor_temp=5.0, hour=10)

        stats = learner.get_stats("bureau")
        assert stats["samples"] == 0

    def test_ignore_negative_rate(self, learner):
        """Test that negative rates (cooling) are ignored."""
        learner.record_observation("bureau", -1.0, outdoor_temp=5.0, hour=10)

        stats = learner.get_stats("bureau")
        assert stats["samples"] == 0

    def test_prediction_requires_min_samples(self, learner):
        """Test that prediction requires minimum samples."""
        # Add fewer than minimum samples
        for i in range(LEARNING_MIN_SAMPLES - 1):
            learner.record_observation("bureau", 1.5 + i * 0.1, hour=10)

        prediction = learner.get_predicted_rate("bureau")
        assert prediction is None

    def test_prediction_with_enough_samples(self, learner):
        """Test prediction when enough samples are available."""
        # Add minimum samples
        for i in range(LEARNING_MIN_SAMPLES):
            learner.record_observation("bureau", 1.5, hour=10)

        prediction = learner.get_predicted_rate("bureau")
        assert prediction is not None
        assert prediction == pytest.approx(1.5, rel=0.01)

    def test_prediction_weighted_by_time_period(self, learner):
        """Test that predictions are weighted by time of day."""
        # Add samples from different time periods
        # Morning samples (hour 8)
        for _ in range(5):
            learner.record_observation("bureau", 2.0, hour=8)

        # Evening samples (hour 20)
        for _ in range(5):
            learner.record_observation("bureau", 1.0, hour=20)

        # Prediction at morning should be closer to 2.0
        morning_prediction = learner.get_predicted_rate("bureau", hour=9)

        # Prediction at evening should be closer to 1.0
        evening_prediction = learner.get_predicted_rate("bureau", hour=21)

        assert morning_prediction > evening_prediction

    def test_prediction_weighted_by_outdoor_temp(self, learner):
        """Test that predictions are weighted by outdoor temperature."""
        # Add samples with cold outdoor temps
        for _ in range(5):
            learner.record_observation("bureau", 1.0, outdoor_temp=0.0, hour=12)

        # Add samples with warm outdoor temps
        for _ in range(5):
            learner.record_observation("bureau", 2.0, outdoor_temp=15.0, hour=12)

        # Prediction with cold outdoor temp should be closer to 1.0
        cold_prediction = learner.get_predicted_rate("bureau", outdoor_temp=2.0, hour=12)

        # Prediction with warm outdoor temp should be closer to 2.0
        warm_prediction = learner.get_predicted_rate("bureau", outdoor_temp=14.0, hour=12)

        assert warm_prediction > cold_prediction

    def test_data_persistence(self, mock_hass, temp_storage_path):
        """Test that learned data is persisted and reloaded."""
        # Create learner and add data
        learner1 = HeatingRateLearner(mock_hass, temp_storage_path)
        for _ in range(5):
            learner1.record_observation("bureau", 1.5, hour=10)

        # Create new learner instance that should load persisted data
        learner2 = HeatingRateLearner(mock_hass, temp_storage_path)

        stats = learner2.get_stats("bureau")
        assert stats["samples"] == 5

    def test_multiple_rooms_independent(self, learner):
        """Test that different rooms have independent data."""
        for _ in range(5):
            learner.record_observation("bureau", 1.5, hour=10)
            learner.record_observation("salon", 2.0, hour=10)

        bureau_pred = learner.get_predicted_rate("bureau")
        salon_pred = learner.get_predicted_rate("salon")

        assert bureau_pred == pytest.approx(1.5, rel=0.01)
        assert salon_pred == pytest.approx(2.0, rel=0.01)

    def test_stats_calculation(self, learner):
        """Test statistics calculation."""
        learner.record_observation("bureau", 1.0, hour=10)
        learner.record_observation("bureau", 2.0, hour=10)
        learner.record_observation("bureau", 3.0, hour=10)

        stats = learner.get_stats("bureau")

        assert stats["samples"] == 3
        assert stats["avg_rate"] == pytest.approx(2.0, rel=0.01)
        assert stats["min_rate"] == 1.0
        assert stats["max_rate"] == 3.0

    def test_same_time_period_detection(self, learner):
        """Test time period detection logic."""
        # Morning (6-12)
        assert learner._same_time_period(7, 10) is True
        assert learner._same_time_period(7, 14) is False

        # Afternoon (12-18)
        assert learner._same_time_period(13, 16) is True
        assert learner._same_time_period(13, 20) is False

        # Evening (18-22)
        assert learner._same_time_period(19, 21) is True
        assert learner._same_time_period(19, 8) is False

        # Night (22-6)
        assert learner._same_time_period(23, 2) is True
        assert learner._same_time_period(23, 10) is False


class TestCoordinatorLearningIntegration:
    """Test learning integration with coordinator."""

    def test_learning_only_in_comfort_mode(self, coordinator, mock_hass, mock_state):
        """Test that learning only happens during comfort mode."""
        mock_hass.states.get.return_value = mock_state("20.0")
        coordinator.hass = mock_hass

        # Simulate eco mode - should not learn
        coordinator._learn_heating_rate("bureau", "eco", 1.5, 5.0)

        stats = coordinator._learner.get_stats("bureau")
        assert stats["samples"] == 0

    def test_learning_in_comfort_mode(self, coordinator, mock_hass, mock_state):
        """Test that learning happens during comfort mode."""
        mock_hass.states.get.return_value = mock_state("20.0")
        coordinator.hass = mock_hass

        # Simulate comfort mode - should learn
        coordinator._learn_heating_rate("bureau", "confort", 1.5, 5.0)

        stats = coordinator._learner.get_stats("bureau")
        assert stats["samples"] == 1

    def test_learning_ignores_invalid_rate(self, coordinator, mock_hass, mock_state):
        """Test that invalid rates are not learned."""
        mock_hass.states.get.return_value = mock_state("20.0")
        coordinator.hass = mock_hass

        # Negative rate - should not learn
        coordinator._learn_heating_rate("bureau", "confort", -0.5, 5.0)

        # None rate - should not learn
        coordinator._learn_heating_rate("bureau", "confort", None, 5.0)

        stats = coordinator._learner.get_stats("bureau")
        assert stats["samples"] == 0
