"""Config flow for Chauffage Intelligent integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_PIECE_AREA_ID,
    CONF_PIECE_NAME,
    CONF_PIECE_OFFSET,
    CONF_PIECE_RADIATEURS,
    CONF_PIECE_SONDE,
    CONF_PIECE_TEMPERATURES,
    CONF_PIECE_TYPE,
    CONF_PIECES,
    CONF_UPDATE_INTERVAL,
    DEFAULT_OFFSET,
    DEFAULT_TEMPERATURES,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    ROOM_TYPES,
    TEMP_CONFORT,
    TEMP_ECO,
    TEMP_HORS_GEL,
)
from .storage import ScheduleStore

_LOGGER = logging.getLogger(__name__)

CONFIG_VERSION = 2

# Menu actions
ACTION_ADD_ROOM = "add_room"
ACTION_FINISH = "finish"

# Room form fields (kept flat so the same schema serves add and modify)
FIELD_TEMP_CONFORT = "temp_confort"
FIELD_TEMP_ECO = "temp_eco"
FIELD_TEMP_HORS_GEL = "temp_hors_gel"


def _areas_with_climate(hass: HomeAssistant) -> list[dict[str, str]]:
    """Return areas holding at least one climate entity."""
    area_reg = ar.async_get(hass)
    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)

    area_ids: set[str] = set()
    for entity in entity_reg.entities.values():
        if entity.domain != "climate":
            continue
        if entity.area_id:
            area_ids.add(entity.area_id)
        elif entity.device_id:
            device = device_reg.async_get(entity.device_id)
            if device and device.area_id:
                area_ids.add(device.area_id)

    options = []
    for area_id in area_ids:
        area = area_reg.async_get_area(area_id)
        if area:
            options.append({"value": area.id, "label": area.name})

    return sorted(options, key=lambda option: option["label"])


def _entities_in_area(hass: HomeAssistant, area_id: str, domain: str) -> list[str]:
    """Return entity ids of a domain assigned to an area, directly or via device."""
    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)

    entities = []
    for entity in entity_reg.entities.values():
        if entity.domain != domain:
            continue

        if domain == "sensor":
            state = hass.states.get(entity.entity_id)
            if not state or state.attributes.get("device_class") != "temperature":
                continue

        if entity.area_id == area_id:
            entities.append(entity.entity_id)
        elif entity.device_id:
            device = device_reg.async_get(entity.device_id)
            if device and device.area_id == area_id:
                entities.append(entity.entity_id)

    return entities


def _all_temperature_sensors(hass: HomeAssistant) -> list[str]:
    """Return every temperature sensor, used as a fallback when an area has none."""
    return [
        state.entity_id
        for state in hass.states.async_all("sensor")
        if state.attributes.get("device_class") == "temperature"
    ]


def _room_schema(
    hass: HomeAssistant,
    area_id: str,
    room_config: dict[str, Any] | None = None,
    piece_type: str = "autre",
) -> vol.Schema:
    """Build the room form, pre-filled from ``room_config`` when modifying."""
    room_config = room_config or {}
    temps = room_config.get(CONF_PIECE_TEMPERATURES, {})
    defaults = DEFAULT_TEMPERATURES.get(
        room_config.get(CONF_PIECE_TYPE, piece_type), DEFAULT_TEMPERATURES["autre"]
    )

    climate_entities = _entities_in_area(hass, area_id, "climate") or [
        state.entity_id for state in hass.states.async_all("climate")
    ]
    temp_sensors = _entities_in_area(hass, area_id, "sensor") or _all_temperature_sensors(hass)

    current_radiateurs = room_config.get(CONF_PIECE_RADIATEURS, [])
    if isinstance(current_radiateurs, str):
        current_radiateurs = [current_radiateurs]

    schema: dict[Any, Any] = {
        vol.Required(
            CONF_PIECE_TYPE, default=room_config.get(CONF_PIECE_TYPE, piece_type)
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=ROOM_TYPES, mode=selector.SelectSelectorMode.DROPDOWN
            ),
        ),
        vol.Required(
            CONF_PIECE_RADIATEURS, default=current_radiateurs
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=climate_entities,
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            ),
        ),
        vol.Optional(
            CONF_PIECE_SONDE, default=room_config.get(CONF_PIECE_SONDE) or ""
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=temp_sensors, mode=selector.SelectSelectorMode.DROPDOWN
            ),
        ),
        vol.Optional(
            FIELD_TEMP_CONFORT, default=temps.get(TEMP_CONFORT, defaults[TEMP_CONFORT])
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=15, max=25, step=0.5, unit_of_measurement="°C"),
        ),
        vol.Optional(
            FIELD_TEMP_ECO, default=temps.get(TEMP_ECO, defaults[TEMP_ECO])
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=12, max=20, step=0.5, unit_of_measurement="°C"),
        ),
        vol.Optional(
            FIELD_TEMP_HORS_GEL, default=temps.get(TEMP_HORS_GEL, defaults[TEMP_HORS_GEL])
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=5, max=12, step=0.5, unit_of_measurement="°C"),
        ),
        vol.Optional(
            CONF_PIECE_OFFSET, default=room_config.get(CONF_PIECE_OFFSET, DEFAULT_OFFSET)
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=-5, max=5, step=0.1, unit_of_measurement="°C"),
        ),
    }

    return vol.Schema(schema)


def _room_from_input(
    user_input: dict[str, Any],
    name: str,
    area_id: str,
) -> dict[str, Any]:
    """Turn the room form into a stored room config."""
    piece_type = user_input[CONF_PIECE_TYPE]
    defaults = DEFAULT_TEMPERATURES.get(piece_type, DEFAULT_TEMPERATURES["autre"])

    radiateurs = user_input[CONF_PIECE_RADIATEURS]
    if isinstance(radiateurs, str):
        radiateurs = [radiateurs]

    return {
        CONF_PIECE_NAME: name,
        CONF_PIECE_AREA_ID: area_id,
        CONF_PIECE_TYPE: piece_type,
        CONF_PIECE_RADIATEURS: radiateurs,
        CONF_PIECE_SONDE: user_input.get(CONF_PIECE_SONDE) or None,
        CONF_PIECE_TEMPERATURES: {
            TEMP_CONFORT: float(user_input.get(FIELD_TEMP_CONFORT, defaults[TEMP_CONFORT])),
            TEMP_ECO: float(user_input.get(FIELD_TEMP_ECO, defaults[TEMP_ECO])),
            TEMP_HORS_GEL: float(user_input.get(FIELD_TEMP_HORS_GEL, defaults[TEMP_HORS_GEL])),
        },
        CONF_PIECE_OFFSET: float(user_input.get(CONF_PIECE_OFFSET, DEFAULT_OFFSET)),
    }


def _settings_schema(current_interval: int) -> vol.Schema:
    """Build the global settings form."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_UPDATE_INTERVAL, default=current_interval // 60
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=60, unit_of_measurement="min"),
            ),
        }
    )


class ChauffageIntelligentConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Chauffage Intelligent."""

    VERSION = CONFIG_VERSION

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._current_area_id: str | None = None
        self._current_area_name: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step - global configuration."""
        if user_input is not None:
            self._data = {
                CONF_UPDATE_INTERVAL: int(
                    user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL // 60) * 60
                ),
                CONF_PIECES: {},
            }
            return await self.async_step_room_menu()

        return self.async_show_form(
            step_id="user",
            data_schema=_settings_schema(DEFAULT_UPDATE_INTERVAL),
        )

    async def async_step_room_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Show menu to add a room or finish configuration."""
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

        menu_options = [{"value": ACTION_ADD_ROOM, "label": "Ajouter une pièce"}]
        if num_rooms > 0:
            menu_options.append({"value": ACTION_FINISH, "label": "Terminer la configuration"})

        return self.async_show_form(
            step_id="room_menu",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=menu_options, mode=selector.SelectSelectorMode.LIST
                        ),
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"num_rooms": str(num_rooms)},
        )

    async def async_step_select_area(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle area selection step."""
        errors = {}

        if user_input is not None:
            area_id = user_input["area"]
            area = ar.async_get(self.hass).async_get_area(area_id)

            if area:
                if area_id in self._data.get(CONF_PIECES, {}):
                    errors["base"] = "area_already_configured"
                else:
                    self._current_area_id = area_id
                    self._current_area_name = area.name
                    return await self.async_step_configure_room()

        area_options = [
            area
            for area in _areas_with_climate(self.hass)
            if area["value"] not in self._data.get(CONF_PIECES, {})
        ]

        # Do not let the generic message hide a more specific one.
        if not area_options and not errors:
            errors["base"] = "no_areas_available"

        return self.async_show_form(
            step_id="select_area",
            data_schema=vol.Schema(
                {
                    vol.Required("area"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=area_options, mode=selector.SelectSelectorMode.DROPDOWN
                        ),
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_configure_room(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle room configuration step."""
        if user_input is not None:
            self._data[CONF_PIECES][self._current_area_id] = _room_from_input(
                user_input,
                self._current_area_name or self._current_area_id or "",
                self._current_area_id or "",
            )
            self._current_area_id = None
            self._current_area_name = None
            return await self.async_step_room_menu()

        return self.async_show_form(
            step_id="configure_room",
            data_schema=_room_schema(self.hass, self._current_area_id or ""),
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
        self._entry = config_entry
        self._data: dict[str, Any] = dict(config_entry.data)
        self._selected_room: str | None = None
        self._current_area_id: str | None = None
        self._current_area_name: str | None = None

    async def _async_commit(self) -> config_entries.ConfigFlowResult:
        """Persist the edited config; the update listener reloads the entry."""
        self.hass.config_entries.async_update_entry(self._entry, data=self._data)
        return self.async_create_entry(title="", data={})

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "add_room":
                return await self.async_step_select_area()
            if action == "modify_room":
                return await self.async_step_select_room()
            if action == "delete_room":
                return await self.async_step_delete_room()
            if action == "modify_settings":
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
    ) -> config_entries.ConfigFlowResult:
        """Handle area selection for adding a new room."""
        errors = {}

        if user_input is not None:
            area_id = user_input["area"]
            area = ar.async_get(self.hass).async_get_area(area_id)

            if area:
                if area_id in self._data.get(CONF_PIECES, {}):
                    errors["base"] = "area_already_configured"
                else:
                    self._current_area_id = area_id
                    self._current_area_name = area.name
                    return await self.async_step_add_room()

        area_options = [
            area
            for area in _areas_with_climate(self.hass)
            if area["value"] not in self._data.get(CONF_PIECES, {})
        ]

        if not area_options and not errors:
            return self.async_abort(reason="no_areas_available")

        return self.async_show_form(
            step_id="select_area",
            data_schema=vol.Schema(
                {
                    vol.Required("area"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=area_options, mode=selector.SelectSelectorMode.DROPDOWN
                        ),
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_add_room(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle adding a room in options."""
        if user_input is not None:
            self._data.setdefault(CONF_PIECES, {})
            self._data[CONF_PIECES][self._current_area_id] = _room_from_input(
                user_input,
                self._current_area_name or self._current_area_id or "",
                self._current_area_id or "",
            )
            return await self._async_commit()

        return self.async_show_form(
            step_id="add_room",
            data_schema=_room_schema(self.hass, self._current_area_id or ""),
            description_placeholders={"area_name": self._current_area_name},
        )

    async def async_step_select_room(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle selecting a room to modify."""
        pieces = self._data.get(CONF_PIECES, {})

        if not pieces:
            return self.async_abort(reason="no_rooms")

        if user_input is not None:
            self._selected_room = user_input["room"]
            return await self.async_step_modify_room()

        return self.async_show_form(
            step_id="select_room",
            data_schema=vol.Schema(
                {
                    vol.Required("room"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_room_options(pieces),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                }
            ),
        )

    async def async_step_modify_room(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle modifying a room."""
        if self._selected_room is None:
            return await self.async_step_select_room()

        room_config = self._data[CONF_PIECES].get(self._selected_room, {})
        area_id = room_config.get(CONF_PIECE_AREA_ID, self._selected_room) or ""

        if user_input is not None:
            self._data[CONF_PIECES][self._selected_room] = _room_from_input(
                user_input,
                room_config.get(CONF_PIECE_NAME, self._selected_room),
                area_id,
            )
            return await self._async_commit()

        return self.async_show_form(
            step_id="modify_room",
            data_schema=_room_schema(self.hass, area_id, room_config),
            description_placeholders={
                "room_name": room_config.get(CONF_PIECE_NAME, self._selected_room)
            },
        )

    async def async_step_delete_room(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle deleting a room."""
        pieces = self._data.get(CONF_PIECES, {})

        if not pieces:
            return self.async_abort(reason="no_rooms")

        if user_input is not None:
            if not user_input.get("confirm"):
                return await self.async_step_init()

            room_id = user_input["room"]
            del self._data[CONF_PIECES][room_id]

            # The room is gone: drop its schedule too, so a room later re-added
            # for the same area does not inherit a stale planning.
            store: ScheduleStore | None = self.hass.data.get(DOMAIN, {}).get("store")
            if store is not None:
                await store.async_remove(room_id)

            return await self._async_commit()

        return self.async_show_form(
            step_id="delete_room",
            data_schema=vol.Schema(
                {
                    vol.Required("room"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_room_options(pieces),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                    vol.Required("confirm", default=False): selector.BooleanSelector(),
                }
            ),
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle modifying global settings."""
        if user_input is not None:
            self._data[CONF_UPDATE_INTERVAL] = int(
                user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL // 60) * 60
            )
            return await self._async_commit()

        return self.async_show_form(
            step_id="settings",
            data_schema=_settings_schema(
                self._data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            ),
        )


def _room_options(pieces: dict[str, Any]) -> list[dict[str, str]]:
    """Build a select option list from the configured rooms."""
    return [
        {"value": room_id, "label": room_config.get(CONF_PIECE_NAME, room_id)}
        for room_id, room_config in pieces.items()
    ]
