"""WebSocket API backing the Chauffage Intelligent panel."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_PIECE_NAME,
    CONF_PIECE_RADIATEURS,
    CONF_PIECE_SONDE,
    CONF_PIECE_TEMPERATURES,
    DOMAIN,
    SCHEDULE_DAYS,
    SCHEDULE_SLOTS_PER_DAY,
    SCHEDULE_STEP_MINUTES,
)
from .coordinator import ChauffageIntelligentCoordinator
from .schedule import ScheduleError, grid_to_slots, slots_to_grid

_LOGGER = logging.getLogger(__name__)

DATA_WS_REGISTERED = "websocket_registered"

TYPE_ROOMS = f"{DOMAIN}/rooms"
TYPE_SCHEDULE_GET = f"{DOMAIN}/schedule/get"
TYPE_SCHEDULE_SET = f"{DOMAIN}/schedule/set"
TYPE_SCHEDULE_COPY = f"{DOMAIN}/schedule/copy"
TYPE_OVERRIDE_SET = f"{DOMAIN}/override/set"

GRID_SCHEMA = vol.All(
    [vol.All([vol.Any(None, vol.Coerce(float))], vol.Length(min=SCHEDULE_SLOTS_PER_DAY,
                                                            max=SCHEDULE_SLOTS_PER_DAY))],
    vol.Length(min=SCHEDULE_DAYS, max=SCHEDULE_DAYS),
)


@callback
def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register the panel's websocket commands (once per instance)."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(DATA_WS_REGISTERED):
        return

    websocket_api.async_register_command(hass, ws_rooms)
    websocket_api.async_register_command(hass, ws_schedule_get)
    websocket_api.async_register_command(hass, ws_schedule_set)
    websocket_api.async_register_command(hass, ws_schedule_copy)
    websocket_api.async_register_command(hass, ws_override_set)

    domain_data[DATA_WS_REGISTERED] = True


def _coordinators(hass: HomeAssistant) -> list[ChauffageIntelligentCoordinator]:
    """Return every loaded coordinator."""
    return [
        value
        for value in hass.data.get(DOMAIN, {}).values()
        if isinstance(value, ChauffageIntelligentCoordinator)
    ]


def _find(hass: HomeAssistant, piece_id: str) -> ChauffageIntelligentCoordinator | None:
    """Find the coordinator owning a room."""
    for coordinator in _coordinators(hass):
        if piece_id in coordinator.pieces:
            return coordinator
    return None


def _room_payload(
    coordinator: ChauffageIntelligentCoordinator, piece_id: str, piece_config: dict[str, Any]
) -> dict[str, Any]:
    """Describe a room and its live state for the panel."""
    data = (coordinator.data or {}).get("pieces", {}).get(piece_id, {})

    return {
        "id": piece_id,
        "name": piece_config.get(CONF_PIECE_NAME, piece_id),
        "temperatures": piece_config.get(CONF_PIECE_TEMPERATURES, {}),
        "sonde": piece_config.get(CONF_PIECE_SONDE),
        "radiateurs": piece_config.get(CONF_PIECE_RADIATEURS, []),
        "temperature": data.get("temperature"),
        "consigne": data.get("consigne"),
        "source": data.get("source"),
        "creneau_actuel": data.get("creneau_actuel"),
        "prochain_changement": data.get("prochain_changement"),
        "off": data.get("off", False),
    }


@websocket_api.websocket_command({vol.Required("type"): TYPE_ROOMS})
@callback
def ws_rooms(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return every configured room with its current state."""
    rooms = [
        _room_payload(coordinator, piece_id, piece_config)
        for coordinator in _coordinators(hass)
        for piece_id, piece_config in coordinator.pieces.items()
    ]

    connection.send_result(
        msg["id"],
        {
            "rooms": rooms,
            "step_minutes": SCHEDULE_STEP_MINUTES,
            "slots_per_day": SCHEDULE_SLOTS_PER_DAY,
            "days": SCHEDULE_DAYS,
        },
    )


@websocket_api.websocket_command(
    {vol.Required("type"): TYPE_SCHEDULE_GET, vol.Required("piece_id"): str}
)
@callback
def ws_schedule_get(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return a room's schedule as both slots and a paintable grid."""
    piece_id = msg["piece_id"]
    coordinator = _find(hass, piece_id)

    if coordinator is None:
        connection.send_error(msg["id"], "not_found", f"Unknown room: {piece_id}")
        return

    slots = coordinator.get_schedule(piece_id)
    connection.send_result(msg["id"], {"slots": slots, "grid": slots_to_grid(slots)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): TYPE_SCHEDULE_SET,
        vol.Required("piece_id"): str,
        vol.Required("grid"): GRID_SCHEMA,
    }
)
@websocket_api.async_response
async def ws_schedule_set(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Replace a room's schedule from the panel's grid."""
    piece_id = msg["piece_id"]
    coordinator = _find(hass, piece_id)

    if coordinator is None:
        connection.send_error(msg["id"], "not_found", f"Unknown room: {piece_id}")
        return

    try:
        slots = await coordinator.async_set_schedule(piece_id, grid_to_slots(msg["grid"]))
    except ScheduleError as err:
        connection.send_error(msg["id"], "invalid_schedule", str(err))
        return

    connection.send_result(msg["id"], {"slots": slots, "grid": slots_to_grid(slots)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): TYPE_SCHEDULE_COPY,
        vol.Required("from_piece"): str,
        vol.Required("to_pieces"): [str],
    }
)
@websocket_api.async_response
async def ws_schedule_copy(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Copy one room's schedule onto others."""
    source = _find(hass, msg["from_piece"])
    if source is None:
        connection.send_error(msg["id"], "not_found", f"Unknown room: {msg['from_piece']}")
        return

    slots = source.get_schedule(msg["from_piece"])

    for piece_id in msg["to_pieces"]:
        target = _find(hass, piece_id)
        if target is None:
            connection.send_error(msg["id"], "not_found", f"Unknown room: {piece_id}")
            return
        await target.async_set_schedule(piece_id, slots)

    connection.send_result(msg["id"], {"copied_to": msg["to_pieces"]})


@websocket_api.websocket_command(
    {
        vol.Required("type"): TYPE_OVERRIDE_SET,
        vol.Required("piece_id"): str,
        vol.Optional("temperature"): vol.Any(None, vol.Coerce(float)),
        vol.Optional("duree"): vol.Any(None, vol.Coerce(int)),
    }
)
@websocket_api.async_response
async def ws_override_set(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Force a temperature for a room, or clear the override."""
    piece_id = msg["piece_id"]
    coordinator = _find(hass, piece_id)

    if coordinator is None:
        connection.send_error(msg["id"], "not_found", f"Unknown room: {piece_id}")
        return

    temperature = msg.get("temperature")
    if temperature is None:
        await coordinator.async_reset_override(piece_id)
    else:
        await coordinator.async_set_override(piece_id, temperature, msg.get("duree"))

    connection.send_result(msg["id"], {})
