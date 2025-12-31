"""Tests for config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.chauffage_intelligent.config_flow import (
    ChauffageIntelligentConfigFlow,
    ChauffageIntelligentOptionsFlow,
)
from custom_components.chauffage_intelligent.const import (
    CONF_CALENDAR,
    CONF_PIECE_AREA_ID,
    CONF_PIECE_NAME,
    CONF_PIECE_RADIATEURS,
    CONF_PIECE_TEMPERATURES,
    CONF_PIECE_TYPE,
    CONF_PIECES,
    CONF_PRESENCE_TRACKERS,
    MODE_CONFORT,
    MODE_ECO,
    MODE_HORS_GEL,
)


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
        hass.states.get = lambda entity_id: {
            "sensor.temperature_bureau": sensor_state,
        }.get(entity_id)
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
        """Test user step proceeds to room_menu with valid input."""
        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass

        user_input = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
        }

        result = await flow.async_step_user(user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "room_menu"

    @pytest.mark.asyncio
    async def test_async_step_room_menu_shows_form(self, mock_hass):
        """Test room_menu step shows form."""
        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass
        flow._data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {},
        }

        result = await flow.async_step_room_menu(None)

        assert result["type"] == "form"
        assert result["step_id"] == "room_menu"

    @pytest.mark.asyncio
    async def test_async_step_room_menu_finish_without_rooms(self, mock_hass):
        """Test finish action fails when no rooms added."""
        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass
        flow._data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {},
        }

        result = await flow.async_step_room_menu({"action": "finish"})

        assert result["type"] == "form"
        assert result["errors"]["base"] == "no_rooms"

    @pytest.mark.asyncio
    async def test_async_step_room_menu_add_room_navigates_to_select_area(self, mock_hass):
        """Test add_room action navigates to select_area."""
        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass
        flow._data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {},
        }

        # Mock the area registry
        with patch(
            "custom_components.chauffage_intelligent.config_flow._get_areas_with_climate"
        ) as mock_areas:
            mock_areas.return_value = [{"value": "bureau", "label": "Bureau"}]

            result = await flow.async_step_room_menu({"action": "add_room"})

            assert result["type"] == "form"
            assert result["step_id"] == "select_area"

    @pytest.mark.asyncio
    async def test_async_step_configure_room_adds_room(self, mock_hass):
        """Test configure_room adds a room and returns to menu."""
        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass
        flow._data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {},
        }
        flow._current_area_id = "bureau"
        flow._current_area_name = "Bureau"

        user_input = {
            CONF_PIECE_TYPE: "bureau",
            CONF_PIECE_RADIATEURS: ["climate.bilbao_bureau"],
            "temp_confort": 19,
            "temp_eco": 17,
            "temp_hors_gel": 7,
        }

        result = await flow.async_step_configure_room(user_input)

        assert "bureau" in flow._data[CONF_PIECES]
        assert flow._data[CONF_PIECES]["bureau"][CONF_PIECE_NAME] == "Bureau"
        assert flow._data[CONF_PIECES]["bureau"][CONF_PIECE_RADIATEURS] == ["climate.bilbao_bureau"]
        assert result["type"] == "form"
        assert result["step_id"] == "room_menu"

    @pytest.mark.asyncio
    async def test_async_step_room_menu_finish_with_rooms(self, mock_hass):
        """Test finish action creates entry when rooms exist."""
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

        result = await flow.async_step_room_menu({"action": "finish"})

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
                    CONF_PIECE_AREA_ID: "bureau",
                    CONF_PIECE_TYPE: "bureau",
                    CONF_PIECE_RADIATEURS: ["climate.bilbao_bureau"],
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
        hass.states.get = lambda entity_id: {
            "sensor.temperature_bureau": sensor_state,
        }.get(entity_id)
        hass.config_entries.async_update_entry = MagicMock()
        hass.config_entries.async_reload = AsyncMock()
        return hass

    def test_options_flow_init(self, mock_config_entry):
        """Test options flow initialization."""
        # The OptionsFlow now uses config_entry from parent class
        # We need to patch it or use a different approach
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            assert flow._data == dict(mock_config_entry.data)
            assert flow._selected_room is None

    @pytest.mark.asyncio
    async def test_async_step_init_shows_menu(self, mock_config_entry):
        """Test init step shows menu."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)

            result = await flow.async_step_init(None)

            assert result["type"] == "form"
            assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_async_step_init_add_room(self, mock_config_entry, mock_hass):
        """Test init step navigates to select_area."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass

            with patch(
                "custom_components.chauffage_intelligent.config_flow._get_areas_with_climate"
            ) as mock_areas:
                mock_areas.return_value = [{"value": "salon", "label": "Salon"}]

                result = await flow.async_step_init({"action": "add_room"})

                assert result["type"] == "form"
                assert result["step_id"] == "select_area"

    @pytest.mark.asyncio
    async def test_async_step_init_modify_room(self, mock_config_entry, mock_hass):
        """Test init step navigates to select_room."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass

            result = await flow.async_step_init({"action": "modify_room"})

            assert result["type"] == "form"
            assert result["step_id"] == "select_room"

    @pytest.mark.asyncio
    async def test_async_step_init_delete_room(self, mock_config_entry, mock_hass):
        """Test init step navigates to delete_room."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass

            result = await flow.async_step_init({"action": "delete_room"})

            assert result["type"] == "form"
            assert result["step_id"] == "delete_room"

    @pytest.mark.asyncio
    async def test_async_step_init_settings(self, mock_config_entry, mock_hass):
        """Test init step navigates to settings."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass

            result = await flow.async_step_init({"action": "modify_settings"})

            assert result["type"] == "form"
            assert result["step_id"] == "settings"

    @pytest.mark.asyncio
    async def test_async_step_select_room_no_rooms(self, mock_config_entry, mock_hass):
        """Test select_room aborts when no rooms."""
        empty_entry = MagicMock()
        empty_entry.data = {CONF_PIECES: {}}
        empty_entry.entry_id = "test_entry_id"

        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: empty_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(empty_entry)
            flow.hass = mock_hass

            result = await flow.async_step_select_room(None)

            assert result["type"] == "abort"
            assert result["reason"] == "no_rooms"

    @pytest.mark.asyncio
    async def test_async_step_delete_room_no_rooms(self, mock_config_entry, mock_hass):
        """Test delete_room aborts when no rooms."""
        empty_entry = MagicMock()
        empty_entry.data = {CONF_PIECES: {}}
        empty_entry.entry_id = "test_entry_id"

        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: empty_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(empty_entry)
            flow.hass = mock_hass

            result = await flow.async_step_delete_room(None)

            assert result["type"] == "abort"
            assert result["reason"] == "no_rooms"

    @pytest.mark.asyncio
    async def test_async_step_select_area_already_configured(self, mock_config_entry, mock_hass):
        """Test select_area aborts when area already configured and no other areas available."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass

            # Mock area registry
            with (
                patch(
                    "custom_components.chauffage_intelligent.config_flow.ar.async_get"
                ) as mock_ar,
                patch(
                    "custom_components.chauffage_intelligent.config_flow._get_areas_with_climate"
                ) as mock_areas,
            ):
                mock_area = MagicMock()
                mock_area.id = "bureau"
                mock_area.name = "Bureau"
                mock_ar.return_value.async_get_area.return_value = mock_area
                # Only bureau available, but it's already configured
                mock_areas.return_value = [{"value": "bureau", "label": "Bureau"}]

                result = await flow.async_step_select_area({"area": "bureau"})

                # When trying to select an already-configured area and no other areas available,
                # the flow aborts with no_areas_available
                assert result["type"] == "abort"
                assert result["reason"] == "no_areas_available"
