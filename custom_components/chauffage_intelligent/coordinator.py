"""DataUpdateCoordinator for Chauffage Intelligent."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CALENDAR,
    CONF_DERIVATIVE_WINDOW,
    CONF_MIN_PREHEAT_TIME,
    CONF_PIECE_NAME,
    CONF_PIECE_RADIATEURS,
    CONF_PIECE_SONDE,
    CONF_PIECE_TEMPERATURES,
    CONF_PIECES,
    CONF_PRESENCE_TRACKERS,
    CONF_SECURITY_FACTOR,
    DEFAULT_HEATING_RATE,
    DOMAIN,
    EVENT_ABSENCE,
    EVENT_CONFORT,
    MODE_CONFORT,
    MODE_ECO,
    MODE_HORS_GEL,
    SOURCE_ANTICIPATION,
    SOURCE_CALENDAR,
    SOURCE_DEFAULT,
    SOURCE_OVERRIDE,
    SOURCE_PRESENCE,
    STATE_HOME,
)

_LOGGER = logging.getLogger(__name__)

# Learning constants
LEARNING_MIN_SAMPLES = 5  # Minimum samples before using learned rate
LEARNING_MAX_SAMPLES = 100  # Maximum samples to keep per condition
LEARNING_RATE_MIN = 0.3  # Minimum valid heating rate °C/h
LEARNING_RATE_MAX = 5.0  # Maximum valid heating rate °C/h


class HeatingRateLearner:
    """Learn and predict heating rates based on historical data."""

    def __init__(self, hass: HomeAssistant, storage_path: Path) -> None:
        """Initialize the learner."""
        self.hass = hass
        self.storage_path = storage_path
        self._data: dict[str, list[dict[str, Any]]] = {}
        self._load_data()

    def _load_data(self) -> None:
        """Load learned data from storage."""
        try:
            if self.storage_path.exists():
                with open(self.storage_path) as f:
                    self._data = json.load(f)
                _LOGGER.debug("Loaded heating rate data: %d rooms", len(self._data))
        except Exception as err:
            _LOGGER.warning("Failed to load heating rate data: %s", err)
            self._data = {}

    def _save_data(self) -> None:
        """Save learned data to storage."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w") as f:
                json.dump(self._data, f)
        except Exception as err:
            _LOGGER.warning("Failed to save heating rate data: %s", err)

    def record_observation(
        self,
        piece_id: str,
        heating_rate: float,
        outdoor_temp: float | None = None,
        hour: int | None = None,
    ) -> None:
        """Record a heating rate observation."""
        # Validate heating rate
        if heating_rate is None or heating_rate <= LEARNING_RATE_MIN:
            return  # Don't learn from cooling or very slow heating

        if heating_rate > LEARNING_RATE_MAX:
            return  # Ignore unrealistic values

        if hour is None:
            hour = dt_util.now().hour

        observation = {
            "rate": round(heating_rate, 3),
            "outdoor_temp": outdoor_temp,
            "hour": hour,
            "timestamp": dt_util.now().isoformat(),
        }

        if piece_id not in self._data:
            self._data[piece_id] = []

        self._data[piece_id].append(observation)

        # Keep only the last N samples
        if len(self._data[piece_id]) > LEARNING_MAX_SAMPLES:
            self._data[piece_id] = self._data[piece_id][-LEARNING_MAX_SAMPLES:]

        self._save_data()
        _LOGGER.debug(
            "Recorded heating rate for %s: %.2f°C/h (outdoor: %s, hour: %d)",
            piece_id,
            heating_rate,
            outdoor_temp,
            hour,
        )

    def get_predicted_rate(
        self,
        piece_id: str,
        outdoor_temp: float | None = None,
        hour: int | None = None,
    ) -> float | None:
        """Get predicted heating rate based on learned data."""
        if piece_id not in self._data:
            return None

        samples = self._data[piece_id]
        if len(samples) < LEARNING_MIN_SAMPLES:
            return None

        if hour is None:
            hour = dt_util.now().hour

        # Weight samples by similarity to current conditions
        weighted_sum = 0.0
        weight_total = 0.0

        for sample in samples:
            weight = 1.0

            # Time-of-day similarity (day vs night)
            sample_hour = sample.get("hour", 12)
            is_same_period = self._same_time_period(hour, sample_hour)
            if is_same_period:
                weight *= 1.5

            # Outdoor temperature similarity
            sample_outdoor = sample.get("outdoor_temp")
            if outdoor_temp is not None and sample_outdoor is not None:
                temp_diff = abs(outdoor_temp - sample_outdoor)
                if temp_diff <= 5:
                    weight *= 1.5
                elif temp_diff <= 10:
                    weight *= 1.0
                else:
                    weight *= 0.5

            weighted_sum += sample["rate"] * weight
            weight_total += weight

        if weight_total > 0:
            predicted = weighted_sum / weight_total
            _LOGGER.debug(
                "Predicted heating rate for %s: %.2f°C/h (from %d samples)",
                piece_id,
                predicted,
                len(samples),
            )
            return predicted

        return None

    def _same_time_period(self, hour1: int, hour2: int) -> bool:
        """Check if two hours are in the same time period."""

        # Define periods: night (22-6), morning (6-12), afternoon (12-18), evening (18-22)
        def get_period(h: int) -> int:
            if 6 <= h < 12:
                return 1
            elif 12 <= h < 18:
                return 2
            elif 18 <= h < 22:
                return 3
            else:
                return 0

        return get_period(hour1) == get_period(hour2)

    def get_stats(self, piece_id: str) -> dict[str, Any]:
        """Get learning statistics for a room."""
        if piece_id not in self._data:
            return {"samples": 0, "avg_rate": None, "min_rate": None, "max_rate": None}

        samples = self._data[piece_id]
        if not samples:
            return {"samples": 0, "avg_rate": None, "min_rate": None, "max_rate": None}

        rates = [s["rate"] for s in samples]
        return {
            "samples": len(samples),
            "avg_rate": round(sum(rates) / len(rates), 2),
            "min_rate": round(min(rates), 2),
            "max_rate": round(max(rates), 2),
        }


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

        # Heating rate learner
        storage_path = Path(hass.config.path(".storage")) / f"{DOMAIN}_learned_rates.json"
        self._learner = HeatingRateLearner(hass, storage_path)

        # Track previous mode to detect heating periods
        self._previous_modes: dict[str, str] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from sources and compute states."""
        try:
            # 1. Get calendar events
            calendar_events = await self._get_calendar_events()
            parsed_events = self._parse_calendar_events(calendar_events)

            # 2. Compute presence
            maison_occupee = self._compute_presence()

            # 3. Get outdoor temperature if available
            outdoor_temp = self._get_outdoor_temperature()

            # 4. Process each room
            pieces_data = {}
            for piece_id, piece_config in self.pieces.items():
                # Get current temperature
                temp_actuelle = self._get_temperature(piece_config)

                # Compute heating rate (measured)
                vitesse_mesuree = self._compute_derivative(piece_id, temp_actuelle)

                # Get learned rate for better predictions
                vitesse_apprise = self._learner.get_predicted_rate(piece_id, outdoor_temp)

                # Use learned rate if available and measured is None
                vitesse = vitesse_mesuree
                if vitesse is None and vitesse_apprise is not None:
                    vitesse = vitesse_apprise

                # Resolve mode
                mode, source = self._resolve_mode(piece_id, parsed_events, maison_occupee)

                # Get target temperature
                consigne = piece_config[CONF_PIECE_TEMPERATURES].get(mode, 19)

                # Compute preheat time using best available rate
                vitesse_pour_calcul = vitesse
                if vitesse_pour_calcul is None and vitesse_apprise is not None:
                    vitesse_pour_calcul = vitesse_apprise

                temps_prechauffe = self.compute_preheat_time(
                    temp_actuelle, consigne, vitesse_pour_calcul
                )

                # Find next comfort event for this room
                prochain_evenement = self._find_next_comfort_event(piece_id, calendar_events)
                prochain_evenement_iso = None
                if prochain_evenement:
                    start = prochain_evenement.get("start")
                    if isinstance(start, str):
                        prochain_evenement_iso = start
                    elif isinstance(start, datetime):
                        prochain_evenement_iso = start.isoformat()

                # Check if preheating should be triggered
                prechauffage_actif = self._check_preheat_trigger(
                    piece_id, calendar_events, temps_prechauffe
                )

                # If preheating triggered and currently in eco, switch to comfort
                if prechauffage_actif and mode == MODE_ECO:
                    mode = MODE_CONFORT
                    consigne = piece_config[CONF_PIECE_TEMPERATURES].get(MODE_CONFORT, 19)
                    source = SOURCE_ANTICIPATION

                # Learn from heating periods
                self._learn_heating_rate(piece_id, mode, vitesse_mesuree, outdoor_temp)

                # Apply temperature to radiators (supports multiple)
                radiateurs = piece_config.get(CONF_PIECE_RADIATEURS, [])
                # Handle legacy single radiator config
                if isinstance(radiateurs, str):
                    radiateurs = [radiateurs]
                await self._set_radiators_temperature(radiateurs, consigne)

                # Get learning stats
                learning_stats = self._learner.get_stats(piece_id)

                pieces_data[piece_id] = {
                    "mode": mode,
                    "source": source,
                    "consigne": consigne,
                    "temperature": temp_actuelle,
                    "vitesse_chauffe": vitesse,
                    "vitesse_apprise": vitesse_apprise,
                    "temps_prechauffage": temps_prechauffe,
                    "prechauffage_actif": prechauffage_actif,
                    "prochain_evenement": prochain_evenement_iso,
                    "learning_samples": learning_stats["samples"],
                    "learning_avg_rate": learning_stats["avg_rate"],
                }

                # Update previous mode
                self._previous_modes[piece_id] = mode

            return {
                "maison_occupee": maison_occupee,
                "outdoor_temp": outdoor_temp,
                "pieces": pieces_data,
            }

        except Exception as err:
            raise UpdateFailed(f"Error updating data: {err}") from err

    def _learn_heating_rate(
        self,
        piece_id: str,
        current_mode: str,
        heating_rate: float | None,
        outdoor_temp: float | None,
    ) -> None:
        """Learn from heating periods."""
        # Only learn when actively heating (comfort mode)
        if current_mode != MODE_CONFORT:
            return

        # Only learn if we have a valid heating rate
        if heating_rate is None or heating_rate <= 0:
            return

        # Record the observation
        self._learner.record_observation(
            piece_id,
            heating_rate,
            outdoor_temp,
        )

    def _get_outdoor_temperature(self) -> float | None:
        """Get outdoor temperature from weather entity if available."""
        # Try common weather entity patterns
        weather_entities = [
            "weather.home",
            "weather.maison",
            "sensor.outdoor_temperature",
            "sensor.temperature_exterieure",
        ]

        for entity_id in weather_entities:
            state = self.hass.states.get(entity_id)
            if state:
                # Weather entities have temperature in attributes
                if entity_id.startswith("weather."):
                    temp = state.attributes.get("temperature")
                    if temp is not None:
                        try:
                            return float(temp)
                        except ValueError:
                            pass
                # Sensor entities have temperature in state
                else:
                    if state.state not in ("unknown", "unavailable"):
                        try:
                            return float(state.state)
                        except ValueError:
                            pass

        return None

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
            # Normalize separators: support "confort - salon" and "confort salon"
            summary = summary.replace(" - ", " ")

            if summary == EVENT_ABSENCE:
                result["absence"] = True
            elif summary == EVENT_CONFORT:
                result["confort_global"] = True
            elif summary.startswith(f"{EVENT_CONFORT} "):
                piece_name = summary[len(EVENT_CONFORT) + 1 :].strip()
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

        # Fallback to first radiator's internal sensor
        radiateurs = piece_config.get(CONF_PIECE_RADIATEURS, [])
        # Handle legacy single radiator config
        if isinstance(radiateurs, str):
            radiateurs = [radiateurs]

        for radiateur_entity in radiateurs:
            state = self.hass.states.get(radiateur_entity)
            if state:
                current_temp = state.attributes.get("current_temperature")
                if current_temp is not None:
                    try:
                        return float(current_temp)
                    except ValueError:
                        pass

        return None

    def _compute_derivative(self, piece_id: str, current_temp: float | None) -> float | None:
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
            (t, temp) for t, temp in self._temp_history[piece_id] if t >= cutoff
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
        piece_name = piece_config.get(CONF_PIECE_NAME, piece_id).lower()

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
        piece_name = piece_config.get(CONF_PIECE_NAME, piece_id).lower()

        next_event = None
        next_start = None

        for event in calendar_events:
            summary = event.get("summary", "").lower().strip()
            # Normalize separators: support "confort - salon" and "confort salon"
            summary = summary.replace(" - ", " ")

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

    async def _set_radiators_temperature(
        self, radiator_entities: list[str], temperature: float
    ) -> None:
        """Set the target temperature on multiple radiators."""
        for radiator_entity in radiator_entities:
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
                _LOGGER.error("Failed to set temperature on %s: %s", radiator_entity, err)

    async def async_set_mode_override(
        self, piece_id: str, mode: str, duration: int | None = None
    ) -> None:
        """Set a manual mode override for a room."""
        expiry = None
        if duration:
            expiry = dt_util.now() + timedelta(minutes=duration)

        self._mode_overrides[piece_id] = (mode, expiry)
        _LOGGER.info("Mode override set for %s: %s (duration: %s min)", piece_id, mode, duration)
        await self.async_request_refresh()

    async def async_reset_mode_override(self, piece_id: str | None = None) -> None:
        """Reset mode override for a room or all rooms."""
        if piece_id:
            self._mode_overrides.pop(piece_id, None)
            _LOGGER.info("Mode override reset for %s", piece_id)
        else:
            self._mode_overrides.clear()
            _LOGGER.info("All mode overrides reset")
        await self.async_request_refresh()

    def get_learner(self) -> HeatingRateLearner:
        """Get the heating rate learner for external access."""
        return self._learner
