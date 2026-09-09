"""Tests for the config and options flows."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.chauffage_intelligent.config_flow import (
    CONFIG_VERSION,
    ChauffageIntelligentConfigFlow,
    ChauffageIntelligentOptionsFlow,
    _all_temperature_sensors,
    _areas_with_climate,
    _entities_in_area,
    _room_from_input,
)
from custom_components.chauffage_intelligent.const import (
    CONF_PIECE_AREA_ID,
    CONF_PIECE_NAME,
    CONF_PIECE_OFFSET,
    CONF_PIECE_RADIATEURS,
    CONF_PIECE_SONDE,
    CONF_PIECE_TEMPERATURES,
    CONF_PIECE_TYPE,
    CONF_PIECES,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
    TEMP_CONFORT,
    TEMP_ECO,
    TEMP_HORS_GEL,
)


def make_state(entity_id, device_class=None):
    """Build a fake state with an entity id."""
    state = MagicMock()
    state.entity_id = entity_id
    state.attributes = {"device_class": device_class} if device_class else {}
    return state


def make_registry_entry(entity_id, domain, area_id=None, device_id=None):
    """Build a fake entity registry entry."""
    entry = MagicMock()
    entry.entity_id = entity_id
    entry.domain = domain
    entry.area_id = area_id
    entry.device_id = device_id
    return entry


@pytest.fixture
def flow_hass():
    """A hass exposing one area with a radiator and a temperature sensor."""
    hass = MagicMock()

    states = {
        "climate": [make_state("climate.bilbao_bureau")],
        "sensor": [make_state("sensor.temperature_bureau", "temperature")],
    }
    hass.states.async_all = lambda domain: states.get(domain, [])
    hass.states.get = lambda entity_id: next(
        (state for group in states.values() for state in group if state.entity_id == entity_id),
        None,
    )
    hass.data = {DOMAIN: {}}
    return hass


@pytest.fixture
def registries(flow_hass):
    """Patch the area/entity/device registries used by the flow."""
    area = MagicMock()
    area.id = "bureau"
    area.name = "Bureau"

    area_reg = MagicMock()
    area_reg.async_get_area = lambda area_id: area if area_id == "bureau" else None

    entity_reg = MagicMock()
    entity_reg.entities.values.return_value = [
        make_registry_entry("climate.bilbao_bureau", "climate", area_id="bureau"),
        make_registry_entry("sensor.temperature_bureau", "sensor", area_id="bureau"),
    ]

    device_reg = MagicMock()
    device_reg.async_get.return_value = None

    module = "custom_components.chauffage_intelligent.config_flow"
    with (
        patch(f"{module}.ar.async_get", return_value=area_reg),
        patch(f"{module}.er.async_get", return_value=entity_reg),
        patch(f"{module}.dr.async_get", return_value=device_reg),
    ):
        yield area_reg, entity_reg, device_reg


ROOM_INPUT = {
    CONF_PIECE_TYPE: "bureau",
    CONF_PIECE_RADIATEURS: ["climate.bilbao_bureau"],
    CONF_PIECE_SONDE: "sensor.temperature_bureau",
    "temp_confort": 19.5,
    "temp_eco": 17.0,
    "temp_hors_gel": 7.0,
    CONF_PIECE_OFFSET: 1.5,
}


# ------------------------------------------------------------------- helpers


def test_areas_with_climate(flow_hass, registries):
    """Areas holding a climate entity are listed."""
    assert _areas_with_climate(flow_hass) == [{"value": "bureau", "label": "Bureau"}]


def test_areas_with_climate_via_device(flow_hass, registries):
    """A climate entity inheriting its area from its device counts too."""
    _, entity_reg, device_reg = registries
    device = MagicMock()
    device.area_id = "bureau"
    device_reg.async_get.return_value = device
    entity_reg.entities.values.return_value = [
        make_registry_entry("climate.other", "climate", device_id="dev1"),
    ]

    assert _areas_with_climate(flow_hass) == [{"value": "bureau", "label": "Bureau"}]


def test_entities_in_area(flow_hass, registries):
    """Climate and temperature sensors are found per area."""
    assert _entities_in_area(flow_hass, "bureau", "climate") == ["climate.bilbao_bureau"]
    assert _entities_in_area(flow_hass, "bureau", "sensor") == ["sensor.temperature_bureau"]
    assert _entities_in_area(flow_hass, "salon", "climate") == []


def test_entities_in_area_skips_non_temperature_sensors(flow_hass, registries):
    """A humidity sensor in the area is not offered as a probe."""
    _, entity_reg, _ = registries
    entity_reg.entities.values.return_value = [
        make_registry_entry("sensor.humidity_bureau", "sensor", area_id="bureau"),
    ]

    assert _entities_in_area(flow_hass, "bureau", "sensor") == []


def test_all_temperature_sensors(flow_hass):
    """The fallback lists every temperature sensor."""
    assert _all_temperature_sensors(flow_hass) == ["sensor.temperature_bureau"]


def test_room_from_input():
    """The room form maps onto the stored room config."""
    room = _room_from_input(ROOM_INPUT, "Bureau", "bureau")

    assert room[CONF_PIECE_NAME] == "Bureau"
    assert room[CONF_PIECE_AREA_ID] == "bureau"
    assert room[CONF_PIECE_RADIATEURS] == ["climate.bilbao_bureau"]
    assert room[CONF_PIECE_TEMPERATURES] == {
        TEMP_CONFORT: 19.5,
        TEMP_ECO: 17.0,
        TEMP_HORS_GEL: 7.0,
    }
    assert room[CONF_PIECE_OFFSET] == 1.5


def test_room_from_input_uses_type_defaults():
    """Omitted temperatures fall back to the room type's defaults."""
    room = _room_from_input(
        {CONF_PIECE_TYPE: "salle_de_bain", CONF_PIECE_RADIATEURS: ["climate.x"]},
        "Salle de bain",
        "sdb",
    )

    assert room[CONF_PIECE_TEMPERATURES][TEMP_CONFORT] == 22
    assert room[CONF_PIECE_OFFSET] == 0.0
    assert room[CONF_PIECE_SONDE] is None


