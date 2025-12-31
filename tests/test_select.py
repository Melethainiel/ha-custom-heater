"""Tests for select entities."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.chauffage_intelligent.const import (
    CONF_PIECE_NAME,
    DOMAIN,
    MODE_AUTO,
    MODE_CONFORT,
    MODE_ECO,
    MODE_HORS_GEL,
    SOURCE_OVERRIDE,
)
from custom_components.chauffage_intelligent.select import (
    ChauffageIntelligentModeSelect,
    _label_to_mode,
)


class TestChauffageIntelligentModeSelect:
    """Test ChauffageIntelligentModeSelect."""

    def test_initialization(self, coordinator):
        """Test select entity initialization."""
        piece_config = {CONF_PIECE_NAME: "Bureau"}
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", piece_config)

        assert select._attr_unique_id == f"{DOMAIN}_bureau_mode_select"
        assert select._attr_name == "Bureau Mode"
        assert select._piece_id == "bureau"
        assert select._piece_name == "Bureau"

    def test_initialization_without_name(self, coordinator):
        """Test select entity initialization without piece name falls back to id."""
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", {})

        assert select._attr_name == "bureau Mode"
        assert select._piece_name == "bureau"

    def test_options_are_french_labels(self, coordinator):
        """Test that options are French labels."""
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", {})

        expected_options = ["Automatique", "Confort", "Éco", "Hors-gel"]
        assert select._attr_options == expected_options

    def test_current_option_returns_auto_when_no_data(self, coordinator):
        """Test current_option returns Automatique when no data."""
        coordinator.data = None
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", {})

        assert select.current_option == "Automatique"

    def test_current_option_returns_auto_when_piece_not_found(self, coordinator):
        """Test current_option returns Automatique when piece not found."""
        coordinator.data = {"pieces": {}}
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", {})

        assert select.current_option == "Automatique"

    def test_current_option_returns_auto_when_source_not_override(self, coordinator):
        """Test current_option returns Automatique when source is not override."""
        coordinator.data = {"pieces": {"bureau": {"mode": "confort", "source": "calendrier"}}}
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", {})

        assert select.current_option == "Automatique"

    def test_current_option_returns_mode_label_when_override(self, coordinator):
        """Test current_option returns correct label when mode is overridden."""
        coordinator.data = {"pieces": {"bureau": {"mode": "confort", "source": SOURCE_OVERRIDE}}}
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", {})

        assert select.current_option == "Confort"

    def test_current_option_returns_eco_label_when_override(self, coordinator):
        """Test current_option returns Éco label when eco mode is overridden."""
        coordinator.data = {"pieces": {"bureau": {"mode": "eco", "source": SOURCE_OVERRIDE}}}
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", {})

        assert select.current_option == "Éco"

    def test_current_option_returns_hors_gel_label_when_override(self, coordinator):
        """Test current_option returns Hors-gel label when hors_gel mode is overridden."""
        coordinator.data = {"pieces": {"bureau": {"mode": "hors_gel", "source": SOURCE_OVERRIDE}}}
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", {})

        assert select.current_option == "Hors-gel"

    def test_current_option_returns_auto_for_unknown_mode_in_override(self, coordinator):
        """Test current_option returns Automatique for unknown mode even when overridden."""
        coordinator.data = {
            "pieces": {"bureau": {"mode": "unknown_mode", "source": SOURCE_OVERRIDE}}
        }
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", {})

        assert select.current_option == "Automatique"

    @pytest.mark.asyncio
    async def test_async_select_option_auto_resets_override(self, coordinator):
        """Test selecting Automatique resets the mode override."""
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", {})

        # Mock the coordinator methods
        coordinator.async_reset_mode_override = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

        await select.async_select_option("Automatique")

        coordinator.async_reset_mode_override.assert_called_once_with("bureau")
        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_select_option_confort_sets_override(self, coordinator):
        """Test selecting Confort sets the mode override."""
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", {})

        # Mock the coordinator methods
        coordinator.async_set_mode_override = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

        await select.async_select_option("Confort")

        coordinator.async_set_mode_override.assert_called_once_with("bureau", "confort")
        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_select_option_eco_sets_override(self, coordinator):
        """Test selecting Éco sets the mode override."""
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", {})

        # Mock the coordinator methods
        coordinator.async_set_mode_override = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

        await select.async_select_option("Éco")

        coordinator.async_set_mode_override.assert_called_once_with("bureau", "eco")
        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_select_option_hors_gel_sets_override(self, coordinator):
        """Test selecting Hors-gel sets the mode override."""
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", {})

        # Mock the coordinator methods
        coordinator.async_set_mode_override = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

        await select.async_select_option("Hors-gel")

        coordinator.async_set_mode_override.assert_called_once_with("bureau", "hors_gel")
        coordinator.async_request_refresh.assert_called_once()

    def test_extra_state_attributes_returns_empty_when_no_data(self, coordinator):
        """Test extra_state_attributes returns empty dict when no data."""
        coordinator.data = None
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", {})

        assert select.extra_state_attributes == {}

    def test_extra_state_attributes_returns_empty_when_piece_not_found(self, coordinator):
        """Test extra_state_attributes returns empty dict when piece not found."""
        coordinator.data = {"pieces": {}}
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", {})

        assert select.extra_state_attributes == {}

    def test_extra_state_attributes_returns_calculated_mode_and_source(self, coordinator):
        """Test extra_state_attributes returns calculated_mode and source."""
        coordinator.data = {"pieces": {"bureau": {"mode": "confort", "source": "calendrier"}}}
        select = ChauffageIntelligentModeSelect(coordinator, "bureau", {})

        assert select.extra_state_attributes == {
            "calculated_mode": "confort",
            "source": "calendrier",
        }


class TestLabelToMode:
    """Test _label_to_mode helper function."""

    def test_automatique_returns_auto(self):
        """Test Automatique label returns auto mode."""
        assert _label_to_mode("Automatique") == MODE_AUTO

    def test_confort_returns_confort(self):
        """Test Confort label returns confort mode."""
        assert _label_to_mode("Confort") == MODE_CONFORT

    def test_eco_returns_eco(self):
        """Test Éco label returns eco mode."""
        assert _label_to_mode("Éco") == MODE_ECO

    def test_hors_gel_returns_hors_gel(self):
        """Test Hors-gel label returns hors_gel mode."""
        assert _label_to_mode("Hors-gel") == MODE_HORS_GEL

    def test_unknown_label_returns_auto(self):
        """Test unknown label returns auto mode as fallback."""
        assert _label_to_mode("Unknown") == MODE_AUTO

    def test_empty_label_returns_auto(self):
        """Test empty label returns auto mode as fallback."""
        assert _label_to_mode("") == MODE_AUTO
