"""Tests for the weekly schedule model."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.chauffage_intelligent.schedule import (
    ScheduleError,
    default_schedule,
    find_slot,
    format_time,
    grid_to_slots,
    next_transition,
    normalize_slots,
    parse_time,
    resolve_temperature,
    slots_to_grid,
)

MONDAY = datetime(2026, 9, 7)  # a Monday
SUNDAY = datetime(2026, 9, 13)


def slot(day, start, end, temperature):
    """Build a slot dict."""
    return {"day": day, "start": start, "end": end, "temperature": temperature}


# ---------------------------------------------------------------- time helpers


@pytest.mark.parametrize(
    ("value", "expected"),
    [("00:00", 0), ("07:30", 450), ("23:59", 1439), ("24:00", 1440)],
)
def test_parse_time(value, expected):
    """Times are parsed to minutes since midnight."""
    assert parse_time(value) == expected


@pytest.mark.parametrize("value", ["25:00", "abc", "-1:00", None])
def test_parse_time_rejects_invalid(value):
    """Out-of-range or malformed times raise."""
    with pytest.raises(ScheduleError):
        parse_time(value)


def test_format_time_round_trip():
    """format_time is the inverse of parse_time."""
    for minutes in (0, 450, 1439, 1440):
        assert parse_time(format_time(minutes)) == minutes


# ----------------------------------------------------------------- normalize


def test_normalize_sorts_and_keeps_slots():
    """Slots come back sorted by day then start."""
    result = normalize_slots(
        [slot(2, "10:00", "11:00", 20), slot(0, "07:00", "09:00", 19)]
    )
    assert [(s["day"], s["start"]) for s in result] == [(0, "07:00"), (2, "10:00")]


def test_normalize_drops_empty_slots():
    """A zero-length slot is discarded."""
    assert normalize_slots([slot(0, "08:00", "08:00", 20)]) == []


def test_normalize_merges_adjacent_equal_temperatures():
    """Touching slots at the same temperature become one."""
    result = normalize_slots(
        [slot(0, "07:00", "09:00", 20), slot(0, "09:00", "11:00", 20)]
    )
    assert result == [slot(0, "07:00", "11:00", 20.0)]


def test_normalize_keeps_adjacent_different_temperatures():
    """Touching slots at different temperatures stay separate."""
    result = normalize_slots(
        [slot(0, "07:00", "09:00", 20), slot(0, "09:00", "11:00", 18)]
    )
    assert result == [slot(0, "07:00", "09:00", 20.0), slot(0, "09:00", "11:00", 18.0)]


def test_normalize_later_slot_wins_on_overlap():
    """On overlap the slot defined last is kept."""
    result = normalize_slots(
        [slot(0, "07:00", "12:00", 20), slot(0, "09:00", "10:00", 16)]
    )
    assert result == [
        slot(0, "07:00", "09:00", 20.0),
        slot(0, "09:00", "10:00", 16.0),
        slot(0, "10:00", "12:00", 20.0),
    ]


def test_normalize_splits_slot_crossing_midnight():
    """A slot wrapping past midnight is split across two days."""
    result = normalize_slots([slot(0, "22:00", "06:00", 18)])
    assert result == [
        slot(0, "22:00", "24:00", 18.0),
        slot(1, "00:00", "06:00", 18.0),
    ]


def test_normalize_wraps_sunday_to_monday():
    """Sunday night rolls over onto Monday."""
    result = normalize_slots([slot(6, "23:00", "01:00", 18)])
    assert result == [
        slot(0, "00:00", "01:00", 18.0),
        slot(6, "23:00", "24:00", 18.0),
    ]


@pytest.mark.parametrize(
    "bad",
    [
        {"day": 7, "start": "07:00", "end": "09:00", "temperature": 20},
        {"day": -1, "start": "07:00", "end": "09:00", "temperature": 20},
        {"day": 0, "start": "07:00", "end": "09:00"},
        {"day": 0, "start": "07:00", "end": "09:00", "temperature": "chaud"},
    ],
)
def test_normalize_rejects_invalid_slots(bad):
    """Malformed slots raise instead of being silently dropped."""
    with pytest.raises(ScheduleError):
        normalize_slots([bad])


def test_normalize_handles_empty():
    """None and [] both normalize to []."""
    assert normalize_slots(None) == []
    assert normalize_slots([]) == []


# ------------------------------------------------------------------- resolve


def test_resolve_start_is_inclusive_end_is_exclusive():
    """A slot covers its start minute but not its end minute."""
    slots = normalize_slots([slot(0, "07:00", "09:00", 20)])

    assert resolve_temperature(slots, MONDAY.replace(hour=6, minute=59)) is None
    assert resolve_temperature(slots, MONDAY.replace(hour=7, minute=0)) == 20.0
    assert resolve_temperature(slots, MONDAY.replace(hour=8, minute=59)) == 20.0
    assert resolve_temperature(slots, MONDAY.replace(hour=9, minute=0)) is None


def test_resolve_uses_the_right_weekday():
    """A Monday slot does not apply on Tuesday."""
    slots = normalize_slots([slot(0, "07:00", "09:00", 20)])
    tuesday = MONDAY + timedelta(days=1)

    assert resolve_temperature(slots, MONDAY.replace(hour=8)) == 20.0
    assert resolve_temperature(slots, tuesday.replace(hour=8)) is None


def test_resolve_covers_end_of_day():
    """A slot ending at 24:00 covers 23:59."""
    slots = normalize_slots([slot(0, "22:00", "24:00", 18)])
    assert resolve_temperature(slots, MONDAY.replace(hour=23, minute=59)) == 18.0


def test_find_slot_returns_the_slot():
    """find_slot exposes the matching slot itself."""
    slots = normalize_slots([slot(0, "07:00", "09:00", 20)])
    assert find_slot(slots, MONDAY.replace(hour=8))["start"] == "07:00"
    assert find_slot(slots, MONDAY.replace(hour=10)) is None


# --------------------------------------------------------------- transitions


def test_next_transition_finds_slot_start():
    """From outside a slot, the next transition is its start."""
    slots = normalize_slots([slot(0, "07:00", "09:00", 20)])
    assert next_transition(slots, MONDAY.replace(hour=6)) == MONDAY.replace(hour=7)


def test_next_transition_finds_slot_end():
    """From inside a slot, the next transition is its end."""
    slots = normalize_slots([slot(0, "07:00", "09:00", 20)])
    assert next_transition(slots, MONDAY.replace(hour=8)) == MONDAY.replace(hour=9)


def test_next_transition_ignores_a_boundary_at_the_current_minute():
    """A boundary happening right now is not the *next* transition."""
    slots = normalize_slots([slot(0, "07:00", "09:00", 20)])
    assert next_transition(slots, MONDAY.replace(hour=7)) == MONDAY.replace(hour=9)


def test_next_transition_wraps_from_sunday_to_monday():
    """Late on Sunday, the next transition is next week's Monday slot."""
    slots = normalize_slots([slot(0, "07:00", "09:00", 20)])
    result = next_transition(slots, SUNDAY.replace(hour=20))
    assert result == (SUNDAY + timedelta(days=1)).replace(hour=7)


