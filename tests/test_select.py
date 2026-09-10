"""Tests for the mode select entity."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.chauffage_intelligent.const import (
    DOMAIN,
    SOURCE_DEFAUT,
    SOURCE_MANUEL,
    SOURCE_PLANNING,
)
from custom_components.chauffage_intelligent.select import (
    ChauffageIntelligentModeSelect,
    async_setup_entry,
)


@pytest.fixture
def entity(coordinator):
    """A mode select for the office."""
    return ChauffageIntelligentModeSelect(coordinator, "bureau", coordinator.pieces["bureau"])


def set_data(coordinator, **overrides):
    """Publish coordinator data for the office."""
    payload = {"consigne": 19.0, "source": SOURCE_PLANNING}
    payload.update(overrides)
    coordinator.data = {"pieces": {"bureau": payload}}


def test_options(entity):
    """The four options mirror the climate presets."""
    assert entity.options == ["Planning", "Confort", "Éco", "Hors-gel"]
    assert entity.unique_id == f"{DOMAIN}_bureau_mode_select"


def test_defaults_to_planning(entity, coordinator):
    """Without an override the select sits on Planning."""
    set_data(coordinator, source=SOURCE_PLANNING)
    assert entity.current_option == "Planning"

    set_data(coordinator, source=SOURCE_DEFAUT)
    assert entity.current_option == "Planning"


def test_without_data(entity, coordinator):
    """Before the first refresh the select still reports Planning."""
    coordinator.data = None
    assert entity.current_option == "Planning"


@pytest.mark.parametrize(
    ("consigne", "expected"), [(19.0, "Confort"), (17.0, "Éco"), (7.0, "Hors-gel")]
)
def test_reflects_the_active_override(entity, coordinator, consigne, expected):
    """An override on a palette value selects that option."""
    set_data(coordinator, source=SOURCE_MANUEL, consigne=consigne)
    assert entity.current_option == expected


def test_free_temperature_falls_back_to_planning(entity, coordinator):
    """An off-palette override matches no option."""
    set_data(coordinator, source=SOURCE_MANUEL, consigne=21.5)
    assert entity.current_option == "Planning"


def test_attributes(entity, coordinator):
    """The setpoint and its source are exposed."""
    set_data(coordinator)
    assert entity.extra_state_attributes == {"consigne": 19.0, "source": SOURCE_PLANNING}


async def test_selecting_planning_clears_the_override(entity, coordinator):
    """Planning returns control to the schedule."""
    coordinator.async_reset_override = AsyncMock()

    await entity.async_select_option("Planning")

    coordinator.async_reset_override.assert_awaited_once_with("bureau")


@pytest.mark.parametrize(
    ("option", "expected"), [("Confort", 19.0), ("Éco", 17.0), ("Hors-gel", 7.0)]
)
async def test_selecting_a_palette_option(entity, coordinator, option, expected):
    """A palette option forces the matching temperature."""
    coordinator.async_set_override = AsyncMock()

    await entity.async_select_option(option)

    coordinator.async_set_override.assert_awaited_once_with("bureau", expected)


async def test_unknown_option_falls_back_to_planning(entity, coordinator):
    """An unexpected label is treated as Planning rather than crashing."""
    coordinator.async_reset_override = AsyncMock()

    await entity.async_select_option("Vacances")

    coordinator.async_reset_override.assert_awaited_once_with("bureau")


async def test_setup_entry_creates_one_select_per_room(hass_with_coordinator):
    """Every room gets a select."""
    hass, entry, _ = hass_with_coordinator
    added = []

    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))

    assert {entity._piece_id for entity in added} == {"bureau", "salon"}