def test_room_from_input_accepts_a_single_radiator():
    """A lone entity id is coerced into a list."""
    room = _room_from_input(
        {CONF_PIECE_TYPE: "bureau", CONF_PIECE_RADIATEURS: "climate.x"}, "Bureau", "bureau"
    )

    assert room[CONF_PIECE_RADIATEURS] == ["climate.x"]


# --------------------------------------------------------------- config flow


def test_flow_version():
    """The flow creates version 2 entries."""
    assert ChauffageIntelligentConfigFlow.VERSION == CONFIG_VERSION == 2


async def test_user_step_shows_only_the_interval(flow_hass):
    """Calendar and presence are gone from the first step."""
    flow = ChauffageIntelligentConfigFlow()
    flow.hass = flow_hass

    result = await flow.async_step_user(None)

    assert result["step_id"] == "user"
    keys = {str(key) for key in result["data_schema"].schema}
    assert keys == {CONF_UPDATE_INTERVAL}


async def test_user_step_stores_the_interval_in_seconds(flow_hass):
    """Minutes entered in the form are stored as seconds."""
    flow = ChauffageIntelligentConfigFlow()
    flow.hass = flow_hass

    result = await flow.async_step_user({CONF_UPDATE_INTERVAL: 10})

    assert flow._data[CONF_UPDATE_INTERVAL] == 600
    assert result["step_id"] == "room_menu"


async def test_room_menu_requires_a_room_before_finishing(flow_hass):
    """Finishing with no room is refused."""
    flow = ChauffageIntelligentConfigFlow()
    flow.hass = flow_hass
    flow._data = {CONF_PIECES: {}}

    result = await flow.async_step_room_menu({"action": "finish"})

    assert result["errors"]["base"] == "no_rooms"


async def test_full_config_flow(flow_hass, registries):
    """A room can be added and the entry created."""
    flow = ChauffageIntelligentConfigFlow()
    flow.hass = flow_hass
    flow.async_create_entry = MagicMock(
        side_effect=lambda **kwargs: {"type": "create_entry", **kwargs}
    )

    await flow.async_step_user({CONF_UPDATE_INTERVAL: 5})
    await flow.async_step_room_menu({"action": "add_room"})
    await flow.async_step_select_area({"area": "bureau"})
    await flow.async_step_configure_room(ROOM_INPUT)
    result = await flow.async_step_room_menu({"action": "finish"})

    room = result["data"][CONF_PIECES]["bureau"]
    assert room[CONF_PIECE_NAME] == "Bureau"
    assert room[CONF_PIECE_OFFSET] == 1.5


async def test_configure_room_form_offers_the_offset(flow_hass, registries):
    """The room form exposes the setpoint offset."""
    flow = ChauffageIntelligentConfigFlow()
    flow.hass = flow_hass
    flow._data = {CONF_PIECES: {}}
    flow._current_area_id = "bureau"
    flow._current_area_name = "Bureau"

    result = await flow.async_step_configure_room(None)

    keys = {str(key) for key in result["data_schema"].schema}
    assert CONF_PIECE_OFFSET in keys
    assert {"temp_confort", "temp_eco", "temp_hors_gel"} <= keys


async def test_select_area_rejects_a_configured_area(flow_hass, registries):
    """An area already set up cannot be added twice."""
    flow = ChauffageIntelligentConfigFlow()
    flow.hass = flow_hass
    flow._data = {CONF_PIECES: {"bureau": {}}}

    result = await flow.async_step_select_area({"area": "bureau"})

    assert result["errors"]["base"] == "area_already_configured"


