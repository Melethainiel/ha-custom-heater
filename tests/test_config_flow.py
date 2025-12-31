"""Tests for config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.chauffage_intelligent.config_flow import (
    ChauffageIntelligentConfigFlow,
    ChauffageIntelligentOptionsFlow,
    _get_areas_with_climate,
    _get_climate_entities_for_area,
    _get_temperature_sensors_for_area,
)
from custom_components.chauffage_intelligent.const import (
    CONF_CALENDAR,
    CONF_MIN_PREHEAT_TIME,
    CONF_PIECE_AREA_ID,
    CONF_PIECE_NAME,
    CONF_PIECE_RADIATEURS,
    CONF_PIECE_SONDE,
    CONF_PIECE_TEMPERATURES,
    CONF_PIECE_TYPE,
    CONF_PIECES,
    CONF_PRESENCE_TRACKERS,
    CONF_SECURITY_FACTOR,
    CONF_UPDATE_INTERVAL,
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


class TestHelperFunctions:
    """Test helper functions for area and entity discovery."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock hass instance with registries."""
        hass = MagicMock()

        # Mock sensor state with temperature device class
        sensor_state = MagicMock()
        sensor_state.entity_id = "sensor.temperature_bureau"
        sensor_state.attributes = {"device_class": "temperature"}

        # Mock sensor without temperature class
        other_sensor_state = MagicMock()
        other_sensor_state.entity_id = "sensor.humidity_bureau"
        other_sensor_state.attributes = {"device_class": "humidity"}

        hass.states.get = lambda entity_id: {
            "sensor.temperature_bureau": sensor_state,
            "sensor.humidity_bureau": other_sensor_state,
            "sensor.temperature_salon": sensor_state,
        }.get(entity_id)

        return hass

    def test_get_areas_with_climate_direct_area(self, mock_hass):
        """Test getting areas with climate entities assigned directly."""
        with (
            patch("custom_components.chauffage_intelligent.config_flow.ar.async_get") as mock_ar,
            patch("custom_components.chauffage_intelligent.config_flow.er.async_get") as mock_er,
            patch("homeassistant.helpers.device_registry.async_get") as mock_dr,
        ):
            # Setup entity registry with climate entity in area
            mock_entity = MagicMock()
            mock_entity.domain = "climate"
            mock_entity.entity_id = "climate.bureau"
            mock_entity.area_id = "bureau"
            mock_entity.device_id = None

            mock_er.return_value.entities.values.return_value = [mock_entity]

            # Setup device registry (empty)
            mock_dr.return_value.async_get.return_value = None

            # Setup area registry
            mock_area = MagicMock()
            mock_area.id = "bureau"
            mock_area.name = "Bureau"
            mock_ar.return_value.async_get_area.return_value = mock_area

            result = _get_areas_with_climate(mock_hass)

            assert len(result) == 1
            assert result[0]["value"] == "bureau"
            assert result[0]["label"] == "Bureau"

    def test_get_areas_with_climate_via_device(self, mock_hass):
        """Test getting areas with climate entities via device area."""
        with (
            patch("custom_components.chauffage_intelligent.config_flow.ar.async_get") as mock_ar,
            patch("custom_components.chauffage_intelligent.config_flow.er.async_get") as mock_er,
            patch("homeassistant.helpers.device_registry.async_get") as mock_dr,
        ):
            # Setup entity registry with climate entity (no direct area, but has device)
            mock_entity = MagicMock()
            mock_entity.domain = "climate"
            mock_entity.entity_id = "climate.salon"
            mock_entity.area_id = None
            mock_entity.device_id = "device_123"

            mock_er.return_value.entities.values.return_value = [mock_entity]

            # Setup device registry with device in area
            mock_device = MagicMock()
            mock_device.area_id = "salon"
            mock_dr.return_value.async_get.return_value = mock_device

            # Setup area registry
            mock_area = MagicMock()
            mock_area.id = "salon"
            mock_area.name = "Salon"
            mock_ar.return_value.async_get_area.return_value = mock_area

            result = _get_areas_with_climate(mock_hass)

            assert len(result) == 1
            assert result[0]["value"] == "salon"
            assert result[0]["label"] == "Salon"

    def test_get_climate_entities_for_area_direct(self, mock_hass):
        """Test getting climate entities directly assigned to area."""
        with (
            patch("custom_components.chauffage_intelligent.config_flow.er.async_get") as mock_er,
            patch("homeassistant.helpers.device_registry.async_get") as mock_dr,
        ):
            # Setup entity registry
            mock_entity = MagicMock()
            mock_entity.domain = "climate"
            mock_entity.entity_id = "climate.bureau"
            mock_entity.area_id = "bureau"
            mock_entity.device_id = None

            mock_other_entity = MagicMock()
            mock_other_entity.domain = "light"
            mock_other_entity.entity_id = "light.bureau"
            mock_other_entity.area_id = "bureau"
            mock_other_entity.device_id = None

            mock_er.return_value.entities.values.return_value = [
                mock_entity,
                mock_other_entity,
            ]
            mock_dr.return_value.async_get.return_value = None

            result = _get_climate_entities_for_area(mock_hass, "bureau")

            assert result == ["climate.bureau"]

    def test_get_climate_entities_for_area_via_device(self, mock_hass):
        """Test getting climate entities via device area."""
        with (
            patch("custom_components.chauffage_intelligent.config_flow.er.async_get") as mock_er,
            patch("homeassistant.helpers.device_registry.async_get") as mock_dr,
        ):
            # Setup entity registry with climate entity (no direct area)
            mock_entity = MagicMock()
            mock_entity.domain = "climate"
            mock_entity.entity_id = "climate.salon"
            mock_entity.area_id = None
            mock_entity.device_id = "device_123"

            mock_er.return_value.entities.values.return_value = [mock_entity]

            # Setup device in area
            mock_device = MagicMock()
            mock_device.area_id = "salon"
            mock_dr.return_value.async_get.return_value = mock_device

            result = _get_climate_entities_for_area(mock_hass, "salon")

            assert result == ["climate.salon"]

    def test_get_temperature_sensors_for_area_direct(self, mock_hass):
        """Test getting temperature sensors directly assigned to area."""
        with (
            patch("custom_components.chauffage_intelligent.config_flow.er.async_get") as mock_er,
            patch("homeassistant.helpers.device_registry.async_get") as mock_dr,
        ):
            # Setup entity registry with temperature sensor
            mock_entity = MagicMock()
            mock_entity.domain = "sensor"
            mock_entity.entity_id = "sensor.temperature_bureau"
            mock_entity.area_id = "bureau"
            mock_entity.device_id = None

            mock_er.return_value.entities.values.return_value = [mock_entity]
            mock_dr.return_value.async_get.return_value = None

            result = _get_temperature_sensors_for_area(mock_hass, "bureau")

            assert result == ["sensor.temperature_bureau"]

    def test_get_temperature_sensors_for_area_via_device(self, mock_hass):
        """Test getting temperature sensors via device area."""
        with (
            patch("custom_components.chauffage_intelligent.config_flow.er.async_get") as mock_er,
            patch("homeassistant.helpers.device_registry.async_get") as mock_dr,
        ):
            # Setup entity registry with sensor (no direct area)
            mock_entity = MagicMock()
            mock_entity.domain = "sensor"
            mock_entity.entity_id = "sensor.temperature_salon"
            mock_entity.area_id = None
            mock_entity.device_id = "device_456"

            mock_er.return_value.entities.values.return_value = [mock_entity]

            # Setup device in area
            mock_device = MagicMock()
            mock_device.area_id = "salon"
            mock_dr.return_value.async_get.return_value = mock_device

            result = _get_temperature_sensors_for_area(mock_hass, "salon")

            assert result == ["sensor.temperature_salon"]

    def test_get_temperature_sensors_excludes_non_temperature(self, mock_hass):
        """Test that non-temperature sensors are excluded."""
        with (
            patch("custom_components.chauffage_intelligent.config_flow.er.async_get") as mock_er,
            patch("homeassistant.helpers.device_registry.async_get") as mock_dr,
        ):
            # Setup entity registry with humidity sensor
            mock_entity = MagicMock()
            mock_entity.domain = "sensor"
            mock_entity.entity_id = "sensor.humidity_bureau"
            mock_entity.area_id = "bureau"
            mock_entity.device_id = None

            mock_er.return_value.entities.values.return_value = [mock_entity]
            mock_dr.return_value.async_get.return_value = None

            result = _get_temperature_sensors_for_area(mock_hass, "bureau")

            assert result == []


