"""Tests for the climate entity."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.climate import HVACAction, HVACMode

from custom_components.chauffage_intelligent.climate import (
    ChauffageIntelligentClimate,
    async_setup_entry,
)
from custom_components.chauffage_intelligent.const import (
    DOMAIN,
    SOURCE_DEFAUT,
    SOURCE_MANUEL,
    SOURCE_PLANNING,
)

MONDAY_8H = datetime(2026, 9, 7, 8, 0)


@pytest.fixture
def entity(coordinator):
    """A climate entity for the office."""
    return ChauffageIntelligentClimate(coordinator, "bureau", coordinator.pieces["bureau"])


def set_data(coordinator, **overrides):
    """Publish coordinator data for the office."""
    payload = {
        "consigne": 19.0,
        "source": SOURCE_PLANNING,
        "temperature": 18.0,
        "creneau_actuel": "07:00-09:00",
        "prochain_changement": MONDAY_8H.replace(hour=9).isoformat(),
        "offset": 0.0,
        "off": False,
    }
    payload.update(overrides)
    coordinator.data = {"pieces": {"bureau": payload}}


def test_unique_id_and_device(entity):
    """The entity is identified per room and grouped under a device."""
    assert entity.unique_id == f"{DOMAIN}_bureau"
    assert (DOMAIN, "bureau") in entity.device_info["identifiers"]


def test_reports_temperatures(entity, coordinator):
    """Current and target temperatures come from the coordinator."""
    set_data(coordinator)

    assert entity.current_temperature == 18.0
    assert entity.target_temperature == 19.0


def test_handles_missing_coordinator_data(entity, coordinator):
    """Before the first refresh the entity reports nothing rather than crashing."""
    coordinator.data = None

    assert entity.current_temperature is None
    assert entity.target_temperature is None
    assert entity.hvac_mode == HVACMode.HEAT


def test_hvac_mode_follows_the_off_flag(entity, coordinator):
    """A room switched off reports OFF."""
    set_data(coordinator, off=True)
    assert entity.hvac_mode == HVACMode.OFF

    set_data(coordinator, off=False)
    assert entity.hvac_mode == HVACMode.HEAT


@pytest.mark.parametrize(
    ("temperature", "consigne", "expected"),
    [
        (18.0, 19.0, HVACAction.HEATING),
        (19.0, 19.0, HVACAction.IDLE),
        (21.0, 19.0, HVACAction.IDLE),
    ],
)
def test_hvac_action(entity, coordinator, temperature, consigne, expected):
    """The action reflects whether the room still calls for heat."""
    set_data(coordinator, temperature=temperature, consigne=consigne)
    assert entity.hvac_action == expected


def test_hvac_action_when_off(entity, coordinator):
    """A room switched off reports the OFF action."""
    set_data(coordinator, off=True)
    assert entity.hvac_action == HVACAction.OFF


def test_hvac_action_without_a_reading(entity, coordinator):
    """Without a temperature the action is unknown."""
    set_data(coordinator, temperature=None)
    assert entity.hvac_action is None


def test_preset_is_planning_while_the_schedule_drives(entity, coordinator):
    """No override means the Planning preset."""
    set_data(coordinator, source=SOURCE_PLANNING)
    assert entity.preset_mode == "Planning"

    set_data(coordinator, source=SOURCE_DEFAUT)
    assert entity.preset_mode == "Planning"


def test_preset_matches_the_palette_when_overridden(entity, coordinator):
    """An override landing on a palette value shows that preset."""
    set_data(coordinator, source=SOURCE_MANUEL, consigne=19.0)
    assert entity.preset_mode == "Confort"

    set_data(coordinator, source=SOURCE_MANUEL, consigne=17.0)
    assert entity.preset_mode == "Éco"

    set_data(coordinator, source=SOURCE_MANUEL, consigne=7.0)
    assert entity.preset_mode == "Hors-gel"


def test_preset_for_a_free_temperature(entity, coordinator):
    """A forced temperature outside the palette shows no palette preset."""
    set_data(coordinator, source=SOURCE_MANUEL, consigne=21.5)
    assert entity.preset_mode == "Planning"


def test_attributes_expose_the_decision(entity, coordinator):
    """The attributes explain where the setpoint came from."""
    set_data(coordinator)
    attrs = entity.extra_state_attributes

    assert attrs["source_consigne"] == SOURCE_PLANNING
    assert attrs["creneau_actuel"] == "07:00-09:00"
    assert attrs["prochain_changement"] == MONDAY_8H.replace(hour=9).isoformat()
    assert attrs["radiateur_entities"] == ["climate.bilbao_bureau"]
    assert attrs["sonde_entity"] == "sensor.temperature_bureau"
    assert attrs["type_piece"] == "bureau"


async def test_set_temperature_forces_an_override(entity, coordinator):
    """Dragging the setpoint creates a manual override."""
    coordinator.async_set_override = AsyncMock()

    await entity.async_set_temperature(temperature=21.5)

    coordinator.async_set_override.assert_awaited_once_with("bureau", 21.5)


async def test_set_temperature_without_a_value_does_nothing(entity, coordinator):
    """A call with no temperature is ignored."""
    coordinator.async_set_override = AsyncMock()

    await entity.async_set_temperature()

    coordinator.async_set_override.assert_not_awaited()


async def test_hvac_mode_off_switches_the_room_off(entity, coordinator):
    """Setting OFF puts the room on frost protection."""
    coordinator.async_set_off = AsyncMock()

    await entity.async_set_hvac_mode(HVACMode.OFF)

    coordinator.async_set_off.assert_awaited_once_with("bureau", True)


async def test_hvac_mode_heat_returns_to_the_schedule(entity, coordinator):
    """Setting HEAT switches the room back on."""
    coordinator.async_set_off = AsyncMock()

    await entity.async_set_hvac_mode(HVACMode.HEAT)

    coordinator.async_set_off.assert_awaited_once_with("bureau", False)


async def test_turn_on_and_off(entity, coordinator):
    """The turn_on/turn_off shortcuts map to the off flag."""
    coordinator.async_set_off = AsyncMock()

    await entity.async_turn_off()
    await entity.async_turn_on()

    assert [call.args for call in coordinator.async_set_off.await_args_list] == [
        ("bureau", True),
        ("bureau", False),
    ]


async def test_preset_planning_clears_the_override(entity, coordinator):
    """Picking Planning hands control back to the schedule."""
    coordinator.async_reset_override = AsyncMock()

    await entity.async_set_preset_mode("Planning")

    coordinator.async_reset_override.assert_awaited_once_with("bureau")


@pytest.mark.parametrize(
    ("preset", "expected"), [("Confort", 19.0), ("Éco", 17.0), ("Hors-gel", 7.0)]
)
async def test_preset_applies_the_palette_value(entity, coordinator, preset, expected):
    """A palette preset forces that room's temperature."""
    coordinator.async_set_override = AsyncMock()

    await entity.async_set_preset_mode(preset)

    coordinator.async_set_override.assert_awaited_once_with("bureau", expected)


async def test_setup_entry_creates_one_entity_per_room(hass_with_coordinator):
    """Every configured room gets a climate entity."""
    hass, entry, coordinator = hass_with_coordinator
    added = []

    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))

    assert {entity._piece_id for entity in added} == {"bureau", "salon"}


def test_temperature_bounds_cover_the_palette(entity):
    """The slider spans at least the room's palette."""
    assert entity.min_temp <= 7.0
    assert entity.max_temp >= 22.0
