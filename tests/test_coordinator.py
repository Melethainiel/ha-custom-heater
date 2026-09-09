"""Tests for setpoint resolution and the coordinator update loop."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from custom_components.chauffage_intelligent.const import (
    SOURCE_DEFAUT,
    SOURCE_MANUEL,
    SOURCE_OFF,
    SOURCE_PLANNING,
)

from .conftest import FakeState

MONDAY_8H = datetime(2026, 9, 7, 8, 0)  # inside the office comfort slot
MONDAY_12H = datetime(2026, 9, 7, 12, 0)  # outside every slot

BUREAU = "climate.bilbao_bureau"
SALON = "climate.bilbao_salon"


def at(coordinator, when):
    """Patch dt_util.now() for the coordinator module."""
    return patch(
        "custom_components.chauffage_intelligent.coordinator.dt_util.now",
        return_value=when,
    )


def resolve(coordinator, piece_id, when):
    """Resolve a room's setpoint at a given time."""
    return coordinator._resolve_setpoint(
        piece_id, coordinator.pieces[piece_id], coordinator.store.get(piece_id), when
    )


# --------------------------------------------------------------- resolution


def test_scheduled_slot_wins(coordinator):
    """Inside a slot, the schedule sets the temperature."""
    assert resolve(coordinator, "bureau", MONDAY_8H) == (19.0, SOURCE_PLANNING)


def test_falls_back_to_eco_outside_any_slot(coordinator):
    """Outside every slot the room drops to its eco temperature."""
    assert resolve(coordinator, "bureau", MONDAY_12H) == (17.0, SOURCE_DEFAUT)


def test_room_without_schedule_uses_eco(coordinator):
    """A room with an empty schedule sits at eco."""
    assert resolve(coordinator, "salon", MONDAY_8H) == (17.0, SOURCE_DEFAUT)


async def test_override_beats_the_schedule(coordinator):
    """A manual override takes precedence over the planning."""
    with at(coordinator, MONDAY_8H):
        await coordinator.async_set_override("bureau", 21.5)

    assert resolve(coordinator, "bureau", MONDAY_8H) == (21.5, SOURCE_MANUEL)


async def test_override_without_duration_expires_at_the_next_transition(coordinator):
    """The default override lasts until the schedule next changes."""
    with at(coordinator, MONDAY_8H):
        await coordinator.async_set_override("bureau", 21.5)

    _, expiry = coordinator.get_override("bureau")
    assert expiry == MONDAY_8H.replace(hour=9)

    # Once past that moment the schedule takes back control.
    assert resolve(coordinator, "bureau", MONDAY_8H.replace(hour=9, minute=1)) == (
        17.0,
        SOURCE_DEFAUT,
    )


async def test_override_with_duration_expires_after_it(coordinator):
    """An explicit duration wins over the next transition."""
    with at(coordinator, MONDAY_8H):
        await coordinator.async_set_override("bureau", 21.5, duree=30)

    _, expiry = coordinator.get_override("bureau")
    assert expiry == MONDAY_8H + timedelta(minutes=30)

    assert resolve(coordinator, "bureau", MONDAY_8H + timedelta(minutes=20))[1] == SOURCE_MANUEL
    assert resolve(coordinator, "bureau", MONDAY_8H + timedelta(minutes=40))[1] == SOURCE_PLANNING


async def test_expired_override_is_forgotten(coordinator):
    """An expired override is dropped from memory."""
    with at(coordinator, MONDAY_8H):
        await coordinator.async_set_override("bureau", 21.5, duree=30)

    resolve(coordinator, "bureau", MONDAY_8H + timedelta(hours=2))

    assert coordinator.get_override("bureau") is None


async def test_reset_returns_to_the_schedule(coordinator):
    """Resetting drops the override."""
    with at(coordinator, MONDAY_8H):
        await coordinator.async_set_override("bureau", 21.5)
        await coordinator.async_reset_override("bureau")

    assert resolve(coordinator, "bureau", MONDAY_8H) == (19.0, SOURCE_PLANNING)


