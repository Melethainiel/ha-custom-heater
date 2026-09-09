"""Tests for the sensor entities."""

from __future__ import annotations

import pytest
from homeassistant.components.sensor import SensorDeviceClass

from custom_components.chauffage_intelligent.const import (
    DOMAIN,
    SOURCE_DEFAUT,
    SOURCE_MANUEL,
    SOURCE_OFF,
    SOURCE_PLANNING,
)
from custom_components.chauffage_intelligent.sensor import (
    RoomSourceSensor,
    RoomTargetTempSensor,
    async_setup_entry,
)


@pytest.fixture
def target_sensor(coordinator):
    """A target temperature sensor for the office."""
    return RoomTargetTempSensor(coordinator, "bureau", coordinator.pieces["bureau"])


@pytest.fixture
def source_sensor(coordinator):
    """A setpoint source sensor for the office."""
    return RoomSourceSensor(coordinator, "bureau", coordinator.pieces["bureau"])


def set_data(coordinator, **overrides):
    """Publish coordinator data for the office."""
    payload = {
        "consigne": 19.0,
        "source": SOURCE_PLANNING,
        "temperature": 18.0,
        "creneau_actuel": "07:00-09:00",
        "prochain_changement": "2026-09-07T09:00:00",
        "off": False,
    }
    payload.update(overrides)
    coordinator.data = {"pieces": {"bureau": payload}}


def test_target_sensor_reports_the_setpoint(target_sensor, coordinator):
    """The sensor mirrors the resolved setpoint."""
    set_data(coordinator)

    assert target_sensor.native_value == 19.0
    assert target_sensor.device_class == SensorDeviceClass.TEMPERATURE
    assert target_sensor.unique_id == f"{DOMAIN}_bureau_temperature_cible"


def test_target_sensor_without_data(target_sensor, coordinator):
    """Before the first refresh the value is unknown."""
    coordinator.data = None
    assert target_sensor.native_value is None


@pytest.mark.parametrize(
    "source", [SOURCE_PLANNING, SOURCE_MANUEL, SOURCE_DEFAUT, SOURCE_OFF]
)
def test_source_sensor_reports_every_source(source_sensor, coordinator, source):
    """Each source is a declared enum option."""
    set_data(coordinator, source=source)

    assert source_sensor.native_value == source
    assert source in source_sensor.options


def test_source_sensor_is_an_enum(source_sensor):
    """The sensor is an enum so its states can be translated."""
    assert source_sensor.device_class == SensorDeviceClass.ENUM
    assert source_sensor.unique_id == f"{DOMAIN}_bureau_source_consigne"


def test_source_sensor_attributes(source_sensor, coordinator):
    """The slot and the next change are exposed as attributes."""
    set_data(coordinator)
    attrs = source_sensor.extra_state_attributes

    assert attrs["creneau_actuel"] == "07:00-09:00"
    assert attrs["prochain_changement"] == "2026-09-07T09:00:00"


def test_source_sensor_without_data(source_sensor, coordinator):
    """Missing data yields no value and empty attributes."""
    coordinator.data = None

    assert source_sensor.native_value is None
    assert source_sensor.extra_state_attributes == {
        "creneau_actuel": None,
        "prochain_changement": None,
    }


async def test_setup_entry_creates_two_sensors_per_room(hass_with_coordinator):
    """Each room gets a target temperature and a source sensor."""
    hass, entry, _ = hass_with_coordinator
    added = []

    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))

    assert len(added) == 4
    assert {type(entity).__name__ for entity in added} == {
        "RoomTargetTempSensor",
        "RoomSourceSensor",
    }
