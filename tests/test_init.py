"""Tests for setup, migration and services."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.chauffage_intelligent import (
    SERVICE_REFRESH,
    SERVICE_RESET,
    SERVICE_SET_SCHEDULE,
    SERVICE_SET_TEMPERATURE,
    _async_setup_services,
    _remove_legacy_learning_file,
    async_migrate_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.chauffage_intelligent.const import (
    CONF_PIECE_OFFSET,
    CONF_PIECE_TEMPERATURES,
    CONF_PIECES,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
    LEGACY_LEARNING_FILE,
    TEMP_CONFORT,
    TEMP_ECO,
    TEMP_HORS_GEL,
)
from custom_components.chauffage_intelligent.coordinator import (
    ChauffageIntelligentCoordinator,
)

# ------------------------------------------------------------------ migration


@pytest.fixture
def legacy_entry():
    """A version 1 config entry, calendar and prediction settings included."""
    entry = MagicMock()
    entry.version = 1
    entry.data = {
        "calendar": "calendar.google_home",
        "presence_trackers": ["device_tracker.phone"],
        "security_factor": 1.3,
        "min_preheat_time": 30,
        "derivative_window": 30,
        CONF_UPDATE_INTERVAL: 300,
        CONF_PIECES: {
            "bureau": {
                "name": "Bureau",
                "area_id": "bureau",
                "type": "bureau",
                "radiateurs": ["climate.bilbao_bureau"],
                "sonde": "sensor.temperature_bureau",
                CONF_PIECE_TEMPERATURES: {
                    TEMP_CONFORT: 19,
                    TEMP_ECO: 17,
                    TEMP_HORS_GEL: 7,
                },
            }
        },
    }
    return entry


@pytest.fixture
def migration_hass(mock_hass, tmp_path):
    """A hass whose storage lives in tmp_path and whose executor runs inline."""
    storage = tmp_path / ".storage"
    storage.mkdir(parents=True, exist_ok=True)
    mock_hass.config.path.return_value = str(storage)

    async def run(func, *args):
        return func(*args)

    mock_hass.async_add_executor_job = run
    mock_hass.config_entries.async_update_entry = MagicMock()
    return mock_hass


async def test_migration_drops_the_legacy_settings(migration_hass, legacy_entry):
    """Calendar, presence and prediction keys are removed."""
    with patch("custom_components.chauffage_intelligent.ScheduleStore") as store_cls:
        store_cls.return_value = _fake_store()
        assert await async_migrate_entry(migration_hass, legacy_entry) is True

    data = migration_hass.config_entries.async_update_entry.call_args.kwargs["data"]
    for key in ("calendar", "presence_trackers", "security_factor", "min_preheat_time",
                "derivative_window"):
        assert key not in data


async def test_migration_keeps_the_rooms_and_adds_an_offset(migration_hass, legacy_entry):
    """Rooms survive the migration and gain a neutral offset."""
    with patch("custom_components.chauffage_intelligent.ScheduleStore") as store_cls:
        store_cls.return_value = _fake_store()
        await async_migrate_entry(migration_hass, legacy_entry)

    data = migration_hass.config_entries.async_update_entry.call_args.kwargs["data"]
    piece = data[CONF_PIECES]["bureau"]

    assert piece["radiateurs"] == ["climate.bilbao_bureau"]
    assert piece[CONF_PIECE_TEMPERATURES][TEMP_CONFORT] == 19
    assert piece[CONF_PIECE_OFFSET] == 0.0


async def test_migration_seeds_a_schedule(migration_hass, legacy_entry):
    """Every existing room gets a starting planning."""
    store = _fake_store()
    with patch("custom_components.chauffage_intelligent.ScheduleStore") as store_cls:
        store_cls.return_value = store
        await async_migrate_entry(migration_hass, legacy_entry)

    assert store.has("bureau")
    assert store.get("bureau")


async def test_migration_bumps_the_version(migration_hass, legacy_entry):
    """The entry is stamped as version 2."""
    with patch("custom_components.chauffage_intelligent.ScheduleStore") as store_cls:
        store_cls.return_value = _fake_store()
        await async_migrate_entry(migration_hass, legacy_entry)

    assert migration_hass.config_entries.async_update_entry.call_args.kwargs["version"] == 2


async def test_migration_removes_the_learning_file(migration_hass, legacy_entry, tmp_path):
    """The heating-rate learning store is deleted."""
    learning = tmp_path / ".storage" / LEGACY_LEARNING_FILE
    learning.write_text(json.dumps({"bureau": [{"rate": 1.2}]}))

    with patch("custom_components.chauffage_intelligent.ScheduleStore") as store_cls:
        store_cls.return_value = _fake_store()
        await async_migrate_entry(migration_hass, legacy_entry)

    assert not learning.exists()


async def test_migration_is_a_noop_for_current_entries(migration_hass, legacy_entry):
    """A version 2 entry is left alone."""
    legacy_entry.version = 2

    assert await async_migrate_entry(migration_hass, legacy_entry) is True
    migration_hass.config_entries.async_update_entry.assert_not_called()


def test_removing_a_missing_learning_file_is_safe(migration_hass):
    """Cleanup does not fail when the file was already gone."""
    _remove_legacy_learning_file(migration_hass)


def _fake_store():
    """Build an in-memory ScheduleStore stand-in."""
    from .conftest import FakeScheduleStore

    store = FakeScheduleStore()
    store.async_load = AsyncMock()
    return store


# ------------------------------------------------------------------- services


@pytest.fixture
def services(mock_hass, coordinator):
    """Register the services against a hass holding one coordinator."""
    registry: dict[str, object] = {}

    mock_hass.data = {DOMAIN: {"entry": coordinator, "store": coordinator.store}}
    mock_hass.services.has_service.return_value = False
    mock_hass.services.async_register.side_effect = (
        lambda domain, service, handler, schema=None: registry.__setitem__(service, handler)
    )

    _async_setup_services(mock_hass)
    return registry, coordinator


def make_call(data):
    """Build a fake ServiceCall."""
    call = MagicMock()
    call.data = data
    return call


async def test_set_temperature_service(services):
    """The service forces a temperature on the right room."""
    registry, coordinator = services
    coordinator.async_set_override = AsyncMock()

    await registry[SERVICE_SET_TEMPERATURE](
        make_call({"piece": "bureau", "temperature": 21.0, "duree": 60})
    )

    coordinator.async_set_override.assert_awaited_once_with("bureau", 21.0, 60)


async def test_set_temperature_without_duration(services):
    """Omitting the duration passes None through."""
    registry, coordinator = services
    coordinator.async_set_override = AsyncMock()

    await registry[SERVICE_SET_TEMPERATURE](make_call({"piece": "bureau", "temperature": 21.0}))

    coordinator.async_set_override.assert_awaited_once_with("bureau", 21.0, None)


async def test_set_temperature_on_unknown_room(services):
    """An unknown room raises a validation error the UI can show."""
    registry, _ = services

    with pytest.raises(ServiceValidationError):
        await registry[SERVICE_SET_TEMPERATURE](make_call({"piece": "cave", "temperature": 21.0}))


async def test_reset_service_for_one_room(services):
    """Reset targets a single room when given one."""
    registry, coordinator = services
    coordinator.async_reset_override = AsyncMock()

    await registry[SERVICE_RESET](make_call({"piece": "bureau"}))

    coordinator.async_reset_override.assert_awaited_once_with("bureau")


async def test_reset_service_for_every_room(services):
    """Reset without a room clears everything."""
    registry, coordinator = services
    coordinator.async_reset_override = AsyncMock()

    await registry[SERVICE_RESET](make_call({}))

    coordinator.async_reset_override.assert_awaited_once_with()


async def test_reset_service_on_unknown_room(services):
    """Resetting an unknown room raises."""
    registry, _ = services

    with pytest.raises(ServiceValidationError):
        await registry[SERVICE_RESET](make_call({"piece": "cave"}))


async def test_refresh_service(services):
    """Refresh asks every coordinator to recompute."""
    registry, coordinator = services
    coordinator.async_request_refresh = AsyncMock()

    await registry[SERVICE_REFRESH](make_call({}))

    coordinator.async_request_refresh.assert_awaited_once()


async def test_set_schedule_service(services):
    """The service replaces a room's planning."""
    registry, coordinator = services

    await registry[SERVICE_SET_SCHEDULE](
        make_call(
            {
                "piece": "salon",
                "slots": [{"day": 1, "start": "08:00", "end": "10:00", "temperature": 20}],
            }
        )
    )

    assert coordinator.get_schedule("salon") == [
        {"day": 1, "start": "08:00", "end": "10:00", "temperature": 20.0}
    ]


