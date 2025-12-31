"""Tests for sensor entities."""
from __future__ import annotations

from custom_components.chauffage_intelligent.const import CONF_PIECE_NAME, DOMAIN
from custom_components.chauffage_intelligent.sensor import (
    GlobalModeSensor,
    RoomHeatingRateSensor,
    RoomModeSensor,
    RoomPreheatTimeSensor,
    RoomTargetTempSensor,
)


class TestGlobalModeSensor:
    """Test GlobalModeSensor."""

    def test_initialization(self, coordinator):
        """Test sensor initialization."""
        sensor = GlobalModeSensor(coordinator)

        assert sensor._attr_unique_id == f"{DOMAIN}_mode_global"
        assert sensor._attr_name == "Chauffage Mode Global"

    def test_native_value_returns_dominant_mode(self, coordinator):
        """Test native_value returns the most common mode."""
        coordinator.data = {
            "pieces": {
                "bureau": {"mode": "confort"},
                "salon": {"mode": "confort"},
                "chambre": {"mode": "eco"},
            }
        }
        sensor = GlobalModeSensor(coordinator)

        assert sensor.native_value == "confort"

    def test_native_value_when_all_same_mode(self, coordinator):
        """Test native_value when all rooms have same mode."""
        coordinator.data = {
            "pieces": {
                "bureau": {"mode": "eco"},
                "salon": {"mode": "eco"},
            }
        }
        sensor = GlobalModeSensor(coordinator)

        assert sensor.native_value == "eco"

    def test_native_value_when_no_data(self, coordinator):
        """Test native_value returns None when no data."""
        coordinator.data = None
        sensor = GlobalModeSensor(coordinator)

        assert sensor.native_value is None

    def test_native_value_when_no_pieces(self, coordinator):
        """Test native_value returns None when no pieces."""
        coordinator.data = {"pieces": {}}
        sensor = GlobalModeSensor(coordinator)

        assert sensor.native_value is None

    def test_native_value_when_no_modes(self, coordinator):
        """Test native_value returns None when pieces have no modes."""
        coordinator.data = {
            "pieces": {
                "bureau": {},
                "salon": {},
            }
        }
        sensor = GlobalModeSensor(coordinator)

        assert sensor.native_value is None


class TestRoomModeSensor:
    """Test RoomModeSensor."""

    def test_initialization(self, coordinator):
        """Test sensor initialization."""
        piece_config = {CONF_PIECE_NAME: "Bureau"}
        sensor = RoomModeSensor(coordinator, "bureau", piece_config)

        assert sensor._attr_unique_id == f"{DOMAIN}_bureau_mode_calcule"
        assert sensor._attr_name == "Bureau Mode"

    def test_native_value_returns_mode(self, coordinator):
        """Test native_value returns the room mode."""
        coordinator.data = {
            "pieces": {
                "bureau": {"mode": "confort", "source": "calendrier"}
            }
        }
        sensor = RoomModeSensor(coordinator, "bureau", {})

        assert sensor.native_value == "confort"

    def test_native_value_when_no_data(self, coordinator):
        """Test native_value returns None when no data."""
        coordinator.data = None
        sensor = RoomModeSensor(coordinator, "bureau", {})

        assert sensor.native_value is None

    def test_native_value_when_piece_not_found(self, coordinator):
        """Test native_value returns None when piece not found."""
        coordinator.data = {"pieces": {}}
        sensor = RoomModeSensor(coordinator, "bureau", {})

        assert sensor.native_value is None

    def test_extra_state_attributes(self, coordinator):
        """Test extra_state_attributes returns source."""
        coordinator.data = {
            "pieces": {
                "bureau": {"mode": "confort", "source": "calendrier"}
            }
        }
        sensor = RoomModeSensor(coordinator, "bureau", {})

        assert sensor.extra_state_attributes == {"source": "calendrier"}

    def test_extra_state_attributes_when_no_data(self, coordinator):
        """Test extra_state_attributes returns empty when no data."""
        coordinator.data = None
        sensor = RoomModeSensor(coordinator, "bureau", {})

        assert sensor.extra_state_attributes == {}

    def test_extra_state_attributes_when_piece_not_found(self, coordinator):
        """Test extra_state_attributes returns empty when piece not found."""
        coordinator.data = {"pieces": {}}
        sensor = RoomModeSensor(coordinator, "bureau", {})

        assert sensor.extra_state_attributes == {}


