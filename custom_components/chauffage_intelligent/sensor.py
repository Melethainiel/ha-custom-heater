"""Sensor platform for Chauffage Intelligent."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SOURCE_DEFAUT,
    SOURCE_MANUEL,
    SOURCE_OFF,
    SOURCE_PLANNING,
)
from .coordinator import ChauffageIntelligentCoordinator
from .entity import ChauffageIntelligentEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from a config entry."""
    coordinator: ChauffageIntelligentCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[SensorEntity] = []
    for piece_id, piece_config in coordinator.pieces.items():
        entities.append(RoomTargetTempSensor(coordinator, piece_id, piece_config))
        entities.append(RoomSourceSensor(coordinator, piece_id, piece_config))

    async_add_entities(entities)


class RoomTargetTempSensor(ChauffageIntelligentEntity, SensorEntity):
    """The setpoint currently resolved for a room."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_translation_key = "temperature_cible"

    def __init__(
        self,
        coordinator: ChauffageIntelligentCoordinator,
        piece_id: str,
        piece_config: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, piece_id, piece_config)
        self._attr_unique_id = f"{DOMAIN}_{piece_id}_temperature_cible"

    @property
    def native_value(self) -> float | None:
        """Return the target temperature."""
        return self._piece_data.get("consigne")


class RoomSourceSensor(ChauffageIntelligentEntity, SensorEntity):
    """Where a room's setpoint comes from: planning, manual, fallback or off."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [SOURCE_PLANNING, SOURCE_MANUEL, SOURCE_DEFAUT, SOURCE_OFF]
    _attr_translation_key = "source_consigne"

    def __init__(
        self,
        coordinator: ChauffageIntelligentCoordinator,
        piece_id: str,
        piece_config: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, piece_id, piece_config)
        self._attr_unique_id = f"{DOMAIN}_{piece_id}_source_consigne"

    @property
    def native_value(self) -> str | None:
        """Return the setpoint source."""
        return self._piece_data.get("source")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the active slot and the next transition."""
        data = self._piece_data
        return {
            "creneau_actuel": data.get("creneau_actuel"),
            "prochain_changement": data.get("prochain_changement"),
        }