async def test_set_schedule_on_unknown_room(services):
    """An unknown room raises instead of silently doing nothing."""
    registry, _ = services

    with pytest.raises(ServiceValidationError):
        await registry[SERVICE_SET_SCHEDULE](make_call({"piece": "cave", "slots": []}))


def test_services_are_registered_once(mock_hass, coordinator):
    """A second config entry does not re-register the services."""
    mock_hass.data = {DOMAIN: {"entry": coordinator}}
    mock_hass.services.has_service.return_value = True

    _async_setup_services(mock_hass)

    mock_hass.services.async_register.assert_not_called()


# ---------------------------------------------------------------- setup/unload


@pytest.fixture
def setup_hass(mock_hass):
    """A hass ready to receive a config entry setup."""
    mock_hass.data = {}
    mock_hass.config_entries.async_forward_entry_setups = AsyncMock()
    mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    mock_hass.services.has_service.return_value = False
    return mock_hass


@pytest.fixture
def entry(basic_config):
    """A version 2 config entry with two rooms."""
    entry = MagicMock()
    entry.version = 2
    entry.entry_id = "entry1"
    entry.data = basic_config
    return entry


@pytest.fixture
def setup_patches():
    """Patch out the pieces that need a real Home Assistant."""
    from .conftest import FakeScheduleStore

    module = "custom_components.chauffage_intelligent"
    store = FakeScheduleStore()
    store.async_load = AsyncMock()

    with (
        patch(f"{module}.ScheduleStore", return_value=store),
        patch(f"{module}.async_register_panel", new=AsyncMock()) as panel,
        patch(f"{module}.async_register_websocket_api") as websocket,
        patch(f"{module}.async_unregister_panel", new=AsyncMock()) as unpanel,
        patch.object(
            ChauffageIntelligentCoordinator,
            "async_config_entry_first_refresh",
            new=AsyncMock(),
        ),
    ):
        yield store, panel, websocket, unpanel


