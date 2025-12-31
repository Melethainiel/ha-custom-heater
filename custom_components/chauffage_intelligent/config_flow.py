"""Config flow for Chauffage Intelligent integration."""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CALENDAR,
    CONF_DERIVATIVE_WINDOW,
    CONF_MIN_PREHEAT_TIME,
    CONF_PIECE_ID,
    CONF_PIECE_NAME,
    CONF_PIECE_RADIATEUR,
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


def _slugify(text: str) -> str:
    """Create a slug from text."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "_", text)
    return text


class ChauffageIntelligentConfigFlow(
    config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle a config flow for Chauffage Intelligent."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            self._data = {
                CONF_CALENDAR: user_input[CONF_CALENDAR],
                CONF_PRESENCE_TRACKERS: user_input[CONF_PRESENCE_TRACKERS],
                CONF_UPDATE_INTERVAL: user_input.get(
                    CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL // 60
                )
                * 60,
                CONF_SECURITY_FACTOR: user_input.get(
                    CONF_SECURITY_FACTOR, DEFAULT_SECURITY_FACTOR
                ),
                CONF_MIN_PREHEAT_TIME: user_input.get(
                    CONF_MIN_PREHEAT_TIME, DEFAULT_MIN_PREHEAT_TIME
                ),
                CONF_DERIVATIVE_WINDOW: DEFAULT_DERIVATIVE_WINDOW,
                CONF_PIECES: {},
            }
            return await self.async_step_add_room()

        # Get available calendars
        calendars = [
            state.entity_id
            for state in self.hass.states.async_all("calendar")
        ]

        if not calendars:
            errors["base"] = "no_calendar"

        # Get available device trackers
        trackers = [
            state.entity_id
            for state in self.hass.states.async_all("device_tracker")
        ]

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
                    selector.NumberSelectorConfig(
                        min=1, max=60, unit_of_measurement="min"
                    ),
                ),
                vol.Optional(
                    CONF_SECURITY_FACTOR, default=DEFAULT_SECURITY_FACTOR
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1.0, max=2.0, step=0.1),
                ),
                vol.Optional(
                    CONF_MIN_PREHEAT_TIME, default=DEFAULT_MIN_PREHEAT_TIME
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10, max=120, unit_of_measurement="min"
                    ),
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_add_room(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle adding a room."""
        errors = {}

        if user_input is not None:
            if user_input.get("skip_room"):
                # User wants to finish without adding more rooms
                if not self._data[CONF_PIECES]:
                    errors["base"] = "no_rooms"
                else:
                    return self.async_create_entry(
                        title="Chauffage Intelligent",
                        data=self._data,
                    )
            else:
                # Add the room
                piece_id = user_input.get(CONF_PIECE_ID) or _slugify(
                    user_input[CONF_PIECE_NAME]
                )
                piece_type = user_input[CONF_PIECE_TYPE]

                self._data[CONF_PIECES][piece_id] = {
                    CONF_PIECE_NAME: user_input[CONF_PIECE_NAME],
                    CONF_PIECE_TYPE: piece_type,
                    CONF_PIECE_RADIATEUR: user_input[CONF_PIECE_RADIATEUR],
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

                # Continue to add more rooms or finish
                return await self.async_step_add_room()

        # Get available climate entities
        climates = [
            state.entity_id for state in self.hass.states.async_all("climate")
        ]

        # Get available temperature sensors
        sensors = [
            state.entity_id
            for state in self.hass.states.async_all("sensor")
            if state.attributes.get("device_class") == "temperature"
        ]

        data_schema = vol.Schema(
            {
                vol.Required(CONF_PIECE_NAME): selector.TextSelector(),
                vol.Optional(CONF_PIECE_ID): selector.TextSelector(),
                vol.Required(CONF_PIECE_TYPE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=ROOM_TYPES,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Required(CONF_PIECE_RADIATEUR): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=climates,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional(CONF_PIECE_SONDE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=sensors,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional("temp_confort", default=19): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=15, max=25, unit_of_measurement="°C"
                    ),
                ),
                vol.Optional("temp_eco", default=17): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=12, max=20, unit_of_measurement="°C"
                    ),
                ),
                vol.Optional("temp_hors_gel", default=7): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5, max=12, unit_of_measurement="°C"
                    ),
                ),
                vol.Optional("skip_room", default=False): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="add_room",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "num_rooms": str(len(self._data.get(CONF_PIECES, {})))
            },
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
        self.config_entry = config_entry
        self._data: dict[str, Any] = dict(config_entry.data)
        self._selected_room: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Manage the options."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "add_room":
                return await self.async_step_add_room()
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

    async def async_step_add_room(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle adding a room in options."""
        errors = {}

        if user_input is not None:
            piece_id = user_input.get(CONF_PIECE_ID) or _slugify(
                user_input[CONF_PIECE_NAME]
            )
            piece_type = user_input[CONF_PIECE_TYPE]

            # Check if room ID already exists
            if piece_id in self._data.get(CONF_PIECES, {}):
                errors["base"] = "room_exists"
            else:
                # Add the room
                if CONF_PIECES not in self._data:
                    self._data[CONF_PIECES] = {}

                self._data[CONF_PIECES][piece_id] = {
                    CONF_PIECE_NAME: user_input[CONF_PIECE_NAME],
                    CONF_PIECE_TYPE: piece_type,
                    CONF_PIECE_RADIATEUR: user_input[CONF_PIECE_RADIATEUR],
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
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=self._data
                )
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)

                return self.async_create_entry(title="", data={})

        # Get available climate entities
        climates = [
            state.entity_id for state in self.hass.states.async_all("climate")
        ]

        # Get available temperature sensors
        sensors = [
            state.entity_id
            for state in self.hass.states.async_all("sensor")
            if state.attributes.get("device_class") == "temperature"
        ]

        data_schema = vol.Schema(
            {
                vol.Required(CONF_PIECE_NAME): selector.TextSelector(),
                vol.Optional(CONF_PIECE_ID): selector.TextSelector(),
                vol.Required(CONF_PIECE_TYPE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=ROOM_TYPES,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Required(CONF_PIECE_RADIATEUR): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=climates,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional(CONF_PIECE_SONDE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=sensors,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional("temp_confort", default=19): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=15, max=25, unit_of_measurement="°C"
                    ),
                ),
                vol.Optional("temp_eco", default=17): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=12, max=20, unit_of_measurement="°C"
                    ),
                ),
                vol.Optional("temp_hors_gel", default=7): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5, max=12, unit_of_measurement="°C"
                    ),
                ),
            }
        )

        return self.async_show_form(
            step_id="add_room",
            data_schema=data_schema,
            errors=errors,
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

            # Update the room
            self._data[CONF_PIECES][self._selected_room] = {
                CONF_PIECE_NAME: user_input[CONF_PIECE_NAME],
                CONF_PIECE_TYPE: piece_type,
                CONF_PIECE_RADIATEUR: user_input[CONF_PIECE_RADIATEUR],
                CONF_PIECE_SONDE: user_input.get(CONF_PIECE_SONDE),
                CONF_PIECE_TEMPERATURES: {
                    MODE_CONFORT: user_input.get("temp_confort", 19),
                    MODE_ECO: user_input.get("temp_eco", 17),
                    MODE_HORS_GEL: user_input.get("temp_hors_gel", 7),
                },
            }

            # Update the config entry
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=self._data
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)

            return self.async_create_entry(title="", data={})

        # Get available climate entities
        climates = [
            state.entity_id for state in self.hass.states.async_all("climate")
        ]

        # Get available temperature sensors
        sensors = [
            state.entity_id
            for state in self.hass.states.async_all("sensor")
            if state.attributes.get("device_class") == "temperature"
        ]

        # Pre-fill with current values
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_PIECE_NAME,
                    default=room_config.get(CONF_PIECE_NAME, ""),
                ): selector.TextSelector(),
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
                    CONF_PIECE_RADIATEUR,
                    default=room_config.get(CONF_PIECE_RADIATEUR, ""),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=climates,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional(
                    CONF_PIECE_SONDE,
                    default=room_config.get(CONF_PIECE_SONDE, ""),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=sensors,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional(
                    "temp_confort",
                    default=temps.get(MODE_CONFORT, 19),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=15, max=25, unit_of_measurement="°C"
                    ),
                ),
                vol.Optional(
                    "temp_eco",
                    default=temps.get(MODE_ECO, 17),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=12, max=20, unit_of_measurement="°C"
                    ),
                ),
                vol.Optional(
                    "temp_hors_gel",
                    default=temps.get(MODE_HORS_GEL, 7),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5, max=12, unit_of_measurement="°C"
                    ),
                ),
            }
        )

        return self.async_show_form(
            step_id="modify_room",
            data_schema=data_schema,
            description_placeholders={"room_name": room_config.get(CONF_PIECE_NAME, self._selected_room)},
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
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=self._data
                )
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
            self._data[CONF_UPDATE_INTERVAL] = user_input.get(
                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL // 60
            ) * 60
            self._data[CONF_SECURITY_FACTOR] = user_input.get(
                CONF_SECURITY_FACTOR, DEFAULT_SECURITY_FACTOR
            )
            self._data[CONF_MIN_PREHEAT_TIME] = user_input.get(
                CONF_MIN_PREHEAT_TIME, DEFAULT_MIN_PREHEAT_TIME
            )

            # Update the config entry
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=self._data
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)

            return self.async_create_entry(title="", data={})

        # Get available calendars
        calendars = [
            state.entity_id
            for state in self.hass.states.async_all("calendar")
        ]

        # Get available device trackers
        trackers = [
            state.entity_id
            for state in self.hass.states.async_all("device_tracker")
        ]

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
                    selector.NumberSelectorConfig(
                        min=1, max=60, unit_of_measurement="min"
                    ),
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
                    selector.NumberSelectorConfig(
                        min=10, max=120, unit_of_measurement="min"
                    ),
                ),
            }
        )

        return self.async_show_form(
            step_id="settings",
            data_schema=data_schema,
        )