class TestRoomTargetTempSensor:
    """Test RoomTargetTempSensor."""

    def test_initialization(self, coordinator):
        """Test sensor initialization."""
        piece_config = {CONF_PIECE_NAME: "Bureau"}
        sensor = RoomTargetTempSensor(coordinator, "bureau", piece_config)

        assert sensor._attr_unique_id == f"{DOMAIN}_bureau_temperature_cible"
        assert sensor._attr_name == "Bureau Température Cible"

    def test_native_value_returns_target_temp(self, coordinator):
        """Test native_value returns the target temperature."""
        coordinator.data = {
            "pieces": {
                "bureau": {"consigne": 19.0}
            }
        }
        sensor = RoomTargetTempSensor(coordinator, "bureau", {})

        assert sensor.native_value == 19.0

    def test_native_value_when_no_data(self, coordinator):
        """Test native_value returns None when no data."""
        coordinator.data = None
        sensor = RoomTargetTempSensor(coordinator, "bureau", {})

        assert sensor.native_value is None

    def test_native_value_when_piece_not_found(self, coordinator):
        """Test native_value returns None when piece not found."""
        coordinator.data = {"pieces": {}}
        sensor = RoomTargetTempSensor(coordinator, "bureau", {})

        assert sensor.native_value is None


class TestRoomPreheatTimeSensor:
    """Test RoomPreheatTimeSensor."""

    def test_initialization(self, coordinator):
        """Test sensor initialization."""
        piece_config = {CONF_PIECE_NAME: "Bureau"}
        sensor = RoomPreheatTimeSensor(coordinator, "bureau", piece_config)

        assert sensor._attr_unique_id == f"{DOMAIN}_bureau_temps_prechauffage"
        assert sensor._attr_name == "Bureau Temps Préchauffage"

    def test_native_value_returns_preheat_time(self, coordinator):
        """Test native_value returns the preheat time."""
        coordinator.data = {
            "pieces": {
                "bureau": {"temps_prechauffage": 45}
            }
        }
        sensor = RoomPreheatTimeSensor(coordinator, "bureau", {})

        assert sensor.native_value == 45

    def test_native_value_when_no_data(self, coordinator):
        """Test native_value returns None when no data."""
        coordinator.data = None
        sensor = RoomPreheatTimeSensor(coordinator, "bureau", {})

        assert sensor.native_value is None

    def test_native_value_when_piece_not_found(self, coordinator):
        """Test native_value returns None when piece not found."""
        coordinator.data = {"pieces": {}}
        sensor = RoomPreheatTimeSensor(coordinator, "bureau", {})

        assert sensor.native_value is None


class TestRoomHeatingRateSensor:
    """Test RoomHeatingRateSensor."""

    def test_initialization(self, coordinator):
        """Test sensor initialization."""
        piece_config = {CONF_PIECE_NAME: "Bureau"}
        sensor = RoomHeatingRateSensor(coordinator, "bureau", piece_config)

        assert sensor._attr_unique_id == f"{DOMAIN}_bureau_vitesse_chauffe"
        assert sensor._attr_name == "Bureau Vitesse Chauffe"

    def test_native_value_returns_heating_rate(self, coordinator):
        """Test native_value returns the heating rate rounded."""
        coordinator.data = {
            "pieces": {
                "bureau": {"vitesse_chauffe": 1.2345}
            }
        }
        sensor = RoomHeatingRateSensor(coordinator, "bureau", {})

        assert sensor.native_value == 1.23

    def test_native_value_when_no_data(self, coordinator):
        """Test native_value returns None when no data."""
        coordinator.data = None
        sensor = RoomHeatingRateSensor(coordinator, "bureau", {})

        assert sensor.native_value is None

    def test_native_value_when_piece_not_found(self, coordinator):
        """Test native_value returns None when piece not found."""
        coordinator.data = {"pieces": {}}
        sensor = RoomHeatingRateSensor(coordinator, "bureau", {})

        assert sensor.native_value is None

    def test_native_value_when_rate_is_none(self, coordinator):
        """Test native_value returns None when rate is None."""
        coordinator.data = {
            "pieces": {
                "bureau": {"vitesse_chauffe": None}
            }
        }
        sensor = RoomHeatingRateSensor(coordinator, "bureau", {})

        assert sensor.native_value is None
