"""Tests for binary sensor entities."""
from __future__ import annotations

from custom_components.chauffage_intelligent.binary_sensor import (
    HomeOccupiedSensor,
    RoomPreheatActiveSensor,
)
from custom_components.chauffage_intelligent.const import CONF_PIECE_NAME, DOMAIN


class TestHomeOccupiedSensor:
    """Test HomeOccupiedSensor."""

    def test_initialization(self, coordinator):
        """Test sensor initialization."""
        sensor = HomeOccupiedSensor(coordinator)

        assert sensor._attr_unique_id == f"{DOMAIN}_maison_occupee"
        assert sensor._attr_name == "Chauffage Maison Occupée"

    def test_is_on_when_occupied(self, coordinator):
        """Test is_on returns True when home is occupied."""
        coordinator.data = {"maison_occupee": True}
        sensor = HomeOccupiedSensor(coordinator)

        assert sensor.is_on is True

    def test_is_on_when_not_occupied(self, coordinator):
        """Test is_on returns False when home is not occupied."""
        coordinator.data = {"maison_occupee": False}
        sensor = HomeOccupiedSensor(coordinator)

        assert sensor.is_on is False

    def test_is_on_when_no_data(self, coordinator):
        """Test is_on returns None when no data."""
        coordinator.data = None
        sensor = HomeOccupiedSensor(coordinator)

        assert sensor.is_on is None


class TestRoomPreheatActiveSensor:
    """Test RoomPreheatActiveSensor."""

    def test_initialization(self, coordinator):
        """Test sensor initialization."""
        piece_config = {CONF_PIECE_NAME: "Bureau"}
        sensor = RoomPreheatActiveSensor(coordinator, "bureau", piece_config)

        assert sensor._attr_unique_id == f"{DOMAIN}_bureau_prechauffage_actif"
        assert sensor._attr_name == "Bureau Préchauffage Actif"

    def test_initialization_without_name(self, coordinator):
        """Test sensor initialization without piece name."""
        piece_config = {}
        sensor = RoomPreheatActiveSensor(coordinator, "bureau", piece_config)

        assert sensor._attr_name == "bureau Préchauffage Actif"

    def test_is_on_when_preheating(self, coordinator):
        """Test is_on returns True when preheating is active."""
        coordinator.data = {
            "pieces": {
                "bureau": {"prechauffage_actif": True}
            }
        }
        sensor = RoomPreheatActiveSensor(coordinator, "bureau", {})

        assert sensor.is_on is True

    def test_is_on_when_not_preheating(self, coordinator):
        """Test is_on returns False when preheating is not active."""
        coordinator.data = {
            "pieces": {
                "bureau": {"prechauffage_actif": False}
            }
        }
        sensor = RoomPreheatActiveSensor(coordinator, "bureau", {})

        assert sensor.is_on is False

    def test_is_on_when_no_data(self, coordinator):
        """Test is_on returns None when no data."""
        coordinator.data = None
        sensor = RoomPreheatActiveSensor(coordinator, "bureau", {})

        assert sensor.is_on is None

    def test_is_on_when_piece_not_found(self, coordinator):
        """Test is_on returns None when piece not in data."""
        coordinator.data = {"pieces": {}}
        sensor = RoomPreheatActiveSensor(coordinator, "bureau", {})

        assert sensor.is_on is None
