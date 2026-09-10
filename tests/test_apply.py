"""Tests for how the coordinator pushes setpoints to radiators.

This is the behaviour that replaces the old fire-and-forget
``climate.set_temperature`` call issued on every cycle.
"""

from __future__ import annotations

import pytest

from custom_components.chauffage_intelligent.const import CONF_PIECE_OFFSET, CONF_PIECES

from .conftest import FakeState

BUREAU = "climate.bilbao_bureau"


def piece(coordinator, piece_id="bureau"):
    """Return a room config from the coordinator."""
    return coordinator.pieces[piece_id]


def calls(mock_hass, service=None):
    """Return the climate service calls made so far."""
    result = [call.args for call in mock_hass.services.async_call.call_args_list]
    if service:
        result = [args for args in result if args[1] == service]
    return result


def set_states(mock_hass, states):
    """Wire hass.states.get to a dict of entity_id -> state."""
    mock_hass.states.get.side_effect = lambda entity_id: states.get(entity_id)


async def test_writes_setpoint_when_it_differs(coordinator, mock_hass, radiator_state):
    """A radiator sitting at the wrong setpoint gets a new one."""
    set_states(mock_hass, {BUREAU: radiator_state(temperature=17.0)})

    await coordinator._apply_setpoint("bureau", piece(coordinator), 20.0)

    assert calls(mock_hass, "set_temperature") == [
        ("climate", "set_temperature", {"entity_id": BUREAU, "temperature": 20.0})
    ]


async def test_skips_write_when_already_at_target(coordinator, mock_hass, radiator_state):
    """No Zigbee traffic when the radiator already holds the setpoint."""
    set_states(mock_hass, {BUREAU: radiator_state(temperature=20.0)})

    await coordinator._apply_setpoint("bureau", piece(coordinator), 20.0)

    assert calls(mock_hass) == []


async def test_skips_write_within_tolerance(coordinator, mock_hass, radiator_state):
    """A rounding-level difference is not worth a write."""
    set_states(mock_hass, {BUREAU: radiator_state(temperature=20.05)})

    await coordinator._apply_setpoint("bureau", piece(coordinator), 20.0)

    assert calls(mock_hass) == []


async def test_rewrites_on_the_next_cycle_when_the_setpoint_did_not_stick(
    coordinator, mock_hass, radiator_state
):
    """A setpoint the radiator ignored is retransmitted, with no retry logic."""
    set_states(mock_hass, {BUREAU: radiator_state(temperature=17.0)})

    await coordinator._apply_setpoint("bureau", piece(coordinator), 20.0)
    await coordinator._apply_setpoint("bureau", piece(coordinator), 20.0)

    assert len(calls(mock_hass, "set_temperature")) == 2


async def test_turns_the_radiator_back_on(coordinator, mock_hass, radiator_state):
    """A radiator left in 'off' ignores setpoints, so it is switched to heat."""
    set_states(mock_hass, {BUREAU: radiator_state(temperature=17.0, state="off")})

    await coordinator._apply_setpoint("bureau", piece(coordinator), 20.0)

    assert calls(mock_hass, "set_hvac_mode") == [
        ("climate", "set_hvac_mode", {"entity_id": BUREAU, "hvac_mode": "heat"})
    ]
    assert len(calls(mock_hass, "set_temperature")) == 1


async def test_does_not_touch_an_unavailable_radiator(coordinator, mock_hass):
    """An unreachable radiator is skipped rather than written to blindly."""
    set_states(mock_hass, {BUREAU: FakeState("unavailable")})

    await coordinator._apply_setpoint("bureau", piece(coordinator), 20.0)

    assert calls(mock_hass) == []


async def test_does_not_touch_a_missing_radiator(coordinator, mock_hass):
    """An entity that does not exist yet is skipped."""
    set_states(mock_hass, {})

    await coordinator._apply_setpoint("bureau", piece(coordinator), 20.0)

    assert calls(mock_hass) == []


async def test_clamps_below_the_radiator_minimum(coordinator, mock_hass, radiator_state):
    """A 7°C frost setpoint is raised to what the radiator accepts."""
    set_states(mock_hass, {BUREAU: radiator_state(temperature=17.0, min_temp=10.0)})

    await coordinator._apply_setpoint("bureau", piece(coordinator), 7.0)

    assert calls(mock_hass, "set_temperature") == [
        ("climate", "set_temperature", {"entity_id": BUREAU, "temperature": 10.0})
    ]


