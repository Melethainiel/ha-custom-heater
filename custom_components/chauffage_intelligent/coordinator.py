"""DataUpdateCoordinator for Chauffage Intelligent."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    MODE_CONFORT,
    MODE_ECO,
    MODE_HORS_GEL,
    MODE_OFF,
    EVENT_ABSENCE,
    EVENT_CONFORT,
    SOURCE_CALENDAR,
    SOURCE_PRESENCE,
    SOURCE_DEFAULT,
    SOURCE_OVERRIDE,
    SOURCE_ANTICIPATION,
    STATE_HOME,
    CONF_CALENDAR,
    CONF_PRESENCE_TRACKERS,
    CONF_PIECES,
    CONF_SECURITY_FACTOR,
    CONF_MIN_PREHEAT_TIME,
    CONF_DERIVATIVE_WINDOW,
    DEFAULT_HEATING_RATE,
    CONF_PIECE_RADIATEUR,
    CONF_PIECE_SONDE,
    CONF_PIECE_TEMPERATURES,
)

_LOGGER = logging.getLogger(__name__)


class ChauffageIntelligentCoordinator(DataUpdateCoordinator):
    """Coordinator for Chauffage Intelligent."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

        self.calendar_entity = config[CONF_CALENDAR]
        self.presence_trackers = config[CONF_PRESENCE_TRACKERS]
        self.pieces = config[CONF_PIECES]
        self.security_factor = config[CONF_SECURITY_FACTOR]
        self.min_preheat_time = config[CONF_MIN_PREHEAT_TIME]
        self.derivative_window = config[CONF_DERIVATIVE_WINDOW]

        # Temperature history for derivative calculation
        self._temp_history: dict[str, list[tuple[datetime, float]]] = {}

        # Manual mode overrides: {piece_id: (mode, expiry_datetime or None)}
        self._mode_overrides: dict[str, tuple[str, datetime | None]] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from sources and compute states."""
        try:
            # 1. Get calendar events
            calendar_events = await self._get_calendar_events()
            parsed_events = self._parse_calendar_events(calendar_events)

            # 2. Compute presence
            maison_occupee = self._compute_presence()

            # 3. Process each room
            pieces_data = {}
            for piece_id, piece_config in self.pieces.items():
                # Get current temperature
                temp_actuelle = self._get_temperature(piece_config)

                # Compute heating rate
                vitesse = self._compute_derivative(piece_id, temp_actuelle)

                # Resolve mode
                mode, source = self._resolve_mode(
                    piece_id, parsed_events, maison_occupee
                )

                # Get target temperature
                consigne = piece_config[CONF_PIECE_TEMPERATURES].get(mode, 19)

                # Compute preheat time
                temps_prechauffe = self.compute_preheat_time(
                    temp_actuelle, consigne, vitesse
                )

                # Check if preheating should be triggered
                prechauffage_actif = self._check_preheat_trigger(
                    piece_id, calendar_events, temps_prechauffe
                )

                # If preheating triggered and currently in eco, switch to comfort
                if prechauffage_actif and mode == MODE_ECO:
                    mode = MODE_CONFORT
                    consigne = piece_config[CONF_PIECE_TEMPERATURES].get(
                        MODE_CONFORT, 19
                    )
                    source = SOURCE_ANTICIPATION

                # Apply temperature to radiator
                await self._set_radiator_temperature(
                    piece_config[CONF_PIECE_RADIATEUR], consigne
                )

                pieces_data[piece_id] = {
                    "mode": mode,
                    "source": source,
                    "consigne": consigne,
                    "temperature": temp_actuelle,
                    "vitesse_chauffe": vitesse,
                    "temps_prechauffage": temps_prechauffe,
                    "prechauffage_actif": prechauffage_actif,
                }

            return {
                "maison_occupee": maison_occupee,
                "pieces": pieces_data,
            }

        except Exception as err:
            raise UpdateFailed(f"Error updating data: {err}") from err

    async def _get_calendar_events(self) -> list[dict[str, Any]]:
        """Get current and upcoming events from the calendar."""
        now = dt_util.now()
        end = now + timedelta(hours=24)

        try:
            events = await self.hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": self.calendar_entity,
                    "start_date_time": now.isoformat(),
                    "end_date_time": end.isoformat(),
                },
                blocking=True,
                return_response=True,
            )
            return events.get(self.calendar_entity, {}).get("events", [])
        except Exception as err:
            _LOGGER.warning("Failed to get calendar events: %s", err)
            return []

    def _parse_calendar_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        """Parse calendar events into structured format."""
        result = {
            "absence": False,
            "confort_global": False,
            "confort_pieces": set(),
        }

        now = dt_util.now()

        for event in events:
            # Check if event is currently active
            start = event.get("start")
            end = event.get("end")

            if isinstance(start, str):
                start = dt_util.parse_datetime(start)
            if isinstance(end, str):
                end = dt_util.parse_datetime(end)

            if not start or not end:
                continue

            if not (start <= now <= end):
                continue

            summary = event.get("summary", "").lower().strip()

            if summary == EVENT_ABSENCE:
                result["absence"] = True
            elif summary == EVENT_CONFORT:
                result["confort_global"] = True
            elif summary.startswith(f"{EVENT_CONFORT} "):
                piece_name = summary[8:].strip()
                result["confort_pieces"].add(piece_name)

        return result

    def _compute_presence(self) -> bool:
        """Compute if anyone is home based on device trackers."""
        for tracker in self.presence_trackers:
            state = self.hass.states.get(tracker)
            if state and state.state == STATE_HOME:
                return True
        return False

    def _get_temperature(self, piece_config: dict[str, Any]) -> float | None:
        """Get temperature with fallback to radiator sensor."""
        # Try external sensor first
        sonde_entity = piece_config.get(CONF_PIECE_SONDE)
        if sonde_entity:
            state = self.hass.states.get(sonde_entity)
            if state and state.state not in ("unknown", "unavailable"):
                try:
                    return float(state.state)
                except ValueError:
                    pass

        # Fallback to radiator's internal sensor
        radiateur_entity = piece_config.get(CONF_PIECE_RADIATEUR)
        if radiateur_entity:
            state = self.hass.states.get(radiateur_entity)
            if state:
                current_temp = state.attributes.get("current_temperature")
                if current_temp is not None:
                    try:
                        return float(current_temp)
                    except ValueError:
                        pass

        return None

    def _compute_derivative(
        self, piece_id: str, current_temp: float | None
    ) -> float | None:
        """Compute heating rate in °C/h based on temperature history."""
        if current_temp is None:
            return None

        now = dt_util.now()

        # Initialize history for this piece if needed
        if piece_id not in self._temp_history:
            self._temp_history[piece_id] = []

        # Add current reading
        self._temp_history[piece_id].append((now, current_temp))

        # Clean old entries (keep only last derivative_window minutes)
        cutoff = now - timedelta(minutes=self.derivative_window)
        self._temp_history[piece_id] = [
            (t, temp)
            for t, temp in self._temp_history[piece_id]
            if t >= cutoff
        ]

        # Need at least 2 points to compute derivative
        history = self._temp_history[piece_id]
        if len(history) < 2:
            return None

        # Compute derivative from oldest to newest
        oldest_time, oldest_temp = history[0]
        newest_time, newest_temp = history[-1]

        time_diff_hours = (newest_time - oldest_time).total_seconds() / 3600
        if time_diff_hours <= 0:
            return None

        return (newest_temp - oldest_temp) / time_diff_hours

    def _resolve_mode(
        self,
        piece_id: str,
        parsed_events: dict[str, Any],
        maison_occupee: bool,
    ) -> tuple[str, str]:
        """Resolve the mode for a room based on priorities."""
        # Check for manual override first
        if piece_id in self._mode_overrides:
            mode, expiry = self._mode_overrides[piece_id]
            if expiry is None or dt_util.now() < expiry:
                return mode, SOURCE_OVERRIDE
            else:
                # Override expired, remove it
                del self._mode_overrides[piece_id]

        # Priority 1: Absence event → frost protection
        if parsed_events["absence"]:
            return MODE_HORS_GEL, SOURCE_CALENDAR

        # Priority 2: Nobody home → eco mode
        if not maison_occupee:
            return MODE_ECO, SOURCE_PRESENCE

        # Priority 3: Room-specific comfort event
        piece_config = self.pieces.get(piece_id, {})
        piece_name = piece_config.get("name", piece_id).lower()

        if piece_name in parsed_events["confort_pieces"]:
            return MODE_CONFORT, SOURCE_CALENDAR

        # Also check piece_id as fallback
        if piece_id.lower() in parsed_events["confort_pieces"]:
            return MODE_CONFORT, SOURCE_CALENDAR

        # Priority 4: Global comfort event
        if parsed_events["confort_global"]:
            return MODE_CONFORT, SOURCE_CALENDAR

        # Priority 5: Default to eco
        return MODE_ECO, SOURCE_DEFAULT

    def compute_preheat_time(
        self,
        current_temp: float | None,
        target_temp: float,
        heating_rate: float | None,
    ) -> int:
        """Compute estimated preheat time in minutes."""
        if current_temp is None:
            return self.min_preheat_time

        delta = target_temp - current_temp

        if delta <= 0:
            return 0  # Already at temperature

        # Use default heating rate if no data or room is cooling
        effective_rate = heating_rate
        if effective_rate is None or effective_rate <= 0:
            effective_rate = DEFAULT_HEATING_RATE

        # Calculate time in minutes
        raw_time = (delta / effective_rate) * 60
        time_with_margin = raw_time * self.security_factor

        return max(int(time_with_margin), self.min_preheat_time)

    def _check_preheat_trigger(
        self,
        piece_id: str,
        calendar_events: list[dict[str, Any]],
        preheat_time: int,
    ) -> bool:
        """Check if preheating should be triggered for upcoming event."""
        now = dt_util.now()

        # Find next comfort event for this piece
        next_comfort = self._find_next_comfort_event(piece_id, calendar_events)

        if not next_comfort:
            return False

        start = next_comfort.get("start")
        if isinstance(start, str):
            start = dt_util.parse_datetime(start)

        if not start:
            return False

        # Check if event is in the future
        if start <= now:
            return False

        minutes_until_event = (start - now).total_seconds() / 60

        return minutes_until_event <= preheat_time

    def _find_next_comfort_event(
        self, piece_id: str, calendar_events: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Find the next comfort event for a specific room."""
        now = dt_util.now()
        piece_config = self.pieces.get(piece_id, {})
        piece_name = piece_config.get("name", piece_id).lower()

        next_event = None
        next_start = None

        for event in calendar_events:
            summary = event.get("summary", "").lower().strip()

            # Check if this is a comfort event for this room or global
            is_relevant = (
                summary == EVENT_CONFORT
                or summary == f"{EVENT_CONFORT} {piece_name}"
                or summary == f"{EVENT_CONFORT} {piece_id.lower()}"
            )

            if not is_relevant:
                continue

            start = event.get("start")
            if isinstance(start, str):
                start = dt_util.parse_datetime(start)

            if not start or start <= now:
                continue

            if next_start is None or start < next_start:
                next_event = event
                next_start = start

        return next_event

    async def _set_radiator_temperature(
        self, radiator_entity: str, temperature: float
    ) -> None:
        """Set the target temperature on a radiator."""
        try:
            await self.hass.services.async_call(
                "climate",
                "set_temperature",
                {
                    "entity_id": radiator_entity,
                    "temperature": temperature,
                },
                blocking=True,
            )
        except Exception as err:
            _LOGGER.error(
                "Failed to set temperature on %s: %s", radiator_entity, err
            )

    async def async_set_mode_override(
        self, piece_id: str, mode: str, duration: int | None = None
    ) -> None:
        """Set a manual mode override for a room."""
        expiry = None
        if duration:
            expiry = dt_util.now() + timedelta(minutes=duration)

        self._mode_overrides[piece_id] = (mode, expiry)
        await self.async_request_refresh()

    async def async_reset_mode_override(self, piece_id: str | None = None) -> None:
        """Reset mode override for a room or all rooms."""
        if piece_id:
            self._mode_overrides.pop(piece_id, None)
        else:
            self._mode_overrides.clear()
        await self.async_request_refresh()
