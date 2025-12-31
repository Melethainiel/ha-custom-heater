"""Tests for climate entities."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.const import ATTR_TEMPERATURE

from custom_components.chauffage_intelligent.climate import ChauffageIntelligentClimate
from custom_components.chauffage_intelligent.const import (
    CONF_PIECE_NAME,
    CONF_PIECE_RADIATEUR,
    CONF_PIECE_SONDE,
    CONF_PIECE_TEMPERATURES,
    CONF_PIECE_TYPE,
    DOMAIN,
    MODE_CONFORT,
    MODE_ECO,
    MODE_HORS_GEL,
    MODE_OFF,
)


@pytest.fixture
def piece_config():
    """Create a piece configuration for testing."""
    return {
        CONF_PIECE_NAME: "Bureau",
        CONF_PIECE_TYPE: "bureau",
        CONF_PIECE_RADIATEUR: "climate.bilbao_bureau",
        CONF_PIECE_SONDE: "sensor.temperature_bureau",
        CONF_PIECE_TEMPERATURES: {
            MODE_CONFORT: 19,
            MODE_ECO: 17,
            MODE_HORS_GEL: 7,
        },
    }


class TestChauffageIntelligentClimate:
    """Test ChauffageIntelligentClimate entity."""

    def test_initialization(self, coordinator, piece_config):
        """Test climate entity initialization."""
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        assert climate._attr_unique_id == f"{DOMAIN}_bureau"
        assert climate._attr_name == "Chauffage Bureau"
        assert climate._attr_min_temp == 7
        assert climate._attr_max_temp == 21  # 19 + 2

    def test_initialization_without_name(self, coordinator):
        """Test climate entity initialization without piece name."""
        piece_config = {CONF_PIECE_TEMPERATURES: {}}
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        assert climate._attr_name == "Chauffage bureau"

    def test_initialization_default_temps(self, coordinator):
        """Test climate entity with default temperature limits."""
        piece_config = {}
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        # Defaults: hors_gel=7, confort=22
        assert climate._attr_min_temp == 7
        assert climate._attr_max_temp == 24  # 22 + 2

    def test_piece_data_returns_data(self, coordinator, piece_config):
        """Test _piece_data returns room data."""
        coordinator.data = {
            "pieces": {
                "bureau": {"mode": "confort", "temperature": 18.5}
            }
        }
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        assert climate._piece_data == {"mode": "confort", "temperature": 18.5}

    def test_piece_data_returns_none_when_no_data(self, coordinator, piece_config):
        """Test _piece_data returns None when coordinator has no data."""
        coordinator.data = None
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        assert climate._piece_data is None

    def test_piece_data_returns_none_when_piece_not_found(self, coordinator, piece_config):
        """Test _piece_data returns None when piece not in data."""
        coordinator.data = {"pieces": {}}
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        assert climate._piece_data is None

    def test_current_temperature(self, coordinator, piece_config):
        """Test current_temperature property."""
        coordinator.data = {
            "pieces": {
                "bureau": {"temperature": 18.5}
            }
        }
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        assert climate.current_temperature == 18.5

    def test_current_temperature_when_no_data(self, coordinator, piece_config):
        """Test current_temperature returns None when no data."""
        coordinator.data = None
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        assert climate.current_temperature is None

    def test_target_temperature(self, coordinator, piece_config):
        """Test target_temperature property."""
        coordinator.data = {
            "pieces": {
                "bureau": {"consigne": 19.0}
            }
        }
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        assert climate.target_temperature == 19.0

    def test_target_temperature_when_no_data(self, coordinator, piece_config):
        """Test target_temperature returns None when no data."""
        coordinator.data = None
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        assert climate.target_temperature is None

    def test_hvac_mode_returns_heat(self, coordinator, piece_config):
        """Test hvac_mode returns HEAT when not off."""
        coordinator.data = {
            "pieces": {
                "bureau": {"mode": "confort"}
            }
        }
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        assert climate.hvac_mode == HVACMode.HEAT

    def test_hvac_mode_returns_off(self, coordinator, piece_config):
        """Test hvac_mode returns OFF when mode is off."""
        coordinator.data = {
            "pieces": {
                "bureau": {"mode": MODE_OFF}
            }
        }
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        assert climate.hvac_mode == HVACMode.OFF

    def test_hvac_mode_default_heat(self, coordinator, piece_config):
        """Test hvac_mode defaults to HEAT when no data."""
        coordinator.data = None
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        assert climate.hvac_mode == HVACMode.HEAT

    def test_extra_state_attributes_basic(self, coordinator, piece_config):
        """Test extra_state_attributes returns basic config."""
        coordinator.data = None
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        attrs = climate.extra_state_attributes
        assert attrs["radiateur_entity"] == "climate.bilbao_bureau"
        assert attrs["sonde_entity"] == "sensor.temperature_bureau"
        assert attrs["type_piece"] == "bureau"

    def test_extra_state_attributes_with_data(self, coordinator, piece_config):
        """Test extra_state_attributes includes piece data."""
        coordinator.data = {
            "pieces": {
                "bureau": {
                    "mode": "confort",
                    "source": "calendrier",
                    "consigne": 19.0,
                    "temperature": 18.5,
                    "vitesse_chauffe": 1.2,
                    "vitesse_apprise": 1.4,
                    "temps_prechauffage": 45,
                    "prechauffage_actif": False,
                    "prochain_evenement": "2025-01-02T18:00:00",
                    "learning_samples": 42,
                    "learning_avg_rate": 1.35,
                }
            }
        }
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        attrs = climate.extra_state_attributes
        assert attrs["mode_calcule"] == "confort"
        assert attrs["source_mode"] == "calendrier"
        assert attrs["temperature_cible"] == 19.0
        assert attrs["temperature_actuelle"] == 18.5
        assert attrs["vitesse_chauffe"] == 1.2
        assert attrs["vitesse_apprise"] == 1.4
        assert attrs["temps_prechauffage"] == 45
        assert attrs["prechauffage_actif"] is False
        assert attrs["prochain_evenement"] == "2025-01-02T18:00:00"
        assert attrs["learning_samples"] == 42
        assert attrs["learning_avg_rate"] == 1.35


class TestChauffageIntelligentClimateActions:
    """Test ChauffageIntelligentClimate actions."""

    @pytest.mark.asyncio
    async def test_async_set_temperature_confort(self, coordinator, piece_config):
        """Test setting temperature to comfort mode."""
        coordinator.async_set_mode_override = AsyncMock()
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        await climate.async_set_temperature(**{ATTR_TEMPERATURE: 20.0})

        coordinator.async_set_mode_override.assert_called_once_with("bureau", MODE_CONFORT)

    @pytest.mark.asyncio
    async def test_async_set_temperature_eco(self, coordinator, piece_config):
        """Test setting temperature to eco mode."""
        coordinator.async_set_mode_override = AsyncMock()
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        await climate.async_set_temperature(**{ATTR_TEMPERATURE: 18.0})

        coordinator.async_set_mode_override.assert_called_once_with("bureau", MODE_ECO)

    @pytest.mark.asyncio
    async def test_async_set_temperature_hors_gel(self, coordinator, piece_config):
        """Test setting temperature to hors-gel mode."""
        coordinator.async_set_mode_override = AsyncMock()
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        await climate.async_set_temperature(**{ATTR_TEMPERATURE: 10.0})

        coordinator.async_set_mode_override.assert_called_once_with("bureau", MODE_HORS_GEL)

    @pytest.mark.asyncio
    async def test_async_set_temperature_none(self, coordinator, piece_config):
        """Test setting temperature with None does nothing."""
        coordinator.async_set_mode_override = AsyncMock()
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        await climate.async_set_temperature()

        coordinator.async_set_mode_override.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_set_hvac_mode_off(self, coordinator, piece_config):
        """Test setting HVAC mode to OFF."""
        coordinator.async_set_mode_override = AsyncMock()
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        await climate.async_set_hvac_mode(HVACMode.OFF)

        coordinator.async_set_mode_override.assert_called_once_with("bureau", MODE_OFF)

    @pytest.mark.asyncio
    async def test_async_set_hvac_mode_heat(self, coordinator, piece_config):
        """Test setting HVAC mode to HEAT clears override."""
        coordinator.async_reset_mode_override = AsyncMock()
        climate = ChauffageIntelligentClimate(coordinator, "bureau", piece_config)

        await climate.async_set_hvac_mode(HVACMode.HEAT)

        coordinator.async_reset_mode_override.assert_called_once_with("bureau")