class TestConfigFlowSelectArea:
    """Test ConfigFlow select_area step."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock hass instance."""
        hass = MagicMock()
        return hass

    @pytest.mark.asyncio
    async def test_async_step_select_area_valid_selection(self, mock_hass):
        """Test selecting a valid area navigates to configure_room."""
        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass
        flow._data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {},
        }

        with (
            patch("custom_components.chauffage_intelligent.config_flow.ar.async_get") as mock_ar,
            patch(
                "custom_components.chauffage_intelligent.config_flow._get_areas_with_climate"
            ) as mock_areas,
            patch(
                "custom_components.chauffage_intelligent.config_flow._get_climate_entities_for_area"
            ) as mock_climate,
            patch(
                "custom_components.chauffage_intelligent.config_flow._get_temperature_sensors_for_area"
            ) as mock_sensors,
        ):
            mock_area = MagicMock()
            mock_area.id = "salon"
            mock_area.name = "Salon"
            mock_ar.return_value.async_get_area.return_value = mock_area
            mock_areas.return_value = [{"value": "salon", "label": "Salon"}]
            mock_climate.return_value = ["climate.salon"]
            mock_sensors.return_value = ["sensor.temperature_salon"]

            result = await flow.async_step_select_area({"area": "salon"})

            assert result["type"] == "form"
            assert result["step_id"] == "configure_room"
            assert flow._current_area_id == "salon"
            assert flow._current_area_name == "Salon"

    @pytest.mark.asyncio
    async def test_async_step_select_area_shows_form(self, mock_hass):
        """Test select_area shows form when no input."""
        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass
        flow._data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {},
        }

        with patch(
            "custom_components.chauffage_intelligent.config_flow._get_areas_with_climate"
        ) as mock_areas:
            mock_areas.return_value = [
                {"value": "salon", "label": "Salon"},
                {"value": "bureau", "label": "Bureau"},
            ]

            result = await flow.async_step_select_area(None)

            assert result["type"] == "form"
            assert result["step_id"] == "select_area"

    @pytest.mark.asyncio
    async def test_async_step_select_area_no_areas(self, mock_hass):
        """Test select_area shows error when no areas available."""
        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass
        flow._data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {},
        }

        with patch(
            "custom_components.chauffage_intelligent.config_flow._get_areas_with_climate"
        ) as mock_areas:
            mock_areas.return_value = []

            result = await flow.async_step_select_area(None)

            assert result["type"] == "form"
            assert result["errors"]["base"] == "no_areas_available"


