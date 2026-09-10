"""Tests for the websocket commands backing the panel."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import voluptuous as vol

from custom_components.chauffage_intelligent import websocket_api as ws
from custom_components.chauffage_intelligent.const import DOMAIN, SOURCE_PLANNING


@pytest.fixture
def hass(mock_hass, coordinator):
    """A hass whose domain data holds one coordinator."""
    coordinator.data = {
        "pieces": {
            "bureau": {
                "consigne": 19.0,
                "source": SOURCE_PLANNING,
                "temperature": 18.0,
                "creneau_actuel": "07:00-09:00",
                "prochain_changement": "2026-09-07T09:00:00",
                "off": False,
            },
            "salon": {},
        }
    }
    mock_hass.data = {DOMAIN: {"entry": coordinator}}
    return mock_hass


@pytest.fixture
def connection():
    """A websocket connection recording results and errors."""
    conn = MagicMock()
    conn.results = {}
    conn.errors = []
    conn.send_result.side_effect = lambda msg_id, result=None: conn.results.update(
        {msg_id: result}
    )
    conn.send_error.side_effect = lambda msg_id, code, message: conn.errors.append(
        (code, message)
    )
    return conn


def validate(handler, msg):
    """Run a message through the command's own voluptuous schema."""
    return handler._ws_schema(msg)


def call(handler, *args):
    """Invoke a command, unwrapping the @async_response task scheduler."""
    return getattr(handler, "__wrapped__", handler)(*args)


# ------------------------------------------------------------------- rooms


def test_rooms_lists_every_configured_room(hass, connection):
    """The panel gets both rooms with their palette and live state."""
    ws.ws_rooms(hass, connection, {"id": 1, "type": ws.TYPE_ROOMS})

    result = connection.results[1]
    assert [room["id"] for room in result["rooms"]] == ["bureau", "salon"]
    assert result["days"] == 7
    assert result["slots_per_day"] == 48
    assert result["step_minutes"] == 30

    bureau = result["rooms"][0]
    assert bureau["name"] == "Bureau"
    assert bureau["temperature"] == 18.0
    assert bureau["consigne"] == 19.0
    assert bureau["source"] == SOURCE_PLANNING
    assert bureau["temperatures"]["confort"] == 19


def test_rooms_without_coordinator_data(mock_hass, coordinator, connection):
    """Before the first refresh the rooms are still listed."""
    coordinator.data = None
    mock_hass.data = {DOMAIN: {"entry": coordinator}}

    ws.ws_rooms(mock_hass, connection, {"id": 1, "type": ws.TYPE_ROOMS})

    assert len(connection.results[1]["rooms"]) == 2
    assert connection.results[1]["rooms"][0]["consigne"] is None


# ---------------------------------------------------------------- schedule


def test_schedule_get_returns_slots_and_grid(hass, connection):
    """The panel receives both representations."""
    ws.ws_schedule_get(hass, connection, {"id": 2, "piece_id": "bureau"})

    result = connection.results[2]
    assert result["slots"][0]["start"] == "07:00"
    assert len(result["grid"]) == 7
    assert result["grid"][0][14] == 19.0


def test_schedule_get_on_unknown_room(hass, connection):
    """An unknown room is an explicit error."""
    ws.ws_schedule_get(hass, connection, {"id": 2, "piece_id": "cave"})

    assert connection.errors == [("not_found", "Unknown room: cave")]


async def test_schedule_set_stores_the_grid(hass, connection):
    """Painting the grid persists the compressed slots."""
    grid = [[None] * 48 for _ in range(7)]
    grid[2][20] = 21.0
    grid[2][21] = 21.0

    await call(ws.ws_schedule_set, hass, connection, {"id": 3, "piece_id": "salon", "grid": grid})

    result = connection.results[3]
    assert result["slots"] == [
        {"day": 2, "start": "10:00", "end": "11:00", "temperature": 21.0}
    ]
    assert result["grid"][2][20] == 21.0


async def test_schedule_set_replaces_the_previous_schedule(hass, connection):
    """Saving an empty grid clears the room's planning."""
    grid = [[None] * 48 for _ in range(7)]

    await call(ws.ws_schedule_set, hass, connection, {"id": 3, "piece_id": "bureau", "grid": grid})

    assert connection.results[3]["slots"] == []


async def test_schedule_set_on_unknown_room(hass, connection):
    """An unknown room is refused before any write."""
    grid = [[None] * 48 for _ in range(7)]

    await call(ws.ws_schedule_set, hass, connection, {"id": 3, "piece_id": "cave", "grid": grid})

    assert connection.errors == [("not_found", "Unknown room: cave")]