async def test_reset_without_room_clears_every_override(coordinator):
    """Resetting with no room clears them all."""
    with at(coordinator, MONDAY_8H):
        await coordinator.async_set_override("bureau", 21.5)
        await coordinator.async_set_override("salon", 22.0)
        await coordinator.async_reset_override()

    assert coordinator.get_override("bureau") is None
    assert coordinator.get_override("salon") is None


async def test_off_beats_everything(coordinator):
    """A room switched off falls to frost protection, override or not."""
    with at(coordinator, MONDAY_8H):
        await coordinator.async_set_override("bureau", 21.5)
        await coordinator.async_set_off("bureau", True)

    assert resolve(coordinator, "bureau", MONDAY_8H) == (7.0, SOURCE_OFF)
    assert coordinator.is_off("bureau") is True


async def test_turning_a_room_back_on_restores_the_schedule(coordinator):
    """Switching a room on returns it to its planning."""
    with at(coordinator, MONDAY_8H):
        await coordinator.async_set_off("bureau", True)
        await coordinator.async_set_off("bureau", False)

    assert resolve(coordinator, "bureau", MONDAY_8H) == (19.0, SOURCE_PLANNING)


async def test_forcing_a_temperature_cancels_the_off_state(coordinator):
    """An override on an off room turns it back on."""
    with at(coordinator, MONDAY_8H):
        await coordinator.async_set_off("bureau", True)
        await coordinator.async_set_override("bureau", 21.0)

    assert coordinator.is_off("bureau") is False
    assert resolve(coordinator, "bureau", MONDAY_8H) == (21.0, SOURCE_MANUEL)


async def test_override_on_unknown_room_raises(coordinator):
    """Overriding a room that does not exist is an error."""
    with pytest.raises(ValueError):
        await coordinator.async_set_override("cave", 20.0)


# ------------------------------------------------------------ temperature read


def test_temperature_comes_from_the_room_sensor(coordinator, mock_hass, radiator_state):
    """The external sensor is preferred."""
    mock_hass.states.get.side_effect = {
        "sensor.temperature_bureau": FakeState("18.4"),
        BUREAU: radiator_state(current_temperature=21.0),
    }.get

    assert coordinator._get_temperature(coordinator.pieces["bureau"]) == 18.4


def test_temperature_falls_back_to_the_radiator(coordinator, mock_hass, radiator_state):
    """An unavailable sensor falls back to the radiator's own reading."""
    mock_hass.states.get.side_effect = {
        "sensor.temperature_bureau": FakeState("unavailable"),
        BUREAU: radiator_state(current_temperature=21.0),
    }.get

    assert coordinator._get_temperature(coordinator.pieces["bureau"]) == 21.0


def test_temperature_is_none_when_nothing_is_readable(coordinator, mock_hass):
    """With no usable source the temperature is unknown."""
    mock_hass.states.get.side_effect = lambda entity_id: None

    assert coordinator._get_temperature(coordinator.pieces["bureau"]) is None


def test_temperature_ignores_a_non_numeric_sensor(coordinator, mock_hass, radiator_state):
    """A sensor reporting garbage falls through to the radiator."""
    mock_hass.states.get.side_effect = {
        "sensor.temperature_bureau": FakeState("chaud"),
        BUREAU: radiator_state(current_temperature=21.0),
    }.get

    assert coordinator._get_temperature(coordinator.pieces["bureau"]) == 21.0


# ---------------------------------------------------------------- update loop


async def test_update_produces_a_room_payload(coordinator, mock_hass, radiator_state):
    """The update cycle exposes everything the entities need."""
    mock_hass.states.get.side_effect = {
        "sensor.temperature_bureau": FakeState("18.0"),
        "sensor.temperature_salon": FakeState("19.0"),
        BUREAU: radiator_state(temperature=17.0),
        SALON: radiator_state(temperature=17.0),
    }.get

    with at(coordinator, MONDAY_8H):
        data = await coordinator._async_update_data()

    bureau = data["pieces"]["bureau"]
    assert bureau["consigne"] == 19.0
    assert bureau["source"] == SOURCE_PLANNING
    assert bureau["temperature"] == 18.0
    assert bureau["creneau_actuel"] == "07:00-09:00"
    assert bureau["prochain_changement"] == MONDAY_8H.replace(hour=9).isoformat()
    assert bureau["off"] is False