async def test_clamps_above_the_radiator_maximum(coordinator, mock_hass, radiator_state):
    """A setpoint beyond the radiator's range is capped."""
    set_states(mock_hass, {BUREAU: radiator_state(temperature=17.0, max_temp=24.0)})

    await coordinator._apply_setpoint("bureau", piece(coordinator), 28.0)

    assert calls(mock_hass, "set_temperature") == [
        ("climate", "set_temperature", {"entity_id": BUREAU, "temperature": 24.0})
    ]


async def test_applies_the_offset(coordinator, mock_hass, radiator_state):
    """The per-room offset is added to the setpoint that is sent."""
    coordinator.pieces["bureau"][CONF_PIECE_OFFSET] = 2.5
    set_states(mock_hass, {BUREAU: radiator_state(temperature=17.0)})

    await coordinator._apply_setpoint("bureau", piece(coordinator), 20.0)

    assert calls(mock_hass, "set_temperature") == [
        ("climate", "set_temperature", {"entity_id": BUREAU, "temperature": 22.5})
    ]


async def test_offset_is_accounted_for_when_deciding_to_write(
    coordinator, mock_hass, radiator_state
):
    """With an offset, a radiator already at target+offset is left alone."""
    coordinator.pieces["bureau"][CONF_PIECE_OFFSET] = 2.5
    set_states(mock_hass, {BUREAU: radiator_state(temperature=22.5)})

    await coordinator._apply_setpoint("bureau", piece(coordinator), 20.0)

    assert calls(mock_hass) == []


async def test_writes_when_the_radiator_reports_no_setpoint(
    coordinator, mock_hass, radiator_state
):
    """A radiator without a known setpoint is written to."""
    set_states(mock_hass, {BUREAU: radiator_state(temperature=None)})

    await coordinator._apply_setpoint("bureau", piece(coordinator), 20.0)

    assert len(calls(mock_hass, "set_temperature")) == 1


async def test_writes_to_every_radiator_of_the_room(
    mock_hass, basic_config, store, radiator_state
):
    """Rooms with several radiators get all of them set."""
    from datetime import timedelta

    from custom_components.chauffage_intelligent.coordinator import (
        ChauffageIntelligentCoordinator,
    )

    basic_config[CONF_PIECES]["bureau"]["radiateurs"] = [BUREAU, "climate.bilbao_bureau_2"]
    coordinator = ChauffageIntelligentCoordinator(
        mock_hass, basic_config, store, update_interval=timedelta(seconds=300)
    )
    set_states(
        mock_hass,
        {
            BUREAU: radiator_state(temperature=17.0),
            "climate.bilbao_bureau_2": radiator_state(temperature=17.0),
        },
    )

    await coordinator._apply_setpoint("bureau", piece(coordinator), 20.0)

    assert len(calls(mock_hass, "set_temperature")) == 2


async def test_a_failing_radiator_does_not_break_the_others(
    mock_hass, basic_config, store, radiator_state
):
    """One radiator raising must not stop the room's other radiators."""
    from datetime import timedelta

    from custom_components.chauffage_intelligent.coordinator import (
        ChauffageIntelligentCoordinator,
    )

    basic_config[CONF_PIECES]["bureau"]["radiateurs"] = [BUREAU, "climate.bilbao_bureau_2"]
    coordinator = ChauffageIntelligentCoordinator(
        mock_hass, basic_config, store, update_interval=timedelta(seconds=300)
    )
    set_states(
        mock_hass,
        {
            BUREAU: radiator_state(temperature=17.0),
            "climate.bilbao_bureau_2": radiator_state(temperature=17.0),
        },
    )
    mock_hass.services.async_call.side_effect = [OSError("zigbee down"), None]

    await coordinator._apply_setpoint("bureau", piece(coordinator), 20.0)

    assert len(calls(mock_hass, "set_temperature")) == 2


@pytest.mark.parametrize("bad_value", ["unknown", None])
async def test_survives_a_radiator_with_a_bogus_setpoint(
    coordinator, mock_hass, bad_value
):
    """A non-numeric setpoint attribute triggers a write instead of crashing."""
    set_states(
        mock_hass,
        {BUREAU: FakeState("heat", {"temperature": bad_value, "min_temp": 7, "max_temp": 30})},
    )

    await coordinator._apply_setpoint("bureau", piece(coordinator), 20.0)

    assert len(calls(mock_hass, "set_temperature")) == 1