def test_next_transition_skips_boundaries_that_change_nothing():
    """Merged identical temperatures produce no spurious transition."""
    slots = normalize_slots(
        [slot(0, "07:00", "09:00", 20), slot(0, "09:00", "11:00", 20)]
    )
    assert next_transition(slots, MONDAY.replace(hour=8)) == MONDAY.replace(hour=11)


def test_next_transition_without_slots():
    """An empty schedule never transitions."""
    assert next_transition([], MONDAY) is None


def test_next_transition_with_constant_week():
    """A schedule covering the whole week at one temperature never transitions."""
    slots = normalize_slots(
        [slot(day, "00:00", "24:00", 20) for day in range(7)]
    )
    assert next_transition(slots, MONDAY.replace(hour=8)) is None


# --------------------------------------------------------------------- grid


def test_slots_to_grid_shape_and_content():
    """The grid is 7x48 and carries the slot temperature in its cells."""
    grid = slots_to_grid(normalize_slots([slot(0, "07:00", "09:00", 20)]))

    assert len(grid) == 7
    assert all(len(row) == 48 for row in grid)
    assert grid[0][13] is None  # 06:30
    assert grid[0][14] == 20.0  # 07:00
    assert grid[0][17] == 20.0  # 08:30
    assert grid[0][18] is None  # 09:00


def test_grid_round_trip():
    """slots -> grid -> slots is lossless for aligned slots."""
    slots = normalize_slots(
        [
            slot(0, "07:00", "09:00", 20),
            slot(0, "17:30", "22:00", 21),
            slot(6, "00:00", "24:00", 18),
        ]
    )
    assert normalize_slots(grid_to_slots(slots_to_grid(slots))) == slots


def test_grid_to_slots_merges_contiguous_cells():
    """Adjacent equal cells collapse into a single slot."""
    grid = [[None] * 48 for _ in range(7)]
    grid[1][10] = 20.0
    grid[1][11] = 20.0
    grid[1][12] = 20.0

    assert grid_to_slots(grid) == [slot(1, "05:00", "06:30", 20.0)]


def test_grid_to_slots_rejects_wrong_shape():
    """A grid with the wrong dimensions is refused."""
    with pytest.raises(ScheduleError):
        grid_to_slots([[None] * 48 for _ in range(6)])

    with pytest.raises(ScheduleError):
        grid_to_slots([[None] * 47 for _ in range(7)])


# ------------------------------------------------------------------ defaults


def test_default_schedule_uses_the_comfort_temperature():
    """The starting schedule paints the room's comfort value."""
    slots = default_schedule({"confort": 21, "eco": 17, "hors_gel": 7})

    assert slots
    assert {s["temperature"] for s in slots} == {21.0}
    assert {s["day"] for s in slots} == set(range(7))


def test_default_schedule_is_normalizable():
    """The generated schedule survives normalization untouched."""
    slots = default_schedule({"confort": 20})
    assert normalize_slots(slots) == normalize_slots(normalize_slots(slots))