async def test_update_applies_the_setpoint(coordinator, mock_hass, radiator_state):
    """Each cycle pushes the resolved setpoint out."""
    mock_hass.states.get.side_effect = {
        "sensor.temperature_bureau": FakeState("18.0"),
        BUREAU: radiator_state(temperature=17.0),
        SALON: radiator_state(temperature=17.0),
    }.get

    with at(coordinator, MONDAY_8H):
        await coordinator._async_update_data()

    sent = [
        call.args[2]
        for call in mock_hass.services.async_call.call_args_list
        if call.args[1] == "set_temperature"
    ]
    assert {"entity_id": BUREAU, "temperature": 19.0} in sent


async def test_update_arms_a_timer_on_the_next_transition(
    coordinator, mock_hass, radiator_state
):
    """The next slot boundary is scheduled so the change lands on the minute."""
    mock_hass.states.get.side_effect = lambda entity_id: radiator_state(temperature=17.0)

    with (
        at(coordinator, MONDAY_8H),
        patch(
            "custom_components.chauffage_intelligent.coordinator.async_track_point_in_time"
        ) as track,
    ):
        await coordinator._async_update_data()

    assert track.call_count == 1
    assert track.call_args.args[2] == MONDAY_8H.replace(hour=9)


async def test_update_without_any_transition_arms_no_timer(
    coordinator, mock_hass, radiator_state
):
    """An empty schedule leaves no timer behind."""
    coordinator.store._schedules = {"bureau": [], "salon": []}
    mock_hass.states.get.side_effect = lambda entity_id: radiator_state(temperature=17.0)

    with (
        at(coordinator, MONDAY_8H),
        patch(
            "custom_components.chauffage_intelligent.coordinator.async_track_point_in_time"
        ) as track,
    ):
        await coordinator._async_update_data()

    assert track.call_count == 0


# ------------------------------------------------------------------ schedules


async def test_set_schedule_normalizes_and_stores(coordinator):
    """Saving a schedule normalizes it and keeps it."""
    slots = await coordinator.async_set_schedule(
        "salon",
        [
            {"day": 0, "start": "07:00", "end": "09:00", "temperature": 20},
            {"day": 0, "start": "09:00", "end": "11:00", "temperature": 20},
        ],
    )

    assert slots == [{"day": 0, "start": "07:00", "end": "11:00", "temperature": 20.0}]
    assert coordinator.get_schedule("salon") == slots


async def test_set_schedule_on_unknown_room_raises(coordinator):
    """Writing a schedule for an unknown room is refused."""
    with pytest.raises(ValueError):
        await coordinator.async_set_schedule("cave", [])


def test_radiator_entities_are_deduplicated(coordinator):
    """The listener watches each radiator once."""
    assert coordinator.radiator_entities() == [BUREAU, SALON]


# ------------------------------------------------------------------ listeners


def state_change(entity_id, old, new):
    """Build a fake state-changed event."""
    event = MagicMock()
    event.data = {"entity_id": entity_id, "old_state": old, "new_state": new}
    return event


def test_state_listener_reacts_to_a_setpoint_drift(coordinator, mock_hass, radiator_state):
    """Someone turning the radiator's dial triggers a re-apply."""
    coordinator._handle_radiator_state_change(
        state_change(BUREAU, radiator_state(temperature=19.0), radiator_state(temperature=22.0))
    )

    mock_hass.async_create_task.assert_called_once()


def test_state_listener_reacts_to_the_radiator_being_turned_off(
    coordinator, mock_hass, radiator_state
):
    """A radiator switched off must be caught and turned back on."""
    coordinator._handle_radiator_state_change(
        state_change(
            BUREAU,
            radiator_state(temperature=19.0),
            radiator_state(temperature=19.0, state="off"),
        )
    )

    mock_hass.async_create_task.assert_called_once()


