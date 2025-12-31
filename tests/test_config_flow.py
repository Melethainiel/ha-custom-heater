"""Tests for config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.chauffage_intelligent.config_flow import (
    ChauffageIntelligentConfigFlow,
    ChauffageIntelligentOptionsFlow,
    _slugify,
)
from custom_components.chauffage_intelligent.const import (
    CONF_CALENDAR,
    CONF_PIECE_NAME,
    CONF_PIECE_RADIATEUR,
    CONF_PIECE_TEMPERATURES,
    CONF_PIECE_TYPE,
    CONF_PIECES,
    CONF_PRESENCE_TRACKERS,
    MODE_CONFORT,
    MODE_ECO,
    MODE_HORS_GEL,
)


class TestSlugify:
    """Test the _slugify function."""

    def test_basic_slug(self):
        """Test basic slugification."""
        assert _slugify("Bureau") == "bureau"

    def test_slug_with_spaces(self):
        """Test slug with spaces."""
        assert _slugify("Salle de Bain") == "salle_de_bain"

    def test_slug_with_accents(self):
        """Test slug preserves accents."""
        assert _slugify("Séjour") == "séjour"

    def test_slug_with_special_chars(self):
        """Test slug removes special characters."""
        assert _slugify("Bureau (1)") == "bureau_1"

    def test_slug_with_hyphens(self):
        """Test slug converts hyphens to underscores."""
        assert _slugify("Salle-à-manger") == "salle_à_manger"

    def test_slug_with_leading_trailing_spaces(self):
        """Test slug strips leading/trailing spaces."""
        assert _slugify("  Bureau  ") == "bureau"


class TestConfigFlow:
    """Test the config flow."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock hass instance."""
        hass = MagicMock()

        # Mock calendar states
        calendar_state = MagicMock()
        calendar_state.entity_id = "calendar.google_home"

        # Mock device tracker states
        tracker_state = MagicMock()
        tracker_state.entity_id = "device_tracker.phone"

        # Mock climate states
        climate_state = MagicMock()
        climate_state.entity_id = "climate.bilbao_bureau"

        # Mock sensor states
        sensor_state = MagicMock()
        sensor_state.entity_id = "sensor.temperature_bureau"
        sensor_state.attributes = {"device_class": "temperature"}

        domain_states = {
            "calendar": [calendar_state],
            "device_tracker": [tracker_state],
            "climate": [climate_state],
            "sensor": [sensor_state],
        }
        hass.states.async_all = lambda domain: domain_states.get(domain, [])
        return hass

    def test_config_flow_init(self):
        """Test config flow initialization."""
        flow = ChauffageIntelligentConfigFlow()
        assert flow._data == {}

    @pytest.mark.asyncio
    async def test_async_step_user_shows_form(self, mock_hass):
        """Test user step shows form when no input."""
        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass

        result = await flow.async_step_user(None)

        assert result["type"] == "form"
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_async_step_user_no_calendars(self, mock_hass):
        """Test user step shows error when no calendars."""
        mock_hass.states.async_all = lambda domain: []

        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass

        result = await flow.async_step_user(None)

        assert result["type"] == "form"
        assert "no_trackers" in result.get("errors", {}).get("base", "")

    @pytest.mark.asyncio
    async def test_async_step_user_with_input(self, mock_hass):
        """Test user step proceeds to add_room with valid input."""
        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass

        user_input = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
        }

        result = await flow.async_step_user(user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "add_room"

    @pytest.mark.asyncio
    async def test_async_step_add_room_shows_form(self, mock_hass):
        """Test add_room step shows form."""
        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass
        flow._data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {},
        }

        result = await flow.async_step_add_room(None)

        assert result["type"] == "form"
        assert result["step_id"] == "add_room"

    @pytest.mark.asyncio
    async def test_async_step_add_room_skip_without_rooms(self, mock_hass):
        """Test skip_room fails when no rooms added."""
        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass
        flow._data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {},
        }

        result = await flow.async_step_add_room({"skip_room": True})

        assert result["type"] == "form"
        assert result["errors"]["base"] == "no_rooms"

    @pytest.mark.asyncio
    async def test_async_step_add_room_adds_room(self, mock_hass):
        """Test add_room adds a room and continues."""
        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass
        flow._data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {},
        }

        user_input = {
            CONF_PIECE_NAME: "Bureau",
            CONF_PIECE_TYPE: "bureau",
            CONF_PIECE_RADIATEUR: "climate.bilbao_bureau",
            "temp_confort": 19,
            "temp_eco": 17,
            "temp_hors_gel": 7,
        }

        result = await flow.async_step_add_room(user_input)

        assert "bureau" in flow._data[CONF_PIECES]
        assert flow._data[CONF_PIECES]["bureau"][CONF_PIECE_NAME] == "Bureau"
        assert result["type"] == "form"  # Shows form again to add more rooms

    @pytest.mark.asyncio
    async def test_async_step_add_room_finish(self, mock_hass):
        """Test add_room finishes when skip_room with existing rooms."""
        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass
        flow._data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {
                "bureau": {
                    CONF_PIECE_NAME: "Bureau",
                    CONF_PIECE_TYPE: "bureau",
                }
            },
        }

        result = await flow.async_step_add_room({"skip_room": True})

        assert result["type"] == "create_entry"
        assert result["title"] == "Chauffage Intelligent"


