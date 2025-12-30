"""Config flow for Chauffage Intelligent integration."""
from __future__ import annotations

import logging
from typing import Any
import re

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    ROOM_TYPES,
    DEFAULT_TEMPERATURES,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_SECURITY_FACTOR,
    DEFAULT_MIN_PREHEAT_TIME,
    DEFAULT_DERIVATIVE_WINDOW,
    MODE_CONFORT,
    MODE_ECO,
    MODE_HORS_GEL,
    CONF_CALENDAR,
    CONF_PRESENCE_TRACKERS,
    CONF_PIECES,
    CONF_SECURITY_FACTOR,
    CONF_MIN_PREHEAT_TIME,
    CONF_UPDATE_INTERVAL,
    CONF_DERIVATIVE_WINDOW,
    CONF_PIECE_NAME,
    CONF_PIECE_ID,
    CONF_PIECE_TYPE,
    CONF_PIECE_RADIATEUR,
    CONF_PIECE_SONDE,
    CONF_PIECE_TEMPERATURES,
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
            elif action == "modify_settings":
                return await self.async_step_settings()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": "add_room", "label": "Add a room"},
                                {"value": "modify_room", "label": "Modify a room"},
                                {"value": "modify_settings", "label": "Modify settings"},
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
        # Similar to config flow add_room step
        # Implementation would go here
        return self.async_abort(reason="not_implemented")

    async def async_step_select_room(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle selecting a room to modify."""
        # Implementation would go here
        return self.async_abort(reason="not_implemented")

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle modifying global settings."""
        # Implementation would go here
        return self.async_abort(reason="not_implemented")
