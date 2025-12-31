"""Tests for Chauffage Intelligent __init__.py."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.chauffage_intelligent import (
    _async_setup_services,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.chauffage_intelligent.const import (
    CONF_CALENDAR,
    CONF_PIECES,
    CONF_PRESENCE_TRACKERS,
    DOMAIN,
    MODE_CONFORT,
)


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.services = MagicMock()
    hass.services.async_register = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        CONF_CALENDAR: "calendar.google_home",
        CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
        CONF_PIECES: {
            "bureau": {
                "name": "Bureau",
                "type": "bureau",
            }
        },
    }
    return entry


class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_setup_entry_success(self, mock_hass, mock_config_entry):
        """Test successful setup of config entry."""
        with patch(
            "custom_components.chauffage_intelligent.ChauffageIntelligentCoordinator"
        ) as mock_coordinator_class:
            mock_coordinator = MagicMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator_class.return_value = mock_coordinator

            with patch(
                "custom_components.chauffage_intelligent._async_setup_services",
                new_callable=AsyncMock,
            ):
                result = await async_setup_entry(mock_hass, mock_config_entry)

        assert result is True
        assert DOMAIN in mock_hass.data
        assert mock_config_entry.entry_id in mock_hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_setup_entry_creates_coordinator(self, mock_hass, mock_config_entry):
        """Test that setup creates coordinator with correct config."""
        with patch(
            "custom_components.chauffage_intelligent.ChauffageIntelligentCoordinator"
        ) as mock_coordinator_class:
            mock_coordinator = MagicMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator_class.return_value = mock_coordinator

            with patch(
                "custom_components.chauffage_intelligent._async_setup_services",
                new_callable=AsyncMock,
            ):
                await async_setup_entry(mock_hass, mock_config_entry)

        mock_coordinator_class.assert_called_once()
        call_args = mock_coordinator_class.call_args
        assert call_args[0][0] == mock_hass  # First arg is hass

    @pytest.mark.asyncio
    async def test_setup_entry_forwards_platforms(self, mock_hass, mock_config_entry):
        """Test that setup forwards entry to platforms."""
        with patch(
            "custom_components.chauffage_intelligent.ChauffageIntelligentCoordinator"
        ) as mock_coordinator_class:
            mock_coordinator = MagicMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator_class.return_value = mock_coordinator

            with patch(
                "custom_components.chauffage_intelligent._async_setup_services",
                new_callable=AsyncMock,
            ):
                await async_setup_entry(mock_hass, mock_config_entry)

        mock_hass.config_entries.async_forward_entry_setups.assert_called_once()


class TestAsyncUnloadEntry:
    """Test async_unload_entry function."""

    @pytest.mark.asyncio
    async def test_unload_entry_success(self, mock_hass, mock_config_entry):
        """Test successful unload of config entry."""
        mock_hass.data[DOMAIN] = {mock_config_entry.entry_id: MagicMock()}

        result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is True
        assert mock_config_entry.entry_id not in mock_hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_unload_entry_calls_unload_platforms(
        self, mock_hass, mock_config_entry
    ):
        """Test that unload calls async_unload_platforms."""
        mock_hass.data[DOMAIN] = {mock_config_entry.entry_id: MagicMock()}

        await async_unload_entry(mock_hass, mock_config_entry)

        mock_hass.config_entries.async_unload_platforms.assert_called_once()

    @pytest.mark.asyncio
    async def test_unload_entry_failure(self, mock_hass, mock_config_entry):
        """Test unload when platforms fail to unload."""
        mock_hass.data[DOMAIN] = {mock_config_entry.entry_id: MagicMock()}
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

        result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is False
        # Entry should still be in data since unload failed
        assert mock_config_entry.entry_id in mock_hass.data[DOMAIN]


class TestAsyncSetupServices:
    """Test _async_setup_services function."""

    @pytest.mark.asyncio
    async def test_services_registered(self, mock_hass):
        """Test that services are registered."""
        mock_coordinator = MagicMock()

        await _async_setup_services(mock_hass, mock_coordinator)

        assert mock_hass.services.async_register.call_count == 3
        registered_services = [
            call[0][1] for call in mock_hass.services.async_register.call_args_list
        ]
        assert "set_mode" in registered_services
        assert "reset_mode" in registered_services
        assert "refresh" in registered_services

    @pytest.mark.asyncio
    async def test_set_mode_handler_valid_mode(self, mock_hass):
        """Test set_mode handler with valid mode."""
        mock_coordinator = MagicMock()
        mock_coordinator.async_set_mode_override = AsyncMock()

        await _async_setup_services(mock_hass, mock_coordinator)

        # Get the set_mode handler
        set_mode_handler = mock_hass.services.async_register.call_args_list[0][0][2]

        # Create mock service call
        mock_call = MagicMock()
        mock_call.data = {"piece": "bureau", "mode": MODE_CONFORT, "duree": 60}

        await set_mode_handler(mock_call)

        mock_coordinator.async_set_mode_override.assert_called_once_with(
            "bureau", MODE_CONFORT, 60
        )

    @pytest.mark.asyncio
    async def test_set_mode_handler_invalid_mode(self, mock_hass):
        """Test set_mode handler with invalid mode."""
        mock_coordinator = MagicMock()
        mock_coordinator.async_set_mode_override = AsyncMock()

        await _async_setup_services(mock_hass, mock_coordinator)

        # Get the set_mode handler
        set_mode_handler = mock_hass.services.async_register.call_args_list[0][0][2]

        # Create mock service call with invalid mode
        mock_call = MagicMock()
        mock_call.data = {"piece": "bureau", "mode": "invalid_mode"}

        await set_mode_handler(mock_call)

        # Should not call coordinator for invalid mode
        mock_coordinator.async_set_mode_override.assert_not_called()

    @pytest.mark.asyncio
    async def test_reset_mode_handler(self, mock_hass):
        """Test reset_mode handler."""
        mock_coordinator = MagicMock()
        mock_coordinator.async_reset_mode_override = AsyncMock()

        await _async_setup_services(mock_hass, mock_coordinator)

        # Get the reset_mode handler
        reset_mode_handler = mock_hass.services.async_register.call_args_list[1][0][2]

        # Create mock service call
        mock_call = MagicMock()
        mock_call.data = {"piece": "bureau"}

        await reset_mode_handler(mock_call)

        mock_coordinator.async_reset_mode_override.assert_called_once_with("bureau")

    @pytest.mark.asyncio
    async def test_refresh_handler(self, mock_hass):
        """Test refresh handler."""
        mock_coordinator = MagicMock()
        mock_coordinator.async_request_refresh = AsyncMock()

        await _async_setup_services(mock_hass, mock_coordinator)

        # Get the refresh handler
        refresh_handler = mock_hass.services.async_register.call_args_list[2][0][2]

        # Create mock service call
        mock_call = MagicMock()

        await refresh_handler(mock_call)

        mock_coordinator.async_request_refresh.assert_called_once()