class TestConfigFlowConfigureRoom:
    """Test ConfigFlow configure_room step."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock hass instance."""
        hass = MagicMock()
        return hass

    @pytest.mark.asyncio
    async def test_async_step_configure_room_shows_form(self, mock_hass):
        """Test configure_room shows form when no input."""
        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass
        flow._data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {},
        }
        flow._current_area_id = "salon"
        flow._current_area_name = "Salon"

        with (
            patch(
                "custom_components.chauffage_intelligent.config_flow._get_climate_entities_for_area"
            ) as mock_climate,
            patch(
                "custom_components.chauffage_intelligent.config_flow._get_temperature_sensors_for_area"
            ) as mock_sensors,
        ):
            mock_climate.return_value = ["climate.salon"]
            mock_sensors.return_value = ["sensor.temperature_salon"]

            result = await flow.async_step_configure_room(None)

            assert result["type"] == "form"
            assert result["step_id"] == "configure_room"
            assert result["description_placeholders"]["area_name"] == "Salon"

    @pytest.mark.asyncio
    async def test_async_step_configure_room_with_string_radiateur(self, mock_hass):
        """Test configure_room converts string radiateur to list."""
        flow = ChauffageIntelligentConfigFlow()
        flow.hass = mock_hass
        flow._data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {},
        }
        flow._current_area_id = "salon"
        flow._current_area_name = "Salon"

        user_input = {
            CONF_PIECE_TYPE: "salon",
            CONF_PIECE_RADIATEURS: "climate.salon",  # String instead of list
            "temp_confort": 20,
            "temp_eco": 18,
            "temp_hors_gel": 7,
        }

        result = await flow.async_step_configure_room(user_input)

        assert "salon" in flow._data[CONF_PIECES]
        # Verify it was converted to a list
        assert flow._data[CONF_PIECES]["salon"][CONF_PIECE_RADIATEURS] == ["climate.salon"]
        assert result["type"] == "form"
        assert result["step_id"] == "room_menu"


