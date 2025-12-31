"""Climate platform for Chauffage Intelligent."""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MODE_CONFORT,
    MODE_ECO,
    MODE_HORS_GEL,
    MODE_OFF,
    CONF_PIECE_NAME,
    CONF_PIECE_RADIATEUR,
    CONF_PIECE_SONDE,
    CONF_PIECE_TYPE,
    CONF_PIECE_TEMPERATURES,
)
from .coordinator import ChauffageIntelligentCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate entities from a config entry."""
    coordinator: ChauffageIntelligentCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    entities = [
        ChauffageIntelligentClimate(coordinator, piece_id, piece_config)
        for piece_id, piece_config in coordinator.pieces.items()
    ]

    async_add_entities(entities)


class ChauffageIntelligentClimate(
    CoordinatorEntity[ChauffageIntelligentCoordinator], ClimateEntity
):
    """Climate entity for a room managed by Chauffage Intelligent."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    def __init__(
        self,
        coordinator: ChauffageIntelligentCoordinator,
        piece_id: str,
        piece_config: dict[str, Any],
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._piece_id = piece_id
        self._piece_config = piece_config

        self._attr_unique_id = f"{DOMAIN}_{piece_id}"
        self._attr_name = f"Chauffage {piece_config.get(CONF_PIECE_NAME, piece_id)}"

        # Set temperature limits
        temps = piece_config.get(CONF_PIECE_TEMPERATURES, {})
        self._attr_min_temp = temps.get(MODE_HORS_GEL, 7)
        self._attr_max_temp = temps.get(MODE_CONFORT, 22) + 2

    @property
    def _piece_data(self) -> dict[str, Any] | None:
        """Get current data for this room from coordinator."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("pieces", {}).get(self._piece_id)

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        if self._piece_data:
            return self._piece_data.get("temperature")
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        if self._piece_data:
            return self._piece_data.get("consigne")
        return None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        if self._piece_data:
            mode = self._piece_data.get("mode")
            if mode == MODE_OFF:
                return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "radiateur_entity": self._piece_config.get(CONF_PIECE_RADIATEUR),
            "sonde_entity": self._piece_config.get(CONF_PIECE_SONDE),
            "type_piece": self._piece_config.get(CONF_PIECE_TYPE),
        }

        if self._piece_data:
            attrs.update(
                {
                    "mode_calcule": self._piece_data.get("mode"),
                    "source_mode": self._piece_data.get("source"),
                    "temperature_cible": self._piece_data.get("consigne"),
                    "temperature_actuelle": self._piece_data.get("temperature"),
                    "vitesse_chauffe": self._piece_data.get("vitesse_chauffe"),
                    "vitesse_apprise": self._piece_data.get("vitesse_apprise"),
                    "temps_prechauffage": self._piece_data.get("temps_prechauffage"),
                    "prechauffage_actif": self._piece_data.get("prechauffage_actif"),
                    "prochain_evenement": self._piece_data.get("prochain_evenement"),
                    "learning_samples": self._piece_data.get("learning_samples"),
                    "learning_avg_rate": self._piece_data.get("learning_avg_rate"),
                }
            )

        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature (manual override)."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        # Determine which mode this temperature corresponds to
        temps = self._piece_config.get(CONF_PIECE_TEMPERATURES, {})

        if temperature >= temps.get(MODE_CONFORT, 19):
            mode = MODE_CONFORT
        elif temperature >= temps.get(MODE_ECO, 17):
            mode = MODE_ECO
        else:
            mode = MODE_HORS_GEL

        # Set override
        await self.coordinator.async_set_mode_override(self._piece_id, mode)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_set_mode_override(self._piece_id, MODE_OFF)
        else:
            # Clear override to return to calculated mode
            await self.coordinator.async_reset_mode_override(self._piece_id)
