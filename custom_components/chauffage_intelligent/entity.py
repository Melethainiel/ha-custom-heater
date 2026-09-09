"""Shared base entity for Chauffage Intelligent."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_PIECE_NAME, DOMAIN
from .coordinator import ChauffageIntelligentCoordinator


class ChauffageIntelligentEntity(CoordinatorEntity[ChauffageIntelligentCoordinator]):
    """Base entity bound to one room."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChauffageIntelligentCoordinator,
        piece_id: str,
        piece_config: dict[str, Any],
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._piece_id = piece_id
        self._piece_config = piece_config
        self._piece_name = piece_config.get(CONF_PIECE_NAME, piece_id)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, piece_id)},
            name=f"Chauffage {self._piece_name}",
            manufacturer="Chauffage Intelligent",
            model="Pièce",
        )

    @property
    def _piece_data(self) -> dict[str, Any]:
        """Return this room's slice of the coordinator data."""
        if self.coordinator.data is None:
            return {}
        return self.coordinator.data.get("pieces", {}).get(self._piece_id, {})