class TestOptionsFlowAddRoom:
    """Test OptionsFlow add_room step."""

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry."""
        entry = MagicMock()
        entry.data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {},
        }
        entry.entry_id = "test_entry_id"
        return entry

    @pytest.fixture
    def mock_hass(self):
        """Create a mock hass instance."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        hass.config_entries.async_reload = AsyncMock()
        return hass

    @pytest.mark.asyncio
    async def test_async_step_add_room_shows_form(self, mock_config_entry, mock_hass):
        """Test add_room shows form when no input."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass
            flow._current_area_id = "salon"
            flow._current_area_name = "Salon"

            with (
                patch(
                    "custom_components.chauffage_intelligent.config_flow._get_climate_entities_for_area"
                ) as mock_climate,
                patch(
                    "custom_components.chauffage_intelligent.config_flow._get_temperature_sensors_for_area"
                ) as mock_sensors,
            ):
                mock_climate.return_value = ["climate.salon"]
                mock_sensors.return_value = ["sensor.temperature_salon"]

                result = await flow.async_step_add_room(None)

                assert result["type"] == "form"
                assert result["step_id"] == "add_room"
                assert result["description_placeholders"]["area_name"] == "Salon"

    @pytest.mark.asyncio
    async def test_async_step_add_room_submits(self, mock_config_entry, mock_hass):
        """Test add_room creates room and updates config entry."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass
            flow._current_area_id = "salon"
            flow._current_area_name = "Salon"

            user_input = {
                CONF_PIECE_TYPE: "salon",
                CONF_PIECE_RADIATEURS: ["climate.salon"],
                CONF_PIECE_SONDE: "sensor.temperature_salon",
                "temp_confort": 20,
                "temp_eco": 18,
                "temp_hors_gel": 7,
            }

            result = await flow.async_step_add_room(user_input)

            assert result["type"] == "create_entry"
            assert "salon" in flow._data[CONF_PIECES]
            mock_hass.config_entries.async_update_entry.assert_called_once()
            mock_hass.config_entries.async_reload.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_step_add_room_string_radiateur(self, mock_config_entry, mock_hass):
        """Test add_room converts string radiateur to list."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass
            flow._current_area_id = "bureau"
            flow._current_area_name = "Bureau"

            user_input = {
                CONF_PIECE_TYPE: "bureau",
                CONF_PIECE_RADIATEURS: "climate.bureau",  # String
                "temp_confort": 19,
                "temp_eco": 17,
                "temp_hors_gel": 7,
            }

            result = await flow.async_step_add_room(user_input)

            assert result["type"] == "create_entry"
            assert flow._data[CONF_PIECES]["bureau"][CONF_PIECE_RADIATEURS] == ["climate.bureau"]


class TestOptionsFlowSelectAndModifyRoom:
    """Test OptionsFlow select_room and modify_room steps."""

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry with a room."""
        entry = MagicMock()
        entry.data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {
                "bureau": {
                    CONF_PIECE_NAME: "Bureau",
                    CONF_PIECE_AREA_ID: "bureau",
                    CONF_PIECE_TYPE: "bureau",
                    CONF_PIECE_RADIATEURS: ["climate.bureau"],
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

        # Mock climate states
        climate_state = MagicMock()
        climate_state.entity_id = "climate.bureau"

        # Mock sensor states
        sensor_state = MagicMock()
        sensor_state.entity_id = "sensor.temperature_bureau"
        sensor_state.attributes = {"device_class": "temperature"}

        domain_states = {
            "climate": [climate_state],
            "sensor": [sensor_state],
        }
        hass.states.async_all = lambda domain: domain_states.get(domain, [])
        hass.config_entries.async_update_entry = MagicMock()
        hass.config_entries.async_reload = AsyncMock()
        return hass

    @pytest.mark.asyncio
    async def test_async_step_select_room_shows_form(self, mock_config_entry, mock_hass):
        """Test select_room shows form with room options."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass

            result = await flow.async_step_select_room(None)

            assert result["type"] == "form"
            assert result["step_id"] == "select_room"

    @pytest.mark.asyncio
    async def test_async_step_select_room_selects_room(self, mock_config_entry, mock_hass):
        """Test selecting a room navigates to modify_room."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass

            with (
                patch(
                    "custom_components.chauffage_intelligent.config_flow._get_climate_entities_for_area"
                ) as mock_climate,
                patch(
                    "custom_components.chauffage_intelligent.config_flow._get_temperature_sensors_for_area"
                ) as mock_sensors,
            ):
                mock_climate.return_value = ["climate.bureau"]
                mock_sensors.return_value = ["sensor.temperature_bureau"]

                result = await flow.async_step_select_room({"room": "bureau"})

                assert result["type"] == "form"
                assert result["step_id"] == "modify_room"
                assert flow._selected_room == "bureau"

    @pytest.mark.asyncio
    async def test_async_step_modify_room_shows_form(self, mock_config_entry, mock_hass):
        """Test modify_room shows form with current values."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass
            flow._selected_room = "bureau"

            with (
                patch(
                    "custom_components.chauffage_intelligent.config_flow._get_climate_entities_for_area"
                ) as mock_climate,
                patch(
                    "custom_components.chauffage_intelligent.config_flow._get_temperature_sensors_for_area"
                ) as mock_sensors,
            ):
                mock_climate.return_value = ["climate.bureau"]
                mock_sensors.return_value = ["sensor.temperature_bureau"]

                result = await flow.async_step_modify_room(None)

                assert result["type"] == "form"
                assert result["step_id"] == "modify_room"
                assert result["description_placeholders"]["room_name"] == "Bureau"

    @pytest.mark.asyncio
    async def test_async_step_modify_room_no_selected_room(self, mock_config_entry, mock_hass):
        """Test modify_room redirects to select_room if no room selected."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass
            flow._selected_room = None

            result = await flow.async_step_modify_room(None)

            assert result["type"] == "form"
            assert result["step_id"] == "select_room"

    @pytest.mark.asyncio
    async def test_async_step_modify_room_submits(self, mock_config_entry, mock_hass):
        """Test modify_room updates room and config entry."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass
            flow._selected_room = "bureau"

            user_input = {
                CONF_PIECE_TYPE: "bureau",
                CONF_PIECE_RADIATEURS: ["climate.bureau", "climate.bureau2"],
                CONF_PIECE_SONDE: "sensor.temperature_bureau",
                "temp_confort": 21,
                "temp_eco": 18,
                "temp_hors_gel": 8,
            }

            result = await flow.async_step_modify_room(user_input)

            assert result["type"] == "create_entry"
            assert flow._data[CONF_PIECES]["bureau"][CONF_PIECE_TEMPERATURES][MODE_CONFORT] == 21
            mock_hass.config_entries.async_update_entry.assert_called_once()
            mock_hass.config_entries.async_reload.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_step_modify_room_string_radiateur(self, mock_config_entry, mock_hass):
        """Test modify_room converts string radiateur to list."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass
            flow._selected_room = "bureau"

            user_input = {
                CONF_PIECE_TYPE: "bureau",
                CONF_PIECE_RADIATEURS: "climate.bureau",  # String
                "temp_confort": 19,
                "temp_eco": 17,
                "temp_hors_gel": 7,
            }

            result = await flow.async_step_modify_room(user_input)

            assert result["type"] == "create_entry"
            assert flow._data[CONF_PIECES]["bureau"][CONF_PIECE_RADIATEURS] == ["climate.bureau"]

    @pytest.mark.asyncio
    async def test_async_step_modify_room_fallback_climate_entities(
        self, mock_config_entry, mock_hass
    ):
        """Test modify_room falls back to all climate entities when none in area."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass
            flow._selected_room = "bureau"

            with (
                patch(
                    "custom_components.chauffage_intelligent.config_flow._get_climate_entities_for_area"
                ) as mock_climate,
                patch(
                    "custom_components.chauffage_intelligent.config_flow._get_temperature_sensors_for_area"
                ) as mock_sensors,
            ):
                # Return empty to trigger fallback
                mock_climate.return_value = []
                mock_sensors.return_value = []

                result = await flow.async_step_modify_room(None)

                assert result["type"] == "form"
                assert result["step_id"] == "modify_room"


class TestOptionsFlowDeleteRoom:
    """Test OptionsFlow delete_room step."""

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry with a room."""
        entry = MagicMock()
        entry.data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {
                "bureau": {
                    CONF_PIECE_NAME: "Bureau",
                    CONF_PIECE_AREA_ID: "bureau",
                    CONF_PIECE_TYPE: "bureau",
                    CONF_PIECE_RADIATEURS: ["climate.bureau"],
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
        hass.config_entries.async_update_entry = MagicMock()
        hass.config_entries.async_reload = AsyncMock()
        return hass

    @pytest.mark.asyncio
    async def test_async_step_delete_room_shows_form(self, mock_config_entry, mock_hass):
        """Test delete_room shows form with room options."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass

            result = await flow.async_step_delete_room(None)

            assert result["type"] == "form"
            assert result["step_id"] == "delete_room"

    @pytest.mark.asyncio
    async def test_async_step_delete_room_confirms(self, mock_config_entry, mock_hass):
        """Test delete_room deletes room when confirmed."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass

            result = await flow.async_step_delete_room({"room": "bureau", "confirm": True})

            assert result["type"] == "create_entry"
            assert "bureau" not in flow._data[CONF_PIECES]
            mock_hass.config_entries.async_update_entry.assert_called_once()
            mock_hass.config_entries.async_reload.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_step_delete_room_cancels(self, mock_config_entry, mock_hass):
        """Test delete_room returns to init when cancelled."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass

            result = await flow.async_step_delete_room({"room": "bureau", "confirm": False})

            assert result["type"] == "form"
            assert result["step_id"] == "init"
            # Room should still exist
            assert "bureau" in flow._data[CONF_PIECES]


class TestOptionsFlowSettings:
    """Test OptionsFlow settings step."""

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry."""
        entry = MagicMock()
        entry.data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_UPDATE_INTERVAL: 300,
            CONF_SECURITY_FACTOR: 1.2,
            CONF_MIN_PREHEAT_TIME: 30,
            CONF_PIECES: {},
        }
        entry.entry_id = "test_entry_id"
        return entry

    @pytest.fixture
    def mock_hass(self):
        """Create a mock hass instance."""
        hass = MagicMock()

        # Mock calendar states
        calendar_state = MagicMock()
        calendar_state.entity_id = "calendar.google_home"

        calendar_state2 = MagicMock()
        calendar_state2.entity_id = "calendar.work"

        # Mock device tracker states
        tracker_state = MagicMock()
        tracker_state.entity_id = "device_tracker.phone"

        tracker_state2 = MagicMock()
        tracker_state2.entity_id = "device_tracker.tablet"

        domain_states = {
            "calendar": [calendar_state, calendar_state2],
            "device_tracker": [tracker_state, tracker_state2],
        }
        hass.states.async_all = lambda domain: domain_states.get(domain, [])
        hass.config_entries.async_update_entry = MagicMock()
        hass.config_entries.async_reload = AsyncMock()
        return hass

    @pytest.mark.asyncio
    async def test_async_step_settings_shows_form(self, mock_config_entry, mock_hass):
        """Test settings shows form with current values."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass

            result = await flow.async_step_settings(None)

            assert result["type"] == "form"
            assert result["step_id"] == "settings"

    @pytest.mark.asyncio
    async def test_async_step_settings_submits(self, mock_config_entry, mock_hass):
        """Test settings updates config entry."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass

            user_input = {
                CONF_CALENDAR: "calendar.work",
                CONF_PRESENCE_TRACKERS: ["device_tracker.phone", "device_tracker.tablet"],
                CONF_UPDATE_INTERVAL: 10,
                CONF_SECURITY_FACTOR: 1.5,
                CONF_MIN_PREHEAT_TIME: 45,
            }

            result = await flow.async_step_settings(user_input)

            assert result["type"] == "create_entry"
            assert flow._data[CONF_CALENDAR] == "calendar.work"
            assert flow._data[CONF_PRESENCE_TRACKERS] == [
                "device_tracker.phone",
                "device_tracker.tablet",
            ]
            assert flow._data[CONF_UPDATE_INTERVAL] == 600  # 10 * 60
            assert flow._data[CONF_SECURITY_FACTOR] == 1.5
            assert flow._data[CONF_MIN_PREHEAT_TIME] == 45
            mock_hass.config_entries.async_update_entry.assert_called_once()
            mock_hass.config_entries.async_reload.assert_called_once()


class TestOptionsFlowSelectAreaForAdd:
    """Test OptionsFlow select_area step when adding a room."""

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry."""
        entry = MagicMock()
        entry.data = {
            CONF_CALENDAR: "calendar.google_home",
            CONF_PRESENCE_TRACKERS: ["device_tracker.phone"],
            CONF_PIECES: {},
        }
        entry.entry_id = "test_entry_id"
        return entry

    @pytest.fixture
    def mock_hass(self):
        """Create a mock hass instance."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        hass.config_entries.async_reload = AsyncMock()
        return hass

    @pytest.mark.asyncio
    async def test_async_step_select_area_navigates_to_add_room(self, mock_config_entry, mock_hass):
        """Test selecting an area navigates to add_room."""
        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass

            with (
                patch(
                    "custom_components.chauffage_intelligent.config_flow.ar.async_get"
                ) as mock_ar,
                patch(
                    "custom_components.chauffage_intelligent.config_flow._get_areas_with_climate"
                ) as mock_areas,
                patch(
                    "custom_components.chauffage_intelligent.config_flow._get_climate_entities_for_area"
                ) as mock_climate,
                patch(
                    "custom_components.chauffage_intelligent.config_flow._get_temperature_sensors_for_area"
                ) as mock_sensors,
            ):
                mock_area = MagicMock()
                mock_area.id = "salon"
                mock_area.name = "Salon"
                mock_ar.return_value.async_get_area.return_value = mock_area
                mock_areas.return_value = [{"value": "salon", "label": "Salon"}]
                mock_climate.return_value = ["climate.salon"]
                mock_sensors.return_value = ["sensor.temperature_salon"]

                result = await flow.async_step_select_area({"area": "salon"})

                assert result["type"] == "form"
                assert result["step_id"] == "add_room"
                assert flow._current_area_id == "salon"
                assert flow._current_area_name == "Salon"

    @pytest.mark.asyncio
    async def test_async_step_select_area_already_configured(self, mock_config_entry, mock_hass):
        """Test selecting already configured area shows error."""
        mock_config_entry.data[CONF_PIECES] = {"salon": {CONF_PIECE_NAME: "Salon"}}

        with patch.object(
            ChauffageIntelligentOptionsFlow,
            "config_entry",
            new_callable=lambda: property(lambda self: mock_config_entry),
        ):
            flow = ChauffageIntelligentOptionsFlow(mock_config_entry)
            flow.hass = mock_hass

            with (
                patch(
                    "custom_components.chauffage_intelligent.config_flow.ar.async_get"
                ) as mock_ar,
                patch(
                    "custom_components.chauffage_intelligent.config_flow._get_areas_with_climate"
                ) as mock_areas,
            ):
                mock_area = MagicMock()
                mock_area.id = "salon"
                mock_area.name = "Salon"
                mock_ar.return_value.async_get_area.return_value = mock_area
                # Include another area so it doesn't abort
                mock_areas.return_value = [
                    {"value": "salon", "label": "Salon"},
                    {"value": "bureau", "label": "Bureau"},
                ]

                result = await flow.async_step_select_area({"area": "salon"})

                assert result["type"] == "form"
                assert result["errors"]["base"] == "area_already_configured"