def test_state_listener_reacts_when_a_radiator_comes_back(
    coordinator, mock_hass, radiator_state
):
    """A radiator returning from unavailable gets its setpoint again."""
    coordinator._handle_radiator_state_change(
        state_change(BUREAU, FakeState("unavailable"), radiator_state(temperature=17.0))
    )

    mock_hass.async_create_task.assert_called_once()


def test_state_listener_ignores_irrelevant_changes(coordinator, mock_hass, radiator_state):
    """A plain temperature report does not trigger a refresh."""
    coordinator._handle_radiator_state_change(
        state_change(
            BUREAU,
            radiator_state(temperature=19.0, current_temperature=18.0),
            radiator_state(temperature=19.0, current_temperature=18.5),
        )
    )

    mock_hass.async_create_task.assert_not_called()


def test_state_listener_ignores_a_removed_entity(coordinator, mock_hass, radiator_state):
    """A vanished entity is ignored."""
    coordinator._handle_radiator_state_change(
        state_change(BUREAU, radiator_state(temperature=19.0), None)
    )

    mock_hass.async_create_task.assert_not_called()


def test_start_listeners_watches_every_radiator(coordinator, mock_hass):
    """The listener covers all configured radiators."""
    with patch(
        "custom_components.chauffage_intelligent.coordinator.async_track_state_change_event"
    ) as track:
        coordinator.async_start_listeners()

    assert track.call_args.args[1] == [BUREAU, SALON]


def test_start_listeners_without_radiators(mock_hass, store):
    """A config with no radiator registers nothing."""
    from custom_components.chauffage_intelligent.coordinator import (
        ChauffageIntelligentCoordinator,
    )

    empty = ChauffageIntelligentCoordinator(
        mock_hass, {"pieces": {}}, store, update_interval=timedelta(seconds=300)
    )

    with patch(
        "custom_components.chauffage_intelligent.coordinator.async_track_state_change_event"
    ) as track:
        empty.async_start_listeners()

    track.assert_not_called()


async def test_shutdown_cancels_both_listeners(coordinator, mock_hass, radiator_state):
    """Unloading the entry cancels the timer and the state listener."""
    unsub_state = MagicMock()
    unsub_timer = MagicMock()
    mock_hass.states.get.side_effect = lambda entity_id: radiator_state(temperature=17.0)

    with patch(
        "custom_components.chauffage_intelligent.coordinator.async_track_state_change_event",
        return_value=unsub_state,
    ):
        coordinator.async_start_listeners()

    with (
        at(coordinator, MONDAY_8H),
        patch(
            "custom_components.chauffage_intelligent.coordinator.async_track_point_in_time",
            return_value=unsub_timer,
        ),
    ):
        await coordinator._async_update_data()

    coordinator.async_shutdown_listeners()

    unsub_state.assert_called_once()
    unsub_timer.assert_called_once()


async def test_a_new_transition_replaces_the_previous_timer(
    coordinator, mock_hass, radiator_state
):
    """Each cycle re-arms the timer instead of stacking them."""
    unsub = MagicMock()
    mock_hass.states.get.side_effect = lambda entity_id: radiator_state(temperature=17.0)

    with (
        at(coordinator, MONDAY_8H),
        patch(
            "custom_components.chauffage_intelligent.coordinator.async_track_point_in_time",
            return_value=unsub,
        ),
    ):
        await coordinator._async_update_data()
        await coordinator._async_update_data()

    unsub.assert_called_once()


def test_transition_callback_requests_a_refresh(coordinator, mock_hass):
    """Firing the timer recomputes the setpoints."""
    coordinator._handle_transition(MONDAY_8H)

    mock_hass.async_create_task.assert_called_once()
    assert coordinator._unsub_transition is None


async def test_update_wraps_failures(coordinator, mock_hass):
    """An unexpected error surfaces as UpdateFailed."""
    from homeassistant.helpers.update_coordinator import UpdateFailed

    mock_hass.states.get.side_effect = RuntimeError("boom")

    with at(coordinator, MONDAY_8H), pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
