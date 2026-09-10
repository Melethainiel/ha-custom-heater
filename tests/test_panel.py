"""Tests for the sidebar panel registration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.chauffage_intelligent import panel
from custom_components.chauffage_intelligent.const import (
    DOMAIN,
    PANEL_COMPONENT_NAME,
    PANEL_STATIC_PATH,
    PANEL_URL_PATH,
)


@pytest.fixture
def panel_hass(mock_hass):
    """A hass with an http component able to serve static files."""
    mock_hass.data = {}
    mock_hass.http.async_register_static_paths = AsyncMock()
    return mock_hass


@pytest.fixture
def register():
    """Patch panel_custom.async_register_panel."""
    with patch.object(
        panel.panel_custom, "async_register_panel", new=AsyncMock()
    ) as mocked:
        yield mocked


async def test_register_serves_the_panel_file(panel_hass, register):
    """panel.js is served from the integration's frontend directory."""
    await panel.async_register_panel(panel_hass)

    static = panel_hass.http.async_register_static_paths.call_args.args[0][0]
    assert static.url_path == PANEL_STATIC_PATH
    assert static.path.endswith("/frontend")


async def test_register_adds_the_sidebar_entry(panel_hass, register):
    """The panel lands in the sidebar under a stable url."""
    await panel.async_register_panel(panel_hass)

    kwargs = register.call_args.kwargs
    assert kwargs["webcomponent_name"] == PANEL_COMPONENT_NAME
    assert kwargs["frontend_url_path"] == PANEL_URL_PATH
    assert kwargs["module_url"].startswith(f"{PANEL_STATIC_PATH}/panel.js?v=")
    assert kwargs["require_admin"] is False


async def test_register_is_idempotent(panel_hass, register):
    """A second config entry does not register the panel twice."""
    await panel.async_register_panel(panel_hass)
    await panel.async_register_panel(panel_hass)

    assert register.await_count == 1
    assert panel_hass.http.async_register_static_paths.await_count == 1


async def test_unregister_removes_the_panel(panel_hass, register):
    """Unloading the last entry removes the sidebar entry."""
    await panel.async_register_panel(panel_hass)

    with patch.object(panel.frontend, "async_remove_panel") as remove:
        await panel.async_unregister_panel(panel_hass)

    remove.assert_called_once_with(panel_hass, PANEL_URL_PATH)
    assert panel_hass.data[DOMAIN].get("panel_registered") is None


async def test_unregister_when_never_registered(panel_hass):
    """Removing a panel that was never added is a no-op."""
    with patch.object(panel.frontend, "async_remove_panel") as remove:
        await panel.async_unregister_panel(panel_hass)

    remove.assert_not_called()


def test_panel_js_is_shipped():
    """The static file the panel points at actually exists."""
    from pathlib import Path

    panel_js = Path(panel.__file__).parent / "frontend" / "panel.js"

    assert panel_js.is_file()
    assert f'customElements.define("{PANEL_COMPONENT_NAME}"' in panel_js.read_text()
