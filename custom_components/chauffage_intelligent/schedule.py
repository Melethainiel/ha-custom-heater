"""Weekly schedule model for Chauffage Intelligent.

A schedule is a list of slots. Each slot is a plain dict::

    {"day": 0, "start": "07:00", "end": "09:00", "temperature": 20.0}

``day`` is 0 for Monday through 6 for Sunday, matching
:meth:`datetime.datetime.weekday`. Slots never cross midnight: a slot spanning
two days is split during normalization. ``start`` is inclusive, ``end`` is
exclusive, and ``end`` may be ``"24:00"`` to reach the end of the day.

Everything here is a pure function so the scheduling logic can be unit tested
without a Home Assistant instance.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .const import (
    SCHEDULE_DAYS,
    SCHEDULE_SLOTS_PER_DAY,
    SCHEDULE_STEP_MINUTES,
    TEMP_CONFORT,
)

MINUTES_PER_DAY = 24 * 60

ATTR_DAY = "day"
ATTR_START = "start"
ATTR_END = "end"
ATTR_TEMPERATURE = "temperature"


class ScheduleError(ValueError):
    """Raised when a schedule payload cannot be parsed."""


def parse_time(value: str) -> int:
    """Convert a ``"HH:MM"`` string to minutes since midnight."""
    if isinstance(value, int):
        minutes = value
    else:
        try:
            hours_str, _, minutes_str = str(value).partition(":")
            minutes = int(hours_str) * 60 + int(minutes_str)
        except (TypeError, ValueError) as err:
            raise ScheduleError(f"Invalid time: {value!r}") from err

    if not 0 <= minutes <= MINUTES_PER_DAY:
        raise ScheduleError(f"Time out of range: {value!r}")

    return minutes


def format_time(minutes: int) -> str:
    """Convert minutes since midnight to a ``"HH:MM"`` string."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def normalize_slots(slots: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Validate and canonicalize a list of slots.

    Splits slots crossing midnight, resolves overlaps in favour of the slot
    defined last, drops empty slots and merges adjacent slots sharing the same
    temperature. The result is sorted by day then start time.
    """
    if not slots:
        return []

    # Expand into (day, start, end, temperature) tuples, splitting at midnight.
    expanded: list[tuple[int, int, int, float]] = []
    for slot in slots:
        try:
            day = int(slot[ATTR_DAY])
            temperature = float(slot[ATTR_TEMPERATURE])
        except (KeyError, TypeError, ValueError) as err:
            raise ScheduleError(f"Invalid slot: {slot!r}") from err

        if not 0 <= day < SCHEDULE_DAYS:
            raise ScheduleError(f"Invalid day: {day}")

        start = parse_time(slot[ATTR_START])
        end = parse_time(slot[ATTR_END])

        if end == start:
            continue

        if end < start:
            # Crosses midnight: split into today's tail and tomorrow's head.
            expanded.append((day, start, MINUTES_PER_DAY, temperature))
            expanded.append(((day + 1) % SCHEDULE_DAYS, 0, end, temperature))
        else:
            expanded.append((day, start, end, temperature))

    # Resolve overlaps by painting onto a per-day minute map: later slots win.
    painted: dict[int, dict[int, float]] = {day: {} for day in range(SCHEDULE_DAYS)}
    for day, start, end, temperature in expanded:
        day_map = painted[day]
        for minute in range(start, end):
            day_map[minute] = temperature

    # Read the minute maps back as contiguous runs.
    result: list[dict[str, Any]] = []
    for day in range(SCHEDULE_DAYS):
        day_map = painted[day]
        if not day_map:
            continue

        run_start: int | None = None
        run_temp: float | None = None

        for minute in range(MINUTES_PER_DAY + 1):
            temperature = day_map.get(minute)
            if temperature != run_temp:
                if run_start is not None and run_temp is not None:
                    result.append(_make_slot(day, run_start, minute, run_temp))
                run_start = minute if temperature is not None else None
                run_temp = temperature

    return result


def _make_slot(day: int, start: int, end: int, temperature: float) -> dict[str, Any]:
    """Build a slot dict from minute offsets."""
    return {
        ATTR_DAY: day,
        ATTR_START: format_time(start),
        ATTR_END: format_time(end),
        ATTR_TEMPERATURE: round(float(temperature), 1),
    }


def find_slot(slots: list[dict[str, Any]], when: datetime) -> dict[str, Any] | None:
    """Return the slot covering ``when``, or ``None``."""
    day = when.weekday()
    minute = when.hour * 60 + when.minute

    for slot in slots:
        if int(slot[ATTR_DAY]) != day:
            continue
        if parse_time(slot[ATTR_START]) <= minute < parse_time(slot[ATTR_END]):
            return slot

    return None


def resolve_temperature(slots: list[dict[str, Any]], when: datetime) -> float | None:
    """Return the scheduled temperature at ``when``, or ``None`` if uncovered."""
    slot = find_slot(slots, when)
    return float(slot[ATTR_TEMPERATURE]) if slot else None


def next_transition(slots: list[dict[str, Any]], when: datetime) -> datetime | None:
    """Return the next datetime at which the scheduled temperature changes.

    Looks ahead one full week. Returns ``None`` when the schedule is empty or
    holds a single temperature covering the whole week (no transition ever).
    """
    if not slots:
        return None

    # Collect every boundary as (weekday, minute) pairs.
    boundaries: set[tuple[int, int]] = set()
    for slot in slots:
        day = int(slot[ATTR_DAY])
        start = parse_time(slot[ATTR_START])
        end = parse_time(slot[ATTR_END])
        boundaries.add((day, start))
        if end >= MINUTES_PER_DAY:
            boundaries.add(((day + 1) % SCHEDULE_DAYS, 0))
        else:
            boundaries.add((day, end))

    current = resolve_temperature(slots, when)
    base = when.replace(second=0, microsecond=0)

    candidates = []
    for day, minute in boundaries:
        # Days until that weekday, then the minute offset within it.
        days_ahead = (day - when.weekday()) % SCHEDULE_DAYS
        moment = (base + timedelta(days=days_ahead)).replace(hour=0, minute=0) + timedelta(
            minutes=minute
        )
        if moment <= base:
            moment += timedelta(days=SCHEDULE_DAYS)
        candidates.append(moment)

    for moment in sorted(candidates):
        if resolve_temperature(slots, moment) != current:
            return moment

    return None


def slots_to_grid(slots: list[dict[str, Any]]) -> list[list[float | None]]:
    """Render slots as a ``SCHEDULE_DAYS`` x ``SCHEDULE_SLOTS_PER_DAY`` grid."""
    grid: list[list[float | None]] = [
        [None] * SCHEDULE_SLOTS_PER_DAY for _ in range(SCHEDULE_DAYS)
    ]

    for slot in normalize_slots(slots):
        day = int(slot[ATTR_DAY])
        start = parse_time(slot[ATTR_START]) // SCHEDULE_STEP_MINUTES
        end = parse_time(slot[ATTR_END]) // SCHEDULE_STEP_MINUTES
        for cell in range(start, min(end, SCHEDULE_SLOTS_PER_DAY)):
            grid[day][cell] = float(slot[ATTR_TEMPERATURE])

    return grid


def grid_to_slots(grid: list[list[float | None]]) -> list[dict[str, Any]]:
    """Compress a grid back into slots, merging contiguous equal cells."""
    if len(grid) != SCHEDULE_DAYS:
        raise ScheduleError(f"Grid must have {SCHEDULE_DAYS} rows, got {len(grid)}")

    slots: list[dict[str, Any]] = []

    for day, row in enumerate(grid):
        if len(row) != SCHEDULE_SLOTS_PER_DAY:
            raise ScheduleError(
                f"Grid row {day} must have {SCHEDULE_SLOTS_PER_DAY} cells, got {len(row)}"
            )

        run_start: int | None = None
        run_temp: float | None = None

        for cell in range(SCHEDULE_SLOTS_PER_DAY + 1):
            value = row[cell] if cell < SCHEDULE_SLOTS_PER_DAY else None
            temperature = None if value is None else float(value)

            if temperature != run_temp:
                if run_start is not None and run_temp is not None:
                    slots.append(
                        _make_slot(
                            day,
                            run_start * SCHEDULE_STEP_MINUTES,
                            cell * SCHEDULE_STEP_MINUTES,
                            run_temp,
                        )
                    )
                run_start = cell if temperature is not None else None
                run_temp = temperature

    return slots


def default_schedule(temperatures: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a sensible starting schedule from a room's temperature palette."""
    confort = float(temperatures.get(TEMP_CONFORT, 19))

    slots: list[dict[str, Any]] = []
    for day in range(5):  # Monday to Friday
        slots.append(_make_slot(day, parse_time("07:00"), parse_time("09:00"), confort))
        slots.append(_make_slot(day, parse_time("17:30"), parse_time("22:00"), confort))
    for day in (5, 6):  # Weekend
        slots.append(_make_slot(day, parse_time("08:00"), parse_time("22:00"), confort))

    return slots
