"""Select platform for Chauffage Intelligent."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_PIECE_NAME,
    DOMAIN,
    MODE_AUTO,
    SELECT_OPTION_LABELS,
    SELECT_OPTIONS,
    SOURCE_OVERRIDE,
)
from .coordinator import ChauffageIntelligentCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities from a config entry."""
    coordinator: ChauffageIntelligentCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[SelectEntity] = []

    for piece_id, piece_config in coordinator.pieces.items():
        entities.append(ChauffageIntelligentModeSelect(coordinator, piece_id, piece_config))

    async_add_entities(entities)


class ChauffageIntelligentModeSelect(
    CoordinatorEntity[ChauffageIntelligentCoordinator], SelectEntity
):
    """Select entity for manual mode override per room."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChauffageIntelligentCoordinator,
        piece_id: str,
        piece_config: dict[str, Any],
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._piece_id = piece_id
        self._piece_name = piece_config.get(CONF_PIECE_NAME, piece_id)
        self._attr_unique_id = f"{DOMAIN}_{piece_id}_mode_select"
        self._attr_name = f"{self._piece_name} Mode"
        self._attr_options = [SELECT_OPTION_LABELS[opt] for opt in SELECT_OPTIONS]

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        if self.coordinator.data is None:
            return SELECT_OPTION_LABELS[MODE_AUTO]

        piece_data = self.coordinator.data.get("pieces", {}).get(self._piece_id)
        if piece_data is None:
            return SELECT_OPTION_LABELS[MODE_AUTO]

        source = piece_data.get("source")
        if source == SOURCE_OVERRIDE:
            current_mode = piece_data.get("mode")
            if current_mode in SELECT_OPTION_LABELS:
                return SELECT_OPTION_LABELS[current_mode]

        return SELECT_OPTION_LABELS[MODE_AUTO]

    async def async_select_option(self, option: str) -> None:
        """Handle option selection."""
        mode = _label_to_mode(option)

        if mode == MODE_AUTO:
            await self.coordinator.async_reset_mode_override(self._piece_id)
        else:
            await self.coordinator.async_set_mode_override(self._piece_id, mode)

        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}

        piece_data = self.coordinator.data.get("pieces", {}).get(self._piece_id)
        if piece_data is None:
            return {}

        return {
            "calculated_mode": piece_data.get("mode"),
            "source": piece_data.get("source"),
        }


def _label_to_mode(label: str) -> str:
    """Convert a display label back to mode constant."""
    label_to_mode_map = {v: k for k, v in SELECT_OPTION_LABELS.items()}
    return label_to_mode_map.get(label, MODE_AUTO)