class TestOptionsFlow:
    """Test the options flow."""

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry."""
        entry = MagicMock()
        entry.data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {
                "bureau": {
                    CONF_PIECE_NAME: "Bureau",
                    CONF_PIECE_TYPE: "bureau",
                    CONF_PIECE_RADIATEUR: "climate.bilbao_bureau",
                    CONF_PIECE_TEMPERATURES: {
                        MODE_CONFORT: 19,
                        MODE_ECO: 17,
                        MODE_HORS_GEL: 7,
                    },
                }
            },
        }
        entry.entry_id = "test_entry_id"
        return entry

    @pytest.fixture
    def mock_hass(self):
        """Create a mock hass instance."""
        hass = MagicMock()

        # Mock states
        calendar_state = MagicMock()
        calendar_state.entity_id = "calendar.google_home"

        tracker_state = MagicMock()
        tracker_state.entity_id = "device_tracker.phone"

        climate_state = MagicMock()
        climate_state.entity_id = "climate.bilbao_bureau"

        sensor_state = MagicMock()
        sensor_state.entity_id = "sensor.temperature_bureau"
        sensor_state.attributes = {"device_class": "temperature"}

        domain_states = {
            "calendar": [calendar_state],
            "device_tracker": [tracker_state],
            "climate": [climate_state],
            "sensor": [sensor_state],
        }
        hass.states.async_all = lambda domain: domain_states.get(domain, [])
        hass.config_entries.async_update_entry = MagicMock()
        hass.config_entries.async_reload = AsyncMock()
        return hass

    def test_options_flow_init(self, mock_config_entry):
        """Test options flow initialization."""
        flow = ChauffageIntelligentOptionsFlow(mock_config_entry)

        assert flow.config_entry == mock_config_entry
        assert flow._data == dict(mock_config_entry.data)
        assert flow._selected_room is None

    @pytest.mark.asyncio
    async def test_async_step_init_shows_menu(self, mock_config_entry):
        """Test init step shows menu."""
        flow = ChauffageIntelligentOptionsFlow(mock_config_entry)

        result = await flow.async_step_init(None)

        assert result["type"] == "form"
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_async_step_init_add_room(self, mock_config_entry, mock_hass):
        """Test init step navigates to add_room."""
        flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
        flow.hass = mock_hass

        result = await flow.async_step_init({"action": "add_room"})

        assert result["type"] == "form"
        assert result["step_id"] == "add_room"

    @pytest.mark.asyncio
    async def test_async_step_init_modify_room(self, mock_config_entry, mock_hass):
        """Test init step navigates to select_room."""
        flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
        flow.hass = mock_hass

        result = await flow.async_step_init({"action": "modify_room"})

        assert result["type"] == "form"
        assert result["step_id"] == "select_room"

    @pytest.mark.asyncio
    async def test_async_step_init_delete_room(self, mock_config_entry, mock_hass):
        """Test init step navigates to delete_room."""
        flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
        flow.hass = mock_hass

        result = await flow.async_step_init({"action": "delete_room"})

        assert result["type"] == "form"
        assert result["step_id"] == "delete_room"

    @pytest.mark.asyncio
    async def test_async_step_init_settings(self, mock_config_entry, mock_hass):
        """Test init step navigates to settings."""
        flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
        flow.hass = mock_hass

        result = await flow.async_step_init({"action": "modify_settings"})

        assert result["type"] == "form"
        assert result["step_id"] == "settings"

    @pytest.mark.asyncio
    async def test_async_step_select_room_no_rooms(self, mock_config_entry, mock_hass):
        """Test select_room aborts when no rooms."""
        mock_config_entry.data = {CONF_PIECES: {}}
        flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
        flow.hass = mock_hass

        result = await flow.async_step_select_room(None)

        assert result["type"] == "abort"
        assert result["reason"] == "no_rooms"

    @pytest.mark.asyncio
    async def test_async_step_delete_room_no_rooms(self, mock_config_entry, mock_hass):
        """Test delete_room aborts when no rooms."""
        mock_config_entry.data = {CONF_PIECES: {}}
        flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
        flow.hass = mock_hass

        result = await flow.async_step_delete_room(None)

        assert result["type"] == "abort"
        assert result["reason"] == "no_rooms"

    @pytest.mark.asyncio
    async def test_async_step_add_room_existing_id(self, mock_config_entry, mock_hass):
        """Test add_room shows error for existing room ID."""
        flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
        flow.hass = mock_hass

        user_input = {
            CONF_PIECE_NAME: "Bureau",  # Will slugify to "bureau" which exists
            CONF_PIECE_TYPE: "bureau",
            CONF_PIECE_RADIATEUR: "climate.bilbao_bureau",
        }

        result = await flow.async_step_add_room(user_input)

        assert result["type"] == "form"
        assert result["errors"]["base"] == "room_exists"
