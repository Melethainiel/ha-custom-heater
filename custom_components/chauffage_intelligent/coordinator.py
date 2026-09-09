"""DataUpdateCoordinator for Chauffage Intelligent."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.climate import HVACMode
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_PIECE_OFFSET,
    CONF_PIECE_RADIATEURS,
    CONF_PIECE_SONDE,
    CONF_PIECE_TEMPERATURES,
    CONF_PIECES,
    DEFAULT_OFFSET,
    DOMAIN,
    SETPOINT_TOLERANCE,
    SOURCE_DEFAUT,
    SOURCE_MANUEL,
    SOURCE_OFF,
    SOURCE_PLANNING,
    TEMP_ECO,
    TEMP_HORS_GEL,
)
from .schedule import find_slot, next_transition, resolve_temperature
from .storage import ScheduleStore

_LOGGER = logging.getLogger(__name__)

UNUSABLE_STATES = (STATE_UNAVAILABLE, STATE_UNKNOWN)


def as_entity_list(value: Any) -> list[str]:
    """Coerce a radiator config value into a list of entity ids."""
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


class ChauffageIntelligentCoordinator(DataUpdateCoordinator):
    """Resolve each room's setpoint from its schedule and push it to radiators."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        store: ScheduleStore,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

        self.pieces: dict[str, dict[str, Any]] = config[CONF_PIECES]
        self.store = store

        # Manual overrides: {piece_id: (temperature, expiry or None)}
        self._overrides: dict[str, tuple[float, datetime | None]] = {}

        # Rooms switched off from the climate entity.
        self._off_pieces: set[str] = set()

        self._unsub_transition: Any = None
        self._unsub_state: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @callback
    def async_start_listeners(self) -> None:
        """Watch radiator states so we can re-apply a setpoint immediately."""
        entities = self.radiator_entities()
        if not entities:
            return

        self._unsub_state = async_track_state_change_event(
            self.hass, entities, self._handle_radiator_state_change
        )

    @callback
    def async_shutdown_listeners(self) -> None:
        """Cancel every listener owned by the coordinator."""
        if self._unsub_transition is not None:
            self._unsub_transition()
            self._unsub_transition = None
        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None

    def radiator_entities(self) -> list[str]:
        """Return every radiator entity id across all rooms."""
        entities: list[str] = []
        for piece_config in self.pieces.values():
            for entity_id in as_entity_list(piece_config.get(CONF_PIECE_RADIATEURS)):
                if entity_id not in entities:
                    entities.append(entity_id)
        return entities

    @callback
    def _handle_radiator_state_change(self, event: Event[EventStateChangedData]) -> None:
        """Re-apply setpoints when a radiator changes on its own."""
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        if new_state is None:
            return

        # Only react to things that matter: availability, hvac mode, setpoint.
        if old_state is not None:
            same_state = old_state.state == new_state.state
            same_target = old_state.attributes.get("temperature") == new_state.attributes.get(
                "temperature"
            )
            if same_state and same_target:
                return

        _LOGGER.debug("Radiator %s changed, re-applying setpoints", event.data["entity_id"])
        self.hass.async_create_task(self.async_request_refresh())

    @callback
    def _schedule_next_transition(self, moments: list[datetime]) -> None:
        """Arm a timer on the earliest upcoming setpoint change."""
        if self._unsub_transition is not None:
            self._unsub_transition()
            self._unsub_transition = None

        if not moments:
            return

        moment = min(moments)
        self._unsub_transition = async_track_point_in_time(
            self.hass, self._handle_transition, moment
        )
        _LOGGER.debug("Next schedule transition at %s", moment)

    @callback
    def _handle_transition(self, _now: datetime) -> None:
        """Fire when a scheduled slot boundary is reached."""
        self._unsub_transition = None
        self.hass.async_create_task(self.async_request_refresh())

    # ------------------------------------------------------------------
    # Update loop
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Resolve and apply the setpoint of every room."""
        try:
            now = dt_util.now()
            pieces_data: dict[str, Any] = {}
            transitions: list[datetime] = []

            for piece_id, piece_config in self.pieces.items():
                slots = self.store.get(piece_id)

                temperature = self._get_temperature(piece_config)
                consigne, source = self._resolve_setpoint(piece_id, piece_config, slots, now)

                await self._apply_setpoint(piece_id, piece_config, consigne)

                transition = next_transition(slots, now)
                if transition is not None:
                    transitions.append(transition)

                slot = find_slot(slots, now)

                pieces_data[piece_id] = {
                    "consigne": consigne,
                    "source": source,
                    "temperature": temperature,
                    "creneau_actuel": _describe_slot(slot),
                    "prochain_changement": transition.isoformat() if transition else None,
                    "offset": float(piece_config.get(CONF_PIECE_OFFSET, DEFAULT_OFFSET)),
                    "off": piece_id in self._off_pieces,
                }

            self._schedule_next_transition(transitions)

            return {"pieces": pieces_data}

        except Exception as err:
            raise UpdateFailed(f"Error updating data: {err}") from err

    # ------------------------------------------------------------------
    # Setpoint resolution
    # ------------------------------------------------------------------

    def _resolve_setpoint(
        self,
        piece_id: str,
        piece_config: dict[str, Any],
        slots: list[dict[str, Any]],
        now: datetime,
    ) -> tuple[float, str]:
        """Resolve the target temperature for a room and where it comes from."""
        temperatures = piece_config.get(CONF_PIECE_TEMPERATURES, {})

        # 1. Room switched off -> frost protection.
        if piece_id in self._off_pieces:
            return float(temperatures.get(TEMP_HORS_GEL, 7)), SOURCE_OFF

        # 2. Active manual override.
        override = self._overrides.get(piece_id)
        if override is not None:
            temperature, expiry = override
            if expiry is None or now < expiry:
                return float(temperature), SOURCE_MANUEL
            del self._overrides[piece_id]

        # 3. Scheduled slot.
        scheduled = resolve_temperature(slots, now)
        if scheduled is not None:
            return scheduled, SOURCE_PLANNING

        # 4. Fallback: the room's eco temperature.
        return float(temperatures.get(TEMP_ECO, 17)), SOURCE_DEFAUT

    def _get_temperature(self, piece_config: dict[str, Any]) -> float | None:
        """Get the room temperature, falling back to a radiator's own sensor."""
        sonde_entity = piece_config.get(CONF_PIECE_SONDE)
        if sonde_entity:
            state = self.hass.states.get(sonde_entity)
            if state and state.state not in UNUSABLE_STATES:
                try:
                    return float(state.state)
                except ValueError:
                    pass

        for radiateur_entity in as_entity_list(piece_config.get(CONF_PIECE_RADIATEURS)):
            state = self.hass.states.get(radiateur_entity)
            if state and state.state not in UNUSABLE_STATES:
                current_temp = state.attributes.get("current_temperature")
                if current_temp is not None:
                    try:
                        return float(current_temp)
                    except (TypeError, ValueError):
                        pass

        return None

    # ------------------------------------------------------------------
    # Setpoint application
    # ------------------------------------------------------------------

    async def _apply_setpoint(
        self, piece_id: str, piece_config: dict[str, Any], consigne: float
    ) -> None:
        """Push the resolved setpoint to every radiator of a room.

        The setpoint is only written when it actually differs from what the
        radiator reports, so a value that failed to stick is retransmitted on
        the next cycle without any dedicated retry logic.
        """
        offset = float(piece_config.get(CONF_PIECE_OFFSET, DEFAULT_OFFSET) or 0.0)

        for entity_id in as_entity_list(piece_config.get(CONF_PIECE_RADIATEURS)):
            state = self.hass.states.get(entity_id)

            if state is None or state.state in UNUSABLE_STATES:
                _LOGGER.warning(
                    "Radiator %s (%s) is unavailable, skipping setpoint", entity_id, piece_id
                )
                continue

            target = self._clamp(consigne + offset, state.attributes)

            # A radiator that is off ignores the setpoint entirely.
            if state.state == HVACMode.OFF:
                _LOGGER.info("Radiator %s is off, turning it back to heat", entity_id)
                await self._call_climate("set_hvac_mode", entity_id, hvac_mode=HVACMode.HEAT)

            current_target = state.attributes.get("temperature")
            try:
                needs_write = current_target is None or abs(float(current_target) - target) >= (
                    SETPOINT_TOLERANCE
                )
            except (TypeError, ValueError):
                needs_write = True

            if not needs_write:
                continue

            _LOGGER.debug(
                "Setting %s to %.1f°C (room target %.1f, offset %+.1f, was %s)",
                entity_id,
                target,
                consigne,
                offset,
                current_target,
            )
            await self._call_climate("set_temperature", entity_id, temperature=target)

    @staticmethod
    def _clamp(target: float, attributes: dict[str, Any]) -> float:
        """Clamp a setpoint to the radiator's advertised range."""
        min_temp = attributes.get("min_temp")
        max_temp = attributes.get("max_temp")

        try:
            if min_temp is not None:
                target = max(target, float(min_temp))
            if max_temp is not None:
                target = min(target, float(max_temp))
        except (TypeError, ValueError):
            pass

        return round(target, 1)

    async def _call_climate(self, service: str, entity_id: str, **data: Any) -> None:
        """Call a climate service, logging failures instead of raising."""
        try:
            await self.hass.services.async_call(
                "climate",
                service,
                {"entity_id": entity_id, **data},
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 - a failing radiator must not break the cycle
            _LOGGER.error("climate.%s failed on %s: %s", service, entity_id, err)

    # ------------------------------------------------------------------
    # Public API (services, entities, websocket)
    # ------------------------------------------------------------------

    def get_schedule(self, piece_id: str) -> list[dict[str, Any]]:
        """Return the stored schedule of a room."""
        return self.store.get(piece_id)

    async def async_set_schedule(
        self, piece_id: str, slots: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Replace a room's schedule and re-apply immediately."""
        if piece_id not in self.pieces:
            raise ValueError(f"Unknown room: {piece_id}")

        normalized = await self.store.async_set(piece_id, slots)
        _LOGGER.info("Schedule updated for %s (%d slots)", piece_id, len(normalized))
        await self.async_request_refresh()
        return normalized

    async def async_set_override(
        self, piece_id: str, temperature: float, duree: int | None = None
    ) -> None:
        """Force a temperature for a room.

        Without an explicit duration the override lasts until the next
        scheduled transition, which is what one expects from a thermostat: nudge
        it now, let the planning take over at the next slot.
        """
        if piece_id not in self.pieces:
            raise ValueError(f"Unknown room: {piece_id}")

        now = dt_util.now()
        if duree:
            expiry = now + timedelta(minutes=duree)
        else:
            expiry = next_transition(self.store.get(piece_id), now)

        self._off_pieces.discard(piece_id)
        self._overrides[piece_id] = (float(temperature), expiry)
        _LOGGER.info(
            "Override set for %s: %.1f°C until %s", piece_id, temperature, expiry or "further notice"
        )
        await self.async_request_refresh()

    async def async_reset_override(self, piece_id: str | None = None) -> None:
        """Return a room (or every room) to its schedule."""
        if piece_id:
            self._overrides.pop(piece_id, None)
            self._off_pieces.discard(piece_id)
        else:
            self._overrides.clear()
            self._off_pieces.clear()
        await self.async_request_refresh()

    async def async_set_off(self, piece_id: str, off: bool) -> None:
        """Switch a room off (frost protection) or back to its schedule."""
        if off:
            self._off_pieces.add(piece_id)
            self._overrides.pop(piece_id, None)
        else:
            self._off_pieces.discard(piece_id)
        await self.async_request_refresh()

    def is_off(self, piece_id: str) -> bool:
        """Return True if the room is switched off."""
        return piece_id in self._off_pieces

    def get_override(self, piece_id: str) -> tuple[float, datetime | None] | None:
        """Return the active override for a room, if any."""
        return self._overrides.get(piece_id)


def _describe_slot(slot: dict[str, Any] | None) -> str | None:
    """Render the active slot as ``"07:00-09:00"`` for the UI."""
    if not slot:
        return None
    return f"{slot['start']}-{slot['end']}"
