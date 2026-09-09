"""Climate platform for Chauffage Intelligent."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_PIECE_RADIATEURS,
    CONF_PIECE_SONDE,
    CONF_PIECE_TEMPERATURES,
    CONF_PIECE_TYPE,
    DOMAIN,
    PRESET_PLANNING,
    SELECT_OPTION_LABELS,
    SOURCE_MANUEL,
    TEMP_CONFORT,
    TEMP_ECO,
    TEMP_HORS_GEL,
)
from .coordinator import ChauffageIntelligentCoordinator, as_entity_list
from .entity import ChauffageIntelligentEntity

# Preset labels shown in the UI, mapped back to a palette key.
PRESET_TO_KEY = {label: key for key, label in SELECT_OPTION_LABELS.items()}
PRESET_MODES = list(SELECT_OPTION_LABELS.values())
PRESET_PLANNING_LABEL = SELECT_OPTION_LABELS[PRESET_PLANNING]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate entities from a config entry."""
    coordinator: ChauffageIntelligentCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        ChauffageIntelligentClimate(coordinator, piece_id, piece_config)
        for piece_id, piece_config in coordinator.pieces.items()
    )


class ChauffageIntelligentClimate(ChauffageIntelligentEntity, ClimateEntity):
    """Climate entity for a room driven by its weekly schedule."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_preset_modes = PRESET_MODES
    _attr_target_temperature_step = 0.5
    _attr_name = None  # the device name carries the room

    def __init__(
        self,
        coordinator: ChauffageIntelligentCoordinator,
        piece_id: str,
        piece_config: dict[str, Any],
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, piece_id, piece_config)
        self._attr_unique_id = f"{DOMAIN}_{piece_id}"

        temps = piece_config.get(CONF_PIECE_TEMPERATURES, {})
        self._attr_min_temp = min(float(temps.get(TEMP_HORS_GEL, 7)), 7.0)
        self._attr_max_temp = max(float(temps.get(TEMP_CONFORT, 22)) + 3.0, 25.0)

    @property
    def current_temperature(self) -> float | None:
        """Return the room temperature."""
        return self._piece_data.get("temperature")

    @property
    def target_temperature(self) -> float | None:
        """Return the resolved setpoint."""
        return self._piece_data.get("consigne")

    @property
    def hvac_mode(self) -> HVACMode:
        """Return HEAT unless the room was switched off."""
        return HVACMode.OFF if self._piece_data.get("off") else HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        """Report whether the room is currently calling for heat."""
        if self._piece_data.get("off"):
            return HVACAction.OFF

        current = self._piece_data.get("temperature")
        target = self._piece_data.get("consigne")
        if current is None or target is None:
            return None

        return HVACAction.HEATING if current < target else HVACAction.IDLE

    @property
    def preset_mode(self) -> str:
        """Return the palette preset matching the active override, else Planning."""
        if self._piece_data.get("source") != SOURCE_MANUEL:
            return PRESET_PLANNING_LABEL

        consigne = self._piece_data.get("consigne")
        temps = self._piece_config.get(CONF_PIECE_TEMPERATURES, {})
        for key in (TEMP_CONFORT, TEMP_ECO, TEMP_HORS_GEL):
            if key in temps and consigne is not None and abs(float(temps[key]) - consigne) < 0.05:
                return SELECT_OPTION_LABELS[key]

        # A free temperature was forced: no preset matches it.
        return PRESET_PLANNING_LABEL

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostics about how the setpoint was chosen."""
        data = self._piece_data
        return {
            "source_consigne": data.get("source"),
            "creneau_actuel": data.get("creneau_actuel"),
            "prochain_changement": data.get("prochain_changement"),
            "offset": data.get("offset"),
            "radiateur_entities": as_entity_list(self._piece_config.get(CONF_PIECE_RADIATEURS)),
            "sonde_entity": self._piece_config.get(CONF_PIECE_SONDE),
            "type_piece": self._piece_config.get(CONF_PIECE_TYPE),
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Force a temperature until the next scheduled transition."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        await self.coordinator.async_set_override(self._piece_id, float(temperature))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Switch the room off (frost protection) or back to its schedule."""
        await self.coordinator.async_set_off(self._piece_id, hvac_mode == HVACMode.OFF)

    async def async_turn_on(self) -> None:
        """Return the room to its schedule."""
        await self.coordinator.async_set_off(self._piece_id, False)

    async def async_turn_off(self) -> None:
        """Switch the room to frost protection."""
        await self.coordinator.async_set_off(self._piece_id, True)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Apply a palette preset, or hand control back to the schedule."""
        key = PRESET_TO_KEY.get(preset_mode)

        if key is None or key == PRESET_PLANNING:
            await self.coordinator.async_reset_override(self._piece_id)
            return

        temps = self._piece_config.get(CONF_PIECE_TEMPERATURES, {})
        await self.coordinator.async_set_override(self._piece_id, float(temps.get(key, 19)))