async def test_setup_entry_seeds_a_schedule_for_new_rooms(setup_hass, entry, setup_patches):
    """A room without a planning gets the default one."""
    store, _, _, _ = setup_patches

    assert await async_setup_entry(setup_hass, entry) is True

    assert store.get("bureau")
    assert store.get("salon")


async def test_setup_entry_keeps_an_existing_schedule(setup_hass, entry, setup_patches):
    """An already stored planning is never overwritten at startup."""
    store, _, _, _ = setup_patches
    await store.async_set(
        "bureau", [{"day": 3, "start": "06:00", "end": "07:00", "temperature": 21}]
    )

    await async_setup_entry(setup_hass, entry)

    assert store.get("bureau") == [
        {"day": 3, "start": "06:00", "end": "07:00", "temperature": 21.0}
    ]


async def test_setup_entry_registers_panel_and_websocket(setup_hass, entry, setup_patches):
    """The panel and its API come up with the entry."""
    _, panel, websocket, _ = setup_patches

    await async_setup_entry(setup_hass, entry)

    panel.assert_awaited_once()
    websocket.assert_called_once()


async def test_setup_entry_forwards_the_platforms(setup_hass, entry, setup_patches):
    """Climate, sensor and select are set up; binary_sensor is gone."""
    await async_setup_entry(setup_hass, entry)

    platforms = setup_hass.config_entries.async_forward_entry_setups.call_args.args[1]
    assert [str(platform) for platform in platforms] == ["climate", "sensor", "select"]


async def test_unload_entry_tears_everything_down(setup_hass, entry, setup_patches):
    """Unloading the last entry drops the store, panel and services."""
    _, _, _, unpanel = setup_patches
    await async_setup_entry(setup_hass, entry)
    # Registration normally leaves these behind; they must not be mistaken for
    # a still-loaded config entry.
    setup_hass.data[DOMAIN]["panel_registered"] = True
    setup_hass.data[DOMAIN]["websocket_registered"] = True
    coordinator = setup_hass.data[DOMAIN]["entry1"]
    coordinator.async_shutdown_listeners = MagicMock()

    assert await async_unload_entry(setup_hass, entry) is True

    coordinator.async_shutdown_listeners.assert_called_once()
    unpanel.assert_awaited_once()
    assert "entry1" not in setup_hass.data[DOMAIN]
    assert "store" not in setup_hass.data[DOMAIN]


async def test_unload_entry_when_it_fails(setup_hass, entry, setup_patches):
    """A failed platform unload leaves the coordinator in place."""
    await async_setup_entry(setup_hass, entry)
    setup_hass.config_entries.async_unload_platforms.return_value = False

    assert await async_unload_entry(setup_hass, entry) is False
    assert "entry1" in setup_hass.data[DOMAIN]