@pytest.mark.parametrize(
    "grid",
    [
        [[None] * 48 for _ in range(6)],  # too few days
        [[None] * 47 for _ in range(7)],  # too few cells
        [[None] * 48 for _ in range(8)],  # too many days
    ],
)
def test_schedule_set_schema_rejects_a_malformed_grid(grid):
    """A grid with the wrong shape never reaches the store."""
    with pytest.raises(vol.Invalid):
        validate(ws.ws_schedule_set, {"id": 3, "type": ws.TYPE_SCHEDULE_SET,
                                      "piece_id": "bureau", "grid": grid})


def test_schedule_set_schema_accepts_a_valid_grid():
    """A well-formed grid passes validation."""
    grid = [[None] * 48 for _ in range(7)]
    grid[0][0] = 20
    validated = validate(
        ws.ws_schedule_set,
        {"id": 3, "type": ws.TYPE_SCHEDULE_SET, "piece_id": "bureau", "grid": grid},
    )
    assert validated["grid"][0][0] == 20.0


# -------------------------------------------------------------------- copy


async def test_schedule_copy(hass, connection):
    """One room's planning can be pushed onto another."""
    await call(
        ws.ws_schedule_copy,
        hass, connection, {"id": 4, "from_piece": "bureau", "to_pieces": ["salon"]}
    )

    assert connection.results[4] == {"copied_to": ["salon"]}
    assert hass.data[DOMAIN]["entry"].get_schedule("salon") == hass.data[DOMAIN][
        "entry"
    ].get_schedule("bureau")


async def test_schedule_copy_from_unknown_room(hass, connection):
    """Copying from a room that does not exist errors out."""
    await call(
        ws.ws_schedule_copy,
        hass, connection, {"id": 4, "from_piece": "cave", "to_pieces": ["salon"]}
    )

    assert connection.errors == [("not_found", "Unknown room: cave")]


async def test_schedule_copy_to_unknown_room(hass, connection):
    """Copying onto a room that does not exist errors out."""
    await call(
        ws.ws_schedule_copy,
        hass, connection, {"id": 4, "from_piece": "bureau", "to_pieces": ["cave"]}
    )

    assert connection.errors == [("not_found", "Unknown room: cave")]


# ---------------------------------------------------------------- override


async def test_override_set(hass, connection):
    """The panel can force a temperature."""
    await call(
        ws.ws_override_set,
        hass, connection, {"id": 5, "piece_id": "bureau", "temperature": 21.0}
    )

    assert connection.results[5] == {}
    assert hass.data[DOMAIN]["entry"].get_override("bureau")[0] == 21.0


async def test_override_cleared_with_a_null_temperature(hass, connection):
    """Sending no temperature clears the override."""
    coordinator = hass.data[DOMAIN]["entry"]
    await call(
        ws.ws_override_set,
        hass, connection, {"id": 5, "piece_id": "bureau", "temperature": 21.0}
    )

    await call(
        ws.ws_override_set,
        hass, connection, {"id": 6, "piece_id": "bureau", "temperature": None}
    )

    assert coordinator.get_override("bureau") is None


async def test_override_on_unknown_room(hass, connection):
    """An unknown room is refused."""
    await call(
        ws.ws_override_set,
        hass, connection, {"id": 5, "piece_id": "cave", "temperature": 21.0}
    )

    assert connection.errors == [("not_found", "Unknown room: cave")]


# ------------------------------------------------------------- registration


def test_registration_is_idempotent(mock_hass):
    """Registering twice does not register the commands twice."""
    mock_hass.data = {}

    with pytest.MonkeyPatch.context() as monkeypatch:
        registered = []
        monkeypatch.setattr(
            ws.websocket_api,
            "async_register_command",
            lambda hass, handler: registered.append(handler),
        )
        ws.async_register_websocket_api(mock_hass)
        ws.async_register_websocket_api(mock_hass)

    assert len(registered) == 5


async def test_schedule_set_reports_a_conversion_error(hass, connection):
    """A schedule the store refuses comes back as an error, not a crash."""
    from custom_components.chauffage_intelligent.schedule import ScheduleError

    grid = [[None] * 48 for _ in range(7)]

    with patch.object(ws, "grid_to_slots", side_effect=ScheduleError("bad grid")):
        await call(ws.ws_schedule_set, hass, connection, {"id": 7, "piece_id": "bureau",
                                                          "grid": grid})

    assert connection.errors == [("invalid_schedule", "bad grid")]
