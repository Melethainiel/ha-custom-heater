"""Sidebar panel registration for Chauffage Intelligent."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    PANEL_COMPONENT_NAME,
    PANEL_STATIC_PATH,
    PANEL_URL_PATH,
)

_LOGGER = logging.getLogger(__name__)

DATA_PANEL_REGISTERED = "panel_registered"

# Bumped whenever panel.js changes, so browsers do not serve a stale bundle.
PANEL_VERSION = "2"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Serve the schedule editor and add it to the sidebar."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(DATA_PANEL_REGISTERED):
        return

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                PANEL_STATIC_PATH,
                str(Path(__file__).parent / "frontend"),
                cache_headers=False,
            )
        ]
    )

    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_COMPONENT_NAME,
        frontend_url_path=PANEL_URL_PATH,
        module_url=f"{PANEL_STATIC_PATH}/panel.js?v={PANEL_VERSION}",
        sidebar_title="Chauffage",
        sidebar_icon="mdi:radiator",
        require_admin=False,
        config={},
    )

    domain_data[DATA_PANEL_REGISTERED] = True
    _LOGGER.debug("Registered Chauffage Intelligent panel at /%s", PANEL_URL_PATH)


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove the panel from the sidebar."""
    domain_data = hass.data.get(DOMAIN, {})
    if not domain_data.pop(DATA_PANEL_REGISTERED, False):
        return

    frontend.async_remove_panel(hass, PANEL_URL_PATH)
    _LOGGER.debug("Removed Chauffage Intelligent panel")
