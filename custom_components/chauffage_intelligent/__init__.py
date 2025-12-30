"""Chauffage Intelligent integration for Home Assistant."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    DOMAIN,
    CONF_CALENDAR,
    CONF_PRESENCE_TRACKERS,
    CONF_PIECES,
    CONF_SECURITY_FACTOR,
    CONF_MIN_PREHEAT_TIME,
    CONF_UPDATE_INTERVAL,
    CONF_DERIVATIVE_WINDOW,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_SECURITY_FACTOR,
    DEFAULT_MIN_PREHEAT_TIME,
    DEFAULT_DERIVATIVE_WINDOW,
    MODE_CONFORT,
    MODE_ECO,
    MODE_HORS_GEL,
    MODE_OFF,
    MODES,
)
from .coordinator import ChauffageIntelligentCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Chauffage Intelligent from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    config = {
        CONF_CALENDAR: entry.data[CONF_CALENDAR],
        CONF_PRESENCE_TRACKERS: entry.data[CONF_PRESENCE_TRACKERS],
        CONF_PIECES: entry.data.get(CONF_PIECES, {}),
        CONF_SECURITY_FACTOR: entry.data.get(
            CONF_SECURITY_FACTOR, DEFAULT_SECURITY_FACTOR
        ),
        CONF_MIN_PREHEAT_TIME: entry.data.get(
            CONF_MIN_PREHEAT_TIME, DEFAULT_MIN_PREHEAT_TIME
        ),
        CONF_UPDATE_INTERVAL: entry.data.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        ),
        CONF_DERIVATIVE_WINDOW: entry.data.get(
            CONF_DERIVATIVE_WINDOW, DEFAULT_DERIVATIVE_WINDOW
        ),
    }

    coordinator = ChauffageIntelligentCoordinator(
        hass,
        config,
        update_interval=timedelta(seconds=config[CONF_UPDATE_INTERVAL]),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    await _async_setup_services(hass, coordinator)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def _async_setup_services(
    hass: HomeAssistant, coordinator: ChauffageIntelligentCoordinator
) -> None:
    """Set up services for Chauffage Intelligent."""

    async def handle_set_mode(call: ServiceCall) -> None:
        """Handle set_mode service call."""
        piece = call.data.get("piece")
        mode = call.data.get("mode")
        duree = call.data.get("duree")

        if mode not in MODES:
            _LOGGER.error("Invalid mode: %s", mode)
            return

        await coordinator.async_set_mode_override(piece, mode, duree)

    async def handle_reset_mode(call: ServiceCall) -> None:
        """Handle reset_mode service call."""
        piece = call.data.get("piece")
        await coordinator.async_reset_mode_override(piece)

    async def handle_refresh(call: ServiceCall) -> None:
        """Handle refresh service call."""
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "set_mode", handle_set_mode)
    hass.services.async_register(DOMAIN, "reset_mode", handle_reset_mode)
    hass.services.async_register(DOMAIN, "refresh", handle_refresh)