async def test_select_area_without_any_area(flow_hass, registries):
    """With every area configured, the step reports it."""
    _, entity_reg, _ = registries
    entity_reg.entities.values.return_value = []

    flow = ChauffageIntelligentConfigFlow()
    flow.hass = flow_hass
    flow._data = {CONF_PIECES: {}}

    result = await flow.async_step_select_area(None)

    assert result["errors"]["base"] == "no_areas_available"


# -------------------------------------------------------------- options flow


@pytest.fixture
def options_flow(flow_hass):
    """An options flow over an entry holding one room."""
    entry = MagicMock()
    entry.data = {
        CONF_UPDATE_INTERVAL: 300,
        CONF_PIECES: {
            "bureau": {
                CONF_PIECE_NAME: "Bureau",
                CONF_PIECE_AREA_ID: "bureau",
                CONF_PIECE_TYPE: "bureau",
                CONF_PIECE_RADIATEURS: ["climate.bilbao_bureau"],
                CONF_PIECE_SONDE: "sensor.temperature_bureau",
                CONF_PIECE_TEMPERATURES: {
                    TEMP_CONFORT: 19,
                    TEMP_ECO: 17,
                    TEMP_HORS_GEL: 7,
                },
                CONF_PIECE_OFFSET: 0.0,
            }
        },
    }

    flow = ChauffageIntelligentOptionsFlow(entry)
    flow.hass = flow_hass
    flow.async_create_entry = MagicMock(
        side_effect=lambda **kwargs: {"type": "create_entry", **kwargs}
    )
    flow.async_abort = MagicMock(side_effect=lambda **kwargs: {"type": "abort", **kwargs})
    return flow, entry


async def test_options_menu(options_flow):
    """The menu offers the four room actions."""
    flow, _ = options_flow

    result = await flow.async_step_init(None)

    assert result["step_id"] == "init"


async def test_options_modify_room_updates_the_entry(options_flow, registries):
    """Editing a room writes the new config back to the entry."""
    flow, entry = options_flow
    flow._selected_room = "bureau"

    await flow.async_step_modify_room({**ROOM_INPUT, CONF_PIECE_OFFSET: -0.5})

    data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert data[CONF_PIECES]["bureau"][CONF_PIECE_OFFSET] == -0.5
    assert data[CONF_PIECES]["bureau"][CONF_PIECE_NAME] == "Bureau"


async def test_options_modify_room_prefills_the_form(options_flow, registries):
    """The edit form starts from the room's current values."""
    flow, _ = options_flow
    flow._selected_room = "bureau"

    result = await flow.async_step_modify_room(None)

    defaults = {str(key): key.default() for key in result["data_schema"].schema}
    assert defaults["temp_confort"] == 19
    assert defaults[CONF_PIECE_OFFSET] == 0.0


async def test_options_delete_room_removes_its_schedule(options_flow, registries):
    """Deleting a room drops its planning from the store."""
    flow, _ = options_flow
    store = MagicMock()
    store.async_remove = AsyncMock()
    flow.hass.data = {DOMAIN: {"store": store}}

    await flow.async_step_delete_room({"room": "bureau", "confirm": True})

    store.async_remove.assert_awaited_once_with("bureau")
    data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert data[CONF_PIECES] == {}


async def test_options_delete_room_without_confirmation(options_flow, registries):
    """Without confirmation the room is kept."""
    flow, _ = options_flow

    result = await flow.async_step_delete_room({"room": "bureau", "confirm": False})

    assert result["step_id"] == "init"
    flow.hass.config_entries.async_update_entry.assert_not_called()


async def test_options_settings_only_holds_the_interval(options_flow):
    """The settings form lost the calendar, presence and preheat fields."""
    flow, _ = options_flow

    result = await flow.async_step_settings(None)

    keys = {str(key) for key in result["data_schema"].schema}
    assert keys == {CONF_UPDATE_INTERVAL}


async def test_options_settings_saves_seconds(options_flow):
    """The interval is converted back to seconds."""
    flow, _ = options_flow

    await flow.async_step_settings({CONF_UPDATE_INTERVAL: 2})

    data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert data[CONF_UPDATE_INTERVAL] == 120


async def test_options_add_room(options_flow, registries):
    """A second room can be added from the options."""
    flow, _ = options_flow
    flow._current_area_id = "salon"
    flow._current_area_name = "Salon"

    await flow.async_step_add_room(ROOM_INPUT)

    data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert set(data[CONF_PIECES]) == {"bureau", "salon"}


async def test_options_select_room_without_rooms(options_flow):
    """Editing with no rooms aborts."""
    flow, _ = options_flow
    flow._data[CONF_PIECES] = {}

    result = await flow.async_step_select_room(None)

    assert result["reason"] == "no_rooms"
