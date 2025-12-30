"""Sensor platform for Chauffage Intelligent."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_PIECE_NAME,
)
from .coordinator import ChauffageIntelligentCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from a config entry."""
    coordinator: ChauffageIntelligentCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    entities: list[SensorEntity] = []

    # Global mode sensor
    entities.append(GlobalModeSensor(coordinator))

    # Per-room sensors
    for piece_id, piece_config in coordinator.pieces.items():
        entities.extend(
            [
                RoomModeSensor(coordinator, piece_id, piece_config),
                RoomTargetTempSensor(coordinator, piece_id, piece_config),
                RoomPreheatTimeSensor(coordinator, piece_id, piece_config),
                RoomHeatingRateSensor(coordinator, piece_id, piece_config),
            ]
        )

    async_add_entities(entities)


class GlobalModeSensor(
    CoordinatorEntity[ChauffageIntelligentCoordinator], SensorEntity
):
    """Sensor showing the dominant mode across all rooms."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ChauffageIntelligentCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_mode_global"
        self._attr_name = "Chauffage Mode Global"

    @property
    def native_value(self) -> str | None:
        """Return the dominant mode."""
        if self.coordinator.data is None:
            return None

        pieces = self.coordinator.data.get("pieces", {})
        if not pieces:
            return None

        # Find most common mode
        modes = [p.get("mode") for p in pieces.values() if p.get("mode")]
        if not modes:
            return None

        return max(set(modes), key=modes.count)


class RoomModeSensor(
    CoordinatorEntity[ChauffageIntelligentCoordinator], SensorEntity
):
    """Sensor showing the calculated mode for a room."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChauffageIntelligentCoordinator,
        piece_id: str,
        piece_config: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._piece_id = piece_id
        self._attr_unique_id = f"{DOMAIN}_{piece_id}_mode_calcule"
        self._attr_name = f"{piece_config.get(CONF_PIECE_NAME, piece_id)} Mode"

    @property
    def native_value(self) -> str | None:
        """Return the calculated mode."""
        if self.coordinator.data is None:
            return None
        piece_data = self.coordinator.data.get("pieces", {}).get(self._piece_id)
        return piece_data.get("mode") if piece_data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        piece_data = self.coordinator.data.get("pieces", {}).get(self._piece_id)
        if piece_data:
            return {"source": piece_data.get("source")}
        return {}


class RoomTargetTempSensor(
    CoordinatorEntity[ChauffageIntelligentCoordinator], SensorEntity
):
    """Sensor showing the target temperature for a room."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator: ChauffageIntelligentCoordinator,
        piece_id: str,
        piece_config: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._piece_id = piece_id
        self._attr_unique_id = f"{DOMAIN}_{piece_id}_temperature_cible"
        self._attr_name = f"{piece_config.get(CONF_PIECE_NAME, piece_id)} Température Cible"

    @property
    def native_value(self) -> float | None:
        """Return the target temperature."""
        if self.coordinator.data is None:
            return None
        piece_data = self.coordinator.data.get("pieces", {}).get(self._piece_id)
        return piece_data.get("consigne") if piece_data else None


class RoomPreheatTimeSensor(
    CoordinatorEntity[ChauffageIntelligentCoordinator], SensorEntity
):
    """Sensor showing the estimated preheat time for a room."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "min"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: ChauffageIntelligentCoordinator,
        piece_id: str,
        piece_config: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._piece_id = piece_id
        self._attr_unique_id = f"{DOMAIN}_{piece_id}_temps_prechauffage"
        self._attr_name = f"{piece_config.get(CONF_PIECE_NAME, piece_id)} Temps Préchauffage"

    @property
    def native_value(self) -> int | None:
        """Return the estimated preheat time in minutes."""
        if self.coordinator.data is None:
            return None
        piece_data = self.coordinator.data.get("pieces", {}).get(self._piece_id)
        return piece_data.get("temps_prechauffage") if piece_data else None


class RoomHeatingRateSensor(
    CoordinatorEntity[ChauffageIntelligentCoordinator], SensorEntity
):
    """Sensor showing the current heating rate for a room."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "°C/h"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: ChauffageIntelligentCoordinator,
        piece_id: str,
        piece_config: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._piece_id = piece_id
        self._attr_unique_id = f"{DOMAIN}_{piece_id}_vitesse_chauffe"
        self._attr_name = f"{piece_config.get(CONF_PIECE_NAME, piece_id)} Vitesse Chauffe"

    @property
    def native_value(self) -> float | None:
        """Return the heating rate in °C/h."""
        if self.coordinator.data is None:
            return None
        piece_data = self.coordinator.data.get("pieces", {}).get(self._piece_id)
        rate = piece_data.get("vitesse_chauffe") if piece_data else None
        if rate is not None:
            return round(rate, 2)
        return None
