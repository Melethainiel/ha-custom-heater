"""Config flow for Chauffage Intelligent integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_CALENDAR,
    CONF_DERIVATIVE_WINDOW,
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
    DEFAULT_DERIVATIVE_WINDOW,
    DEFAULT_MIN_PREHEAT_TIME,
    DEFAULT_SECURITY_FACTOR,
    DEFAULT_TEMPERATURES,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MODE_CONFORT,
    MODE_ECO,
    MODE_HORS_GEL,
    ROOM_TYPES,
)

_LOGGER = logging.getLogger(__name__)

# Menu actions
ACTION_ADD_ROOM = "add_room"
ACTION_FINISH = "finish"


def _get_areas_with_climate(hass) -> list[dict[str, str]]:
    """Get areas that have climate entities."""
    area_reg = ar.async_get(hass)
    entity_reg = er.async_get(hass)

    # Find all areas with climate entities
    areas_with_climate = set()
    for entity in entity_reg.entities.values():
        if entity.domain == "climate" and entity.area_id:
            areas_with_climate.add(entity.area_id)

    # Also check device areas
    from homeassistant.helpers import device_registry as dr

    device_reg = dr.async_get(hass)

    for entity in entity_reg.entities.values():
        if entity.domain == "climate" and entity.device_id:
            device = device_reg.async_get(entity.device_id)
            if device and device.area_id:
                areas_with_climate.add(device.area_id)

    # Build list of area options
    area_options = []
    for area_id in areas_with_climate:
        area = area_reg.async_get_area(area_id)
        if area:
            area_options.append({"value": area.id, "label": area.name})

    return sorted(area_options, key=lambda x: x["label"])


def _get_climate_entities_for_area(hass, area_id: str) -> list[str]:
    """Get climate entity IDs for a specific area."""
    entity_reg = er.async_get(hass)
    from homeassistant.helpers import device_registry as dr

    device_reg = dr.async_get(hass)

    climate_entities = []
    for entity in entity_reg.entities.values():
        if entity.domain != "climate":
            continue

        # Check direct area assignment
        if entity.area_id == area_id:
            climate_entities.append(entity.entity_id)
            continue

        # Check device area
        if entity.device_id:
            device = device_reg.async_get(entity.device_id)
            if device and device.area_id == area_id:
                climate_entities.append(entity.entity_id)

    return climate_entities


def _get_temperature_sensors_for_area(hass, area_id: str) -> list[str]:
    """Get temperature sensor entity IDs for a specific area."""
    entity_reg = er.async_get(hass)
    from homeassistant.helpers import device_registry as dr

    device_reg = dr.async_get(hass)

    sensors = []
    for entity in entity_reg.entities.values():
        if entity.domain != "sensor":
            continue

        # Check if it's a temperature sensor
        state = hass.states.get(entity.entity_id)
        if not state or state.attributes.get("device_class") != "temperature":
            continue

        # Check direct area assignment
        if entity.area_id == area_id:
            sensors.append(entity.entity_id)
            continue

        # Check device area
        if entity.device_id:
            device = device_reg.async_get(entity.device_id)
            if device and device.area_id == area_id:
                sensors.append(entity.entity_id)

    return sensors


class ChauffageIntelligentConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Chauffage Intelligent."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._current_area_id: str | None = None
        self._current_area_name: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step - global configuration."""
        errors = {}

        if user_input is not None:
            self._data = {
                CONF_CALENDAR: user_input[CONF_CALENDAR],
                CONF_PRESENCE_TRACKERS: user_input[CONF_PRESENCE_TRACKERS],
                CONF_UPDATE_INTERVAL: user_input.get(
                    CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL // 60
                )
                * 60,
                CONF_SECURITY_FACTOR: user_input.get(CONF_SECURITY_FACTOR, DEFAULT_SECURITY_FACTOR),
                CONF_MIN_PREHEAT_TIME: user_input.get(
                    CONF_MIN_PREHEAT_TIME, DEFAULT_MIN_PREHEAT_TIME
                ),
                CONF_DERIVATIVE_WINDOW: DEFAULT_DERIVATIVE_WINDOW,
                CONF_PIECES: {},
            }
            return await self.async_step_room_menu()

        # Get available calendars
        calendars = [state.entity_id for state in self.hass.states.async_all("calendar")]

        if not calendars:
            errors["base"] = "no_calendar"

        # Get available device trackers
        trackers = [state.entity_id for state in self.hass.states.async_all("device_tracker")]

        if not trackers:
            errors["base"] = "no_trackers"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_CALENDAR): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=calendars,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Required(CONF_PRESENCE_TRACKERS): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=trackers,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional(
                    CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL // 60
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=60, unit_of_measurement="min"),
                ),
                vol.Optional(
                    CONF_SECURITY_FACTOR, default=DEFAULT_SECURITY_FACTOR
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1.0, max=2.0, step=0.1),
                ),
                vol.Optional(
                    CONF_MIN_PREHEAT_TIME, default=DEFAULT_MIN_PREHEAT_TIME
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=10, max=120, unit_of_measurement="min"),
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_room_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Show menu to add room or finish configuration."""
        errors = {}

        if user_input is not None:
            action = user_input.get("action")

            if action == ACTION_FINISH:
                if not self._data.get(CONF_PIECES):
                    errors["base"] = "no_rooms"
                else:
                    return self.async_create_entry(
                        title="Chauffage Intelligent",
                        data=self._data,
                    )
            elif action == ACTION_ADD_ROOM:
                return await self.async_step_select_area()

        num_rooms = len(self._data.get(CONF_PIECES, {}))

        # Build menu options
        menu_options = [
            {"value": ACTION_ADD_ROOM, "label": "Ajouter une pièce"},
        ]

        # Only show finish option if at least one room is configured
        if num_rooms > 0:
            menu_options.append({"value": ACTION_FINISH, "label": "Terminer la configuration"})

        data_schema = vol.Schema(
            {
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=menu_options,
                        mode=selector.SelectSelectorMode.LIST,
                    ),
                ),
            }
        )

        return self.async_show_form(
            step_id="room_menu",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"num_rooms": str(num_rooms)},
        )

    async def async_step_select_area(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle area selection step."""
        errors = {}

        if user_input is not None:
            area_id = user_input["area"]
            area_reg = ar.async_get(self.hass)
            area = area_reg.async_get_area(area_id)

            if area:
                # Check if area is already configured
                if area_id in self._data.get(CONF_PIECES, {}):
                    errors["base"] = "area_already_configured"
                else:
                    self._current_area_id = area_id
                    self._current_area_name = area.name
                    return await self.async_step_configure_room()

        # Get areas with climate entities, excluding already configured ones
        area_options = _get_areas_with_climate(self.hass)
        configured_areas = set(self._data.get(CONF_PIECES, {}).keys())
        area_options = [a for a in area_options if a["value"] not in configured_areas]

        if not area_options:
            errors["base"] = "no_areas_available"

        data_schema = vol.Schema(
            {
                vol.Required("area"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=area_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
            }
        )

        return self.async_show_form(
            step_id="select_area",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_configure_room(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle room configuration step."""
        errors = {}

        if user_input is not None:
            piece_type = user_input[CONF_PIECE_TYPE]
            radiateurs = user_input[CONF_PIECE_RADIATEURS]

            # Ensure radiateurs is a list
            if isinstance(radiateurs, str):
                radiateurs = [radiateurs]

            self._data[CONF_PIECES][self._current_area_id] = {
                CONF_PIECE_NAME: self._current_area_name,
                CONF_PIECE_AREA_ID: self._current_area_id,
                CONF_PIECE_TYPE: piece_type,
                CONF_PIECE_RADIATEURS: radiateurs,
                CONF_PIECE_SONDE: user_input.get(CONF_PIECE_SONDE),
                CONF_PIECE_TEMPERATURES: {
                    MODE_CONFORT: user_input.get(
                        "temp_confort",
                        DEFAULT_TEMPERATURES[piece_type][MODE_CONFORT],
                    ),
                    MODE_ECO: user_input.get(
                        "temp_eco",
                        DEFAULT_TEMPERATURES[piece_type][MODE_ECO],
                    ),
                    MODE_HORS_GEL: user_input.get(
                        "temp_hors_gel",
                        DEFAULT_TEMPERATURES[piece_type][MODE_HORS_GEL],
                    ),
                },
            }

            # Reset current area and go back to menu
            self._current_area_id = None
            self._current_area_name = None
            return await self.async_step_room_menu()

        # Get climate entities for this area
        climate_entities = _get_climate_entities_for_area(self.hass, self._current_area_id or "")

        # Get temperature sensors for this area
        temp_sensors = _get_temperature_sensors_for_area(self.hass, self._current_area_id or "")

        data_schema = vol.Schema(
            {
                vol.Required(CONF_PIECE_TYPE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=ROOM_TYPES,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Required(CONF_PIECE_RADIATEURS): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=climate_entities,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional(CONF_PIECE_SONDE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=temp_sensors,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional("temp_confort", default=19): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=15, max=25, unit_of_measurement="°C"),
                ),
                vol.Optional("temp_eco", default=17): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=12, max=20, unit_of_measurement="°C"),
                ),
                vol.Optional("temp_hors_gel", default=7): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=5, max=12, unit_of_measurement="°C"),
                ),
            }
        )

        return self.async_show_form(
            step_id="configure_room",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"area_name": self._current_area_name},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return ChauffageIntelligentOptionsFlow(config_entry)


class ChauffageIntelligentOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Chauffage Intelligent."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        # Note: self.config_entry is provided by the parent class in newer HA versions
        self._data: dict[str, Any] = dict(config_entry.data)
        self._selected_room: str | None = None
        self._current_area_id: str | None = None
        self._current_area_name: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Manage the options."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "add_room":
                return await self.async_step_select_area()
            elif action == "modify_room":
                return await self.async_step_select_room()
            elif action == "delete_room":
                return await self.async_step_delete_room()
            elif action == "modify_settings":
                return await self.async_step_settings()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": "add_room", "label": "Ajouter une pièce"},
                                {"value": "modify_room", "label": "Modifier une pièce"},
                                {"value": "delete_room", "label": "Supprimer une pièce"},
                                {"value": "modify_settings", "label": "Modifier les paramètres"},
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        ),
                    ),
                }
            ),
        )

    async def async_step_select_area(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle area selection for adding a new room."""
        errors = {}

        if user_input is not None:
            area_id = user_input["area"]
            area_reg = ar.async_get(self.hass)
            area = area_reg.async_get_area(area_id)

            if area:
                if area_id in self._data.get(CONF_PIECES, {}):
                    errors["base"] = "area_already_configured"
                else:
                    self._current_area_id = area_id
                    self._current_area_name = area.name
                    return await self.async_step_add_room()

        # Get areas with climate entities, excluding already configured ones
        area_options = _get_areas_with_climate(self.hass)
        configured_areas = set(self._data.get(CONF_PIECES, {}).keys())
        area_options = [a for a in area_options if a["value"] not in configured_areas]

        if not area_options:
            return self.async_abort(reason="no_areas_available")

        data_schema = vol.Schema(
            {
                vol.Required("area"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=area_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
            }
        )

        return self.async_show_form(
            step_id="select_area",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_add_room(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle adding a room in options."""
        errors = {}

        if user_input is not None:
            piece_type = user_input[CONF_PIECE_TYPE]
            radiateurs = user_input[CONF_PIECE_RADIATEURS]

            if isinstance(radiateurs, str):
                radiateurs = [radiateurs]

            if CONF_PIECES not in self._data:
                self._data[CONF_PIECES] = {}

            self._data[CONF_PIECES][self._current_area_id] = {
                CONF_PIECE_NAME: self._current_area_name,
                CONF_PIECE_AREA_ID: self._current_area_id,
                CONF_PIECE_TYPE: piece_type,
                CONF_PIECE_RADIATEURS: radiateurs,
                CONF_PIECE_SONDE: user_input.get(CONF_PIECE_SONDE),
                CONF_PIECE_TEMPERATURES: {
                    MODE_CONFORT: user_input.get(
                        "temp_confort",
                        DEFAULT_TEMPERATURES[piece_type][MODE_CONFORT],
                    ),
                    MODE_ECO: user_input.get(
                        "temp_eco",
                        DEFAULT_TEMPERATURES[piece_type][MODE_ECO],
                    ),
                    MODE_HORS_GEL: user_input.get(
                        "temp_hors_gel",
                        DEFAULT_TEMPERATURES[piece_type][MODE_HORS_GEL],
                    ),
                },
            }

            # Update the config entry
            self.hass.config_entries.async_update_entry(self.config_entry, data=self._data)
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)

            return self.async_create_entry(title="", data={})

        # Get climate entities for this area
        climate_entities = _get_climate_entities_for_area(self.hass, self._current_area_id or "")

        # Get temperature sensors for this area
        temp_sensors = _get_temperature_sensors_for_area(self.hass, self._current_area_id or "")

        data_schema = vol.Schema(
            {
                vol.Required(CONF_PIECE_TYPE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=ROOM_TYPES,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Required(CONF_PIECE_RADIATEURS): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=climate_entities,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional(CONF_PIECE_SONDE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=temp_sensors,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional("temp_confort", default=19): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=15, max=25, unit_of_measurement="°C"),
                ),
                vol.Optional("temp_eco", default=17): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=12, max=20, unit_of_measurement="°C"),
                ),
                vol.Optional("temp_hors_gel", default=7): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=5, max=12, unit_of_measurement="°C"),
                ),
            }
        )

        return self.async_show_form(
            step_id="add_room",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"area_name": self._current_area_name},
        )

    async def async_step_select_room(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle selecting a room to modify."""
        pieces = self._data.get(CONF_PIECES, {})

        if not pieces:
            return self.async_abort(reason="no_rooms")

        if user_input is not None:
            self._selected_room = user_input["room"]
            return await self.async_step_modify_room()

        room_options = [
            {"value": room_id, "label": room_config.get(CONF_PIECE_NAME, room_id)}
            for room_id, room_config in pieces.items()
        ]

        return self.async_show_form(
            step_id="select_room",
            data_schema=vol.Schema(
                {
                    vol.Required("room"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=room_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                }
            ),
        )

    async def async_step_modify_room(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle modifying a room."""
        if self._selected_room is None:
            return await self.async_step_select_room()

        room_config = self._data[CONF_PIECES].get(self._selected_room, {})
        temps = room_config.get(CONF_PIECE_TEMPERATURES, {})

        if user_input is not None:
            piece_type = user_input[CONF_PIECE_TYPE]
            radiateurs = user_input[CONF_PIECE_RADIATEURS]

            if isinstance(radiateurs, str):
                radiateurs = [radiateurs]

            # Update the room
            self._data[CONF_PIECES][self._selected_room] = {
                CONF_PIECE_NAME: room_config.get(CONF_PIECE_NAME),
                CONF_PIECE_AREA_ID: room_config.get(CONF_PIECE_AREA_ID, self._selected_room),
                CONF_PIECE_TYPE: piece_type,
                CONF_PIECE_RADIATEURS: radiateurs,
                CONF_PIECE_SONDE: user_input.get(CONF_PIECE_SONDE),
                CONF_PIECE_TEMPERATURES: {
                    MODE_CONFORT: user_input.get("temp_confort", 19),
                    MODE_ECO: user_input.get("temp_eco", 17),
                    MODE_HORS_GEL: user_input.get("temp_hors_gel", 7),
                },
            }

            # Update the config entry
            self.hass.config_entries.async_update_entry(self.config_entry, data=self._data)
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)

            return self.async_create_entry(title="", data={})

        # Get climate entities for this area
        area_id = room_config.get(CONF_PIECE_AREA_ID, self._selected_room) or ""
        climate_entities = _get_climate_entities_for_area(self.hass, area_id)

        # If no entities found in area, fall back to all climate entities
        if not climate_entities:
            climate_entities = [state.entity_id for state in self.hass.states.async_all("climate")]

        # Get temperature sensors for this area
        temp_sensors = _get_temperature_sensors_for_area(self.hass, area_id)

        # If no sensors found in area, fall back to all temperature sensors
        if not temp_sensors:
            temp_sensors = [
                state.entity_id
                for state in self.hass.states.async_all("sensor")
                if state.attributes.get("device_class") == "temperature"
            ]

        # Get current radiateurs (handle both old single format and new list format)
        current_radiateurs = room_config.get(CONF_PIECE_RADIATEURS, [])
        if isinstance(current_radiateurs, str):
            current_radiateurs = [current_radiateurs]

        # Pre-fill with current values
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_PIECE_TYPE,
                    default=room_config.get(CONF_PIECE_TYPE, "autre"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=ROOM_TYPES,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Required(
                    CONF_PIECE_RADIATEURS,
                    default=current_radiateurs,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=climate_entities,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional(
                    CONF_PIECE_SONDE,
                    default=room_config.get(CONF_PIECE_SONDE, ""),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=temp_sensors,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional(
                    "temp_confort",
                    default=temps.get(MODE_CONFORT, 19),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=15, max=25, unit_of_measurement="°C"),
                ),
                vol.Optional(
                    "temp_eco",
                    default=temps.get(MODE_ECO, 17),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=12, max=20, unit_of_measurement="°C"),
                ),
                vol.Optional(
                    "temp_hors_gel",
                    default=temps.get(MODE_HORS_GEL, 7),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=5, max=12, unit_of_measurement="°C"),
                ),
            }
        )

        return self.async_show_form(
            step_id="modify_room",
            data_schema=data_schema,
            description_placeholders={
                "room_name": room_config.get(CONF_PIECE_NAME, self._selected_room)
            },
        )

    async def async_step_delete_room(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle deleting a room."""
        pieces = self._data.get(CONF_PIECES, {})

        if not pieces:
            return self.async_abort(reason="no_rooms")

        if user_input is not None:
            room_to_delete = user_input["room"]

            if user_input.get("confirm"):
                # Delete the room
                del self._data[CONF_PIECES][room_to_delete]

                # Update the config entry
                self.hass.config_entries.async_update_entry(self.config_entry, data=self._data)
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)

                return self.async_create_entry(title="", data={})
            else:
                # User cancelled
                return await self.async_step_init()

        room_options = [
            {"value": room_id, "label": room_config.get(CONF_PIECE_NAME, room_id)}
            for room_id, room_config in pieces.items()
        ]

        return self.async_show_form(
            step_id="delete_room",
            data_schema=vol.Schema(
                {
                    vol.Required("room"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=room_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                    vol.Required("confirm", default=False): selector.BooleanSelector(),
                }
            ),
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle modifying global settings."""
        if user_input is not None:
            # Update settings
            self._data[CONF_CALENDAR] = user_input[CONF_CALENDAR]
            self._data[CONF_PRESENCE_TRACKERS] = user_input[CONF_PRESENCE_TRACKERS]
            self._data[CONF_UPDATE_INTERVAL] = (
                user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL // 60) * 60
            )
            self._data[CONF_SECURITY_FACTOR] = user_input.get(
                CONF_SECURITY_FACTOR, DEFAULT_SECURITY_FACTOR
            )
            self._data[CONF_MIN_PREHEAT_TIME] = user_input.get(
                CONF_MIN_PREHEAT_TIME, DEFAULT_MIN_PREHEAT_TIME
            )

            # Update the config entry
            self.hass.config_entries.async_update_entry(self.config_entry, data=self._data)
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)

            return self.async_create_entry(title="", data={})

        # Get available calendars
        calendars = [state.entity_id for state in self.hass.states.async_all("calendar")]

        # Get available device trackers
        trackers = [state.entity_id for state in self.hass.states.async_all("device_tracker")]

        current_interval = self._data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_CALENDAR,
                    default=self._data.get(CONF_CALENDAR, ""),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=calendars,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Required(
                    CONF_PRESENCE_TRACKERS,
                    default=self._data.get(CONF_PRESENCE_TRACKERS, []),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=trackers,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=current_interval // 60,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=60, unit_of_measurement="min"),
                ),
                vol.Optional(
                    CONF_SECURITY_FACTOR,
                    default=self._data.get(CONF_SECURITY_FACTOR, DEFAULT_SECURITY_FACTOR),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1.0, max=2.0, step=0.1),
                ),
                vol.Optional(
                    CONF_MIN_PREHEAT_TIME,
                    default=self._data.get(CONF_MIN_PREHEAT_TIME, DEFAULT_MIN_PREHEAT_TIME),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=10, max=120, unit_of_measurement="min"),
                ),
            }
        )

        return self.async_show_form(
            step_id="settings",
            data_schema=data_schema,
        )
