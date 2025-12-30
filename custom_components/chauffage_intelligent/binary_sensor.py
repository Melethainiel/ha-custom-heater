"""Binary sensor platform for Chauffage Intelligent."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
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
    """Set up binary sensor entities from a config entry."""
    coordinator: ChauffageIntelligentCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    entities: list[BinarySensorEntity] = []

    # Global presence sensor
    entities.append(HomeOccupiedSensor(coordinator))

    # Per-room preheat active sensors
    for piece_id, piece_config in coordinator.pieces.items():
        entities.append(RoomPreheatActiveSensor(coordinator, piece_id, piece_config))

    async_add_entities(entities)


class HomeOccupiedSensor(
    CoordinatorEntity[ChauffageIntelligentCoordinator], BinarySensorEntity
):
    """Binary sensor showing if anyone is home."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, coordinator: ChauffageIntelligentCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_maison_occupee"
        self._attr_name = "Chauffage Maison Occupée"

    @property
    def is_on(self) -> bool | None:
        """Return True if someone is home."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("maison_occupee")


class RoomPreheatActiveSensor(
    CoordinatorEntity[ChauffageIntelligentCoordinator], BinarySensorEntity
):
    """Binary sensor showing if preheating is active for a room."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.HEAT

    def __init__(
        self,
        coordinator: ChauffageIntelligentCoordinator,
        piece_id: str,
        piece_config: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._piece_id = piece_id
        self._attr_unique_id = f"{DOMAIN}_{piece_id}_prechauffage_actif"
        self._attr_name = f"{piece_config.get(CONF_PIECE_NAME, piece_id)} Préchauffage Actif"

    @property
    def is_on(self) -> bool | None:
        """Return True if preheating is active."""
        if self.coordinator.data is None:
            return None
        piece_data = self.coordinator.data.get("pieces", {}).get(self._piece_id)
        return piece_data.get("prechauffage_actif") if piece_data else None
