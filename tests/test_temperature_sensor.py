"""Tests for temperature sensor fallback logic."""

from __future__ import annotations

from custom_components.chauffage_intelligent.const import (
    CONF_PIECE_RADIATEURS,
    CONF_PIECE_SONDE,
)


class TestTemperatureSensorFallback:
    """Test temperature sensor fallback logic."""

    def test_external_sensor_available(self, coordinator, mock_hass, mock_state):
        """Test that external sensor is used when available."""
        mock_hass.states.get.side_effect = lambda entity_id: {
            "sensor.temperature_bureau": mock_state("19.5"),
            "climate.bilbao_bureau": mock_state("heat", {"current_temperature": 18.0}),
        }.get(entity_id)

        coordinator.hass = mock_hass
        piece_config = {
            CONF_PIECE_SONDE: "sensor.temperature_bureau",
            CONF_PIECE_RADIATEURS: ["climate.bilbao_bureau"],
        }

        result = coordinator._get_temperature(piece_config)

        assert result == 19.5

    def test_fallback_to_radiator_sensor(self, coordinator, mock_hass, mock_state):
        """Test fallback to radiator's internal sensor."""
        mock_hass.states.get.side_effect = lambda entity_id: {
            "sensor.temperature_bureau": mock_state("unavailable"),
            "climate.bilbao_bureau": mock_state("heat", {"current_temperature": 18.0}),
        }.get(entity_id)

        coordinator.hass = mock_hass
        piece_config = {
            CONF_PIECE_SONDE: "sensor.temperature_bureau",
            CONF_PIECE_RADIATEURS: ["climate.bilbao_bureau"],
        }

        result = coordinator._get_temperature(piece_config)

        assert result == 18.0

    def test_external_sensor_unknown_uses_fallback(self, coordinator, mock_hass, mock_state):
        """Test that 'unknown' state triggers fallback."""
        mock_hass.states.get.side_effect = lambda entity_id: {
            "sensor.temperature_bureau": mock_state("unknown"),
            "climate.bilbao_bureau": mock_state("heat", {"current_temperature": 17.5}),
        }.get(entity_id)

        coordinator.hass = mock_hass
        piece_config = {
            CONF_PIECE_SONDE: "sensor.temperature_bureau",
            CONF_PIECE_RADIATEURS: ["climate.bilbao_bureau"],
        }

        result = coordinator._get_temperature(piece_config)

        assert result == 17.5

    def test_no_external_sensor_configured(self, coordinator, mock_hass, mock_state):
        """Test when no external sensor is configured."""
        mock_hass.states.get.side_effect = lambda entity_id: {
            "climate.bilbao_bureau": mock_state("heat", {"current_temperature": 18.5}),
        }.get(entity_id)

        coordinator.hass = mock_hass
        piece_config = {
            CONF_PIECE_SONDE: None,
            CONF_PIECE_RADIATEURS: ["climate.bilbao_bureau"],
        }

        result = coordinator._get_temperature(piece_config)

        assert result == 18.5

    def test_both_sensors_unavailable(self, coordinator, mock_hass, mock_state):
        """Test when both sensors are unavailable."""
        mock_hass.states.get.side_effect = lambda entity_id: {
            "sensor.temperature_bureau": mock_state("unavailable"),
            "climate.bilbao_bureau": mock_state("unavailable", {}),
        }.get(entity_id)

        coordinator.hass = mock_hass
        piece_config = {
            CONF_PIECE_SONDE: "sensor.temperature_bureau",
            CONF_PIECE_RADIATEURS: ["climate.bilbao_bureau"],
        }

        result = coordinator._get_temperature(piece_config)

        assert result is None

    def test_radiator_has_no_current_temperature(self, coordinator, mock_hass, mock_state):
        """Test when radiator doesn't expose current temperature."""
        mock_hass.states.get.side_effect = lambda entity_id: {
            "sensor.temperature_bureau": mock_state("unavailable"),
            "climate.bilbao_bureau": mock_state("heat", {}),  # No current_temperature
        }.get(entity_id)

        coordinator.hass = mock_hass
        piece_config = {
            CONF_PIECE_SONDE: "sensor.temperature_bureau",
            CONF_PIECE_RADIATEURS: ["climate.bilbao_bureau"],
        }

        result = coordinator._get_temperature(piece_config)

        assert result is None

    def test_invalid_temperature_value(self, coordinator, mock_hass, mock_state):
        """Test handling of invalid temperature value."""
        mock_hass.states.get.side_effect = lambda entity_id: {
            "sensor.temperature_bureau": mock_state("not_a_number"),
            "climate.bilbao_bureau": mock_state("heat", {"current_temperature": 18.0}),
        }.get(entity_id)

        coordinator.hass = mock_hass
        piece_config = {
            CONF_PIECE_SONDE: "sensor.temperature_bureau",
            CONF_PIECE_RADIATEURS: ["climate.bilbao_bureau"],
        }

        result = coordinator._get_temperature(piece_config)

        # Should fall back to radiator sensor
        assert result == 18.0

    def test_entity_not_found(self, coordinator, mock_hass):
        """Test when entities don't exist."""
        mock_hass.states.get.return_value = None

        coordinator.hass = mock_hass
        piece_config = {
            CONF_PIECE_SONDE: "sensor.nonexistent",
            CONF_PIECE_RADIATEURS: ["climate.nonexistent"],
        }

        result = coordinator._get_temperature(piece_config)

        assert result is None
