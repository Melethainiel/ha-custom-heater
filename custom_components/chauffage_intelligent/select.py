"""Select platform for Chauffage Intelligent."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_PIECE_TEMPERATURES,
    DOMAIN,
    PRESET_PLANNING,
    SELECT_OPTION_LABELS,
    SELECT_OPTIONS,
    SOURCE_MANUEL,
    TEMP_CONFORT,
    TEMP_ECO,
    TEMP_HORS_GEL,
)
from .coordinator import ChauffageIntelligentCoordinator
from .entity import ChauffageIntelligentEntity

LABEL_TO_KEY = {label: key for key, label in SELECT_OPTION_LABELS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities from a config entry."""
    coordinator: ChauffageIntelligentCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        ChauffageIntelligentModeSelect(coordinator, piece_id, piece_config)
        for piece_id, piece_config in coordinator.pieces.items()
    )


class ChauffageIntelligentModeSelect(ChauffageIntelligentEntity, SelectEntity):
    """Quick switch between the schedule and a palette temperature."""

    _attr_translation_key = "mode"
    _attr_options = [SELECT_OPTION_LABELS[option] for option in SELECT_OPTIONS]

    def __init__(
        self,
        coordinator: ChauffageIntelligentCoordinator,
        piece_id: str,
        piece_config: dict[str, Any],
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, piece_id, piece_config)
        self._attr_unique_id = f"{DOMAIN}_{piece_id}_mode_select"

    @property
    def current_option(self) -> str:
        """Return the palette entry matching the override, else Planning."""
        data = self._piece_data

        if data.get("source") != SOURCE_MANUEL:
            return SELECT_OPTION_LABELS[PRESET_PLANNING]

        consigne = data.get("consigne")
        temps = self._piece_config.get(CONF_PIECE_TEMPERATURES, {})
        for key in (TEMP_CONFORT, TEMP_ECO, TEMP_HORS_GEL):
            if key in temps and consigne is not None and abs(float(temps[key]) - consigne) < 0.05:
                return SELECT_OPTION_LABELS[key]

        return SELECT_OPTION_LABELS[PRESET_PLANNING]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the resolved setpoint and its source."""
        data = self._piece_data
        return {
            "consigne": data.get("consigne"),
            "source": data.get("source"),
        }

    async def async_select_option(self, option: str) -> None:
        """Apply the selected palette entry."""
        key = LABEL_TO_KEY.get(option, PRESET_PLANNING)

        if key == PRESET_PLANNING:
            await self.coordinator.async_reset_override(self._piece_id)
            return

        temps = self._piece_config.get(CONF_PIECE_TEMPERATURES, {})
        await self.coordinator.async_set_override(self._piece_id, float(temps.get(key, 19)))
