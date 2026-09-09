"""Chauffage Intelligent integration for Home Assistant."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_PIECE_OFFSET,
    CONF_PIECE_TEMPERATURES,
    CONF_PIECES,
    CONF_UPDATE_INTERVAL,
    DEFAULT_OFFSET,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LEGACY_CONF_KEYS,
    LEGACY_LEARNING_FILE,
)
from .coordinator import ChauffageIntelligentCoordinator
from .panel import async_register_panel, async_unregister_panel
from .schedule import default_schedule
from .storage import ScheduleStore
from .websocket_api import async_register_websocket_api

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.SELECT]

DATA_STORE = "store"

SERVICE_SET_TEMPERATURE = "set_temperature"
SERVICE_RESET = "reset"
SERVICE_REFRESH = "refresh"
SERVICE_SET_SCHEDULE = "set_schedule"

SLOT_SCHEMA = vol.Schema(
    {
        vol.Required("day"): vol.All(int, vol.Range(min=0, max=6)),
        vol.Required("start"): cv.string,
        vol.Required("end"): cv.string,
        vol.Required("temperature"): vol.Coerce(float),
    }
)

SET_TEMPERATURE_SCHEMA = vol.Schema(
    {
        vol.Required("piece"): cv.string,
        vol.Required("temperature"): vol.Coerce(float),
        vol.Optional("duree"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
    }
)

RESET_SCHEMA = vol.Schema({vol.Optional("piece"): cv.string})

SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("piece"): cv.string,
        vol.Required("slots"): [SLOT_SCHEMA],
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Chauffage Intelligent from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})

    store: ScheduleStore | None = domain_data.get(DATA_STORE)
    if store is None:
        store = ScheduleStore(hass)
        await store.async_load()
        domain_data[DATA_STORE] = store

    pieces = entry.data.get(CONF_PIECES, {})

    # A room without a schedule yet (fresh install, restored backup) gets a
    # sensible default rather than sitting at the eco fallback forever.
    for piece_id, piece_config in pieces.items():
        if not store.has(piece_id):
            await store.async_set(
                piece_id, default_schedule(piece_config.get(CONF_PIECE_TEMPERATURES, {}))
            )

    config = {
        CONF_PIECES: pieces,
        CONF_UPDATE_INTERVAL: entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
    }

    coordinator = ChauffageIntelligentCoordinator(
        hass,
        config,
        store,
        update_interval=timedelta(seconds=config[CONF_UPDATE_INTERVAL]),
    )

    await coordinator.async_config_entry_first_refresh()
    coordinator.async_start_listeners()

    domain_data[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async_register_websocket_api(hass)
    await async_register_panel(hass)
    _async_setup_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: ChauffageIntelligentCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.async_shutdown_listeners()

        # Drop the shared pieces once the last entry goes away. hass.data also
        # holds the store and the panel/websocket flags, so count coordinators.
        if not _coordinators(hass):
            hass.data[DOMAIN].pop(DATA_STORE, None)
            await async_unregister_panel(hass)
            for service in (
                SERVICE_SET_TEMPERATURE,
                SERVICE_RESET,
                SERVICE_REFRESH,
                SERVICE_SET_SCHEDULE,
            ):
                hass.services.async_remove(DOMAIN, service)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an old config entry to the schedule-based layout."""
    if entry.version >= 2:
        return True

    _LOGGER.info("Migrating Chauffage Intelligent entry from version %s to 2", entry.version)

    data: dict[str, Any] = dict(entry.data)

    # Calendar, presence and the whole prediction layer are gone.
    for key in LEGACY_CONF_KEYS:
        data.pop(key, None)

    pieces = {piece_id: dict(cfg) for piece_id, cfg in data.get(CONF_PIECES, {}).items()}
    for piece_config in pieces.values():
        piece_config.setdefault(CONF_PIECE_OFFSET, DEFAULT_OFFSET)
    data[CONF_PIECES] = pieces

    # Seed a schedule for every existing room, since the calendar no longer
    # drives anything.
    store = ScheduleStore(hass)
    await store.async_load()
    for piece_id, piece_config in pieces.items():
        if not store.has(piece_id):
            await store.async_set(
                piece_id, default_schedule(piece_config.get(CONF_PIECE_TEMPERATURES, {}))
            )

    await hass.async_add_executor_job(_remove_legacy_learning_file, hass)

    hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True


def _remove_legacy_learning_file(hass: HomeAssistant) -> None:
    """Delete the heating-rate learning store left behind by version 1."""
    path = Path(hass.config.path(".storage")) / LEGACY_LEARNING_FILE
    try:
        path.unlink(missing_ok=True)
    except OSError as err:  # pragma: no cover - best effort cleanup
        _LOGGER.debug("Could not remove %s: %s", path, err)


def _coordinators(hass: HomeAssistant) -> list[ChauffageIntelligentCoordinator]:
    """Return every loaded coordinator."""
    return [
        value
        for key, value in hass.data.get(DOMAIN, {}).items()
        if key != DATA_STORE and isinstance(value, ChauffageIntelligentCoordinator)
    ]


def _find_coordinator(
    hass: HomeAssistant, piece_id: str
) -> ChauffageIntelligentCoordinator | None:
    """Find the coordinator owning a room."""
    for coordinator in _coordinators(hass):
        if piece_id in coordinator.pieces:
            return coordinator
    return None


def _async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration services (once per Home Assistant instance)."""
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    async def handle_set_temperature(call: ServiceCall) -> None:
        """Force a temperature for a room."""
        piece = call.data["piece"]
        coordinator = _find_coordinator(hass, piece)
        if coordinator is None:
            raise ServiceValidationError(f"Unknown room: {piece}")
        await coordinator.async_set_override(
            piece, call.data["temperature"], call.data.get("duree")
        )

    async def handle_reset(call: ServiceCall) -> None:
        """Return a room (or every room) to its schedule."""
        piece = call.data.get("piece")
        if piece:
            coordinator = _find_coordinator(hass, piece)
            if coordinator is None:
                raise ServiceValidationError(f"Unknown room: {piece}")
            await coordinator.async_reset_override(piece)
            return

        for coordinator in _coordinators(hass):
            await coordinator.async_reset_override()

    async def handle_refresh(_call: ServiceCall) -> None:
        """Force an immediate recomputation."""
        for coordinator in _coordinators(hass):
            await coordinator.async_request_refresh()

    async def handle_set_schedule(call: ServiceCall) -> None:
        """Replace a room's weekly schedule."""
        piece = call.data["piece"]
        coordinator = _find_coordinator(hass, piece)
        if coordinator is None:
            raise ServiceValidationError(f"Unknown room: {piece}")
        try:
            await coordinator.async_set_schedule(piece, call.data["slots"])
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    hass.services.async_register(
        DOMAIN, SERVICE_SET_TEMPERATURE, handle_set_temperature, schema=SET_TEMPERATURE_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_RESET, handle_reset, schema=RESET_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, handle_refresh)
    hass.services.async_register(
        DOMAIN, SERVICE_SET_SCHEDULE, handle_set_schedule, schema=SET_SCHEDULE_SCHEMA
    )
