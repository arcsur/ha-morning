"""Unit tests for Morning sensor platform."""

import dataclasses
import unittest
from unittest.mock import AsyncMock, MagicMock

from custom_components.morning.coordinator import MorningDataUpdateCoordinator
from custom_components.morning.models import MorningLiveBrewTelemetry, MorningMachine
from custom_components.morning.sensor import (
    MorningBrewBloomSensor,
    MorningBrewMassDispensedSensor,
    MorningBrewStageSensor,
    MorningBrewTemperatureSensor,
    MorningBrewWaterDispensedSensor,
    MorningEstimatedWaterLevelSensor,
    MorningFaultCodeSensor,
    MorningLifetimeWaterSensor,
    MorningSlaveFirmwareSensor,
    MorningStatusSensor,
    MorningWaterTankPercentageSensor,
    async_setup_entry,
)


class TestMorningSensors(unittest.IsolatedAsyncioTestCase):
    """Test Morning sensor entities."""

    def setUp(self):
        """Set up test coordinator and machine."""
        self.coordinator = MagicMock(spec=MorningDataUpdateCoordinator)
        self.coordinator.data = {}
        self.coordinator.water_tank_levels = {}
        self.coordinator.live_telemetry = {}
        self.coordinator.lifetime_water_levels = {}
        self.coordinator.get_tank_capacity.return_value = 850
        self.coordinator.get_estimated_water_level.side_effect = (
            lambda mid: self.coordinator.water_tank_levels.get(mid, 850.0)
        )
        self.coordinator.get_lifetime_water_ml.side_effect = (
            lambda mid: self.coordinator.lifetime_water_levels.get(mid, 0.0)
        )
        self.coordinator.set_lifetime_water_ml.side_effect = (
            lambda mid, v: self.coordinator.lifetime_water_levels.__setitem__(mid, float(v))
        )
        self.coordinator.add_lifetime_water_ml.side_effect = (
            lambda mid, v: self.coordinator.lifetime_water_levels.__setitem__(
                mid, self.coordinator.lifetime_water_levels.get(mid, 0.0) + float(v)
            )
        )

        self.machine = MorningMachine.from_dict({
            "id": "M_123",
            "name": "Morning Machine",
            "model": "MM-730",
            "status": "READY",
            "waterLevel": "NORMAL",
            "brewCount": 42,
            "limeScale": 10,
            "childLock": True,
            "stm32Version": "v1.2.3",
            "faultInfomation": "NO_ERROR",
            "pumpFlowRate": {"k1": 1.05, "p1": 0.98},
            "brew": {"ml": 12500},
        })
        self.coordinator.data["M_123"] = self.machine

    def test_status_sensor_attributes(self):
        """Test status sensor value and extended diagnostic attributes."""
        sensor = MorningStatusSensor(self.coordinator, "M_123")
        self.assertEqual(sensor.native_value, "ready")

        # Status override when brew is finished but shadow still reports BREWING (capsule prompt active)
        self.coordinator.data["M_123"] = dataclasses.replace(self.machine, status="BREWING")
        self.coordinator.live_telemetry["M_123"] = MorningLiveBrewTelemetry(
            stage="done",
            is_brewing=False,
            water_output=50.0,
        )
        self.assertEqual(sensor.native_value, "done")
        self.assertEqual(sensor.icon, "mdi:check-circle-outline")

        # Reset back to ready
        self.coordinator.data["M_123"] = dataclasses.replace(self.machine, status="READY")
        self.coordinator.live_telemetry["M_123"] = MorningLiveBrewTelemetry(
            stage="idle",
            is_brewing=False,
        )
        self.assertEqual(sensor.native_value, "ready")

        attrs = sensor.extra_state_attributes
        self.assertTrue(attrs["child_lock"])
        self.assertEqual(attrs["stm32_version"], "v1.2.3")
        self.assertEqual(attrs["fault_information"], "NO_ERROR")
        self.assertEqual(attrs["pump_flow_rate_k1"], 1.05)
        self.assertEqual(attrs["pump_flow_rate_p1"], 0.98)
        self.assertEqual(attrs["total_water_ml"], 12500)

    def test_estimated_water_level_sensor(self):
        """Test estimated water level sensor and percentage."""
        self.coordinator.water_tank_levels["M_123"] = 680.0
        sensor = MorningEstimatedWaterLevelSensor(self.coordinator, "M_123")
        self.assertEqual(sensor.native_value, 680.0)

        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs["capacity_ml"], 850)
        self.assertEqual(attrs["percentage"], 80.0)
        self.assertEqual(attrs["water_level_sensor"], "NORMAL")

        pct_sensor = MorningWaterTankPercentageSensor(self.coordinator, "M_123")
        self.assertEqual(pct_sensor.native_value, 80.0)

    def test_brew_telemetry_live_and_sticky_sensors(self):
        """Test live brew water, mass, temp, stage, and bloom sensors."""
        water_sensor = MorningBrewWaterDispensedSensor(self.coordinator, "M_123")
        mass_sensor = MorningBrewMassDispensedSensor(self.coordinator, "M_123")
        temp_sensor = MorningBrewTemperatureSensor(self.coordinator, "M_123")
        stage_sensor = MorningBrewStageSensor(self.coordinator, "M_123")
        bloom_sensor = MorningBrewBloomSensor(self.coordinator, "M_123")

        # Initial state before any brew
        self.assertIsNone(water_sensor.native_value)
        self.assertIsNone(mass_sensor.native_value)
        self.assertIsNone(temp_sensor.native_value)
        self.assertEqual(stage_sensor.native_value, "idle")
        self.assertEqual(bloom_sensor.native_value, 0)

        # Verify transient brew sensors do not have state_class (avoids 5-min LTS decimation)
        self.assertIsNone(water_sensor.entity_description.state_class)
        self.assertIsNone(mass_sensor.entity_description.state_class)
        self.assertIsNone(temp_sensor.entity_description.state_class)

        # Active brewing telemetry arrives
        test_profile = [
            {"t": 0.0, "water": 0.0, "mass": 0.0, "temp": 93, "flow": 0.0, "stage": "brewing"},
            {"t": 5.0, "water": 35.5, "mass": 34.2, "temp": 93, "flow": 7.1, "stage": "brewing"},
        ]
        self.coordinator.get_brew_profile.return_value = test_profile
        self.coordinator.live_telemetry["M_123"] = MorningLiveBrewTelemetry(
            stage="brewing",
            is_brewing=True,
            water_output=35.5,
            mass_output=34.2,
            temperature=93,
            bloom_lapse=10,
            profile=test_profile,
        )

        self.assertEqual(water_sensor.native_value, 35.5)
        self.assertEqual(mass_sensor.native_value, 34.2)
        self.assertEqual(temp_sensor.native_value, 93)
        self.assertEqual(stage_sensor.native_value, "brewing")
        self.assertEqual(bloom_sensor.native_value, 10)
        self.assertEqual(stage_sensor.extra_state_attributes["extraction_profile"], test_profile)
        self.assertEqual(water_sensor.extra_state_attributes["extraction_profile"], test_profile)

        # Brew finishes -> values freeze and stay fixed
        self.coordinator.live_telemetry["M_123"] = MorningLiveBrewTelemetry(
            stage="done",
            is_brewing=False,
            water_output=150.0,
            mass_output=148.0,
            temperature=92,
            bloom_lapse=15,
        )

        self.assertEqual(water_sensor.native_value, 150.0)
        self.assertEqual(mass_sensor.native_value, 148.0)
        self.assertEqual(temp_sensor.native_value, 92)
        self.assertEqual(stage_sensor.native_value, "done")
        self.assertEqual(bloom_sensor.native_value, 15)

    def test_lifetime_and_diagnostic_sensors(self):
        """Test lifetime water used, slave firmware, and fault code sensors."""
        life_sensor = MorningLifetimeWaterSensor(self.coordinator, "M_123")
        self.assertEqual(life_sensor.native_value, 12.5)  # 12500 ml = 12.5 L

        slave_sensor = MorningSlaveFirmwareSensor(self.coordinator, "M_123")
        self.assertEqual(slave_sensor.native_value, "v1.2.3")

        fault_sensor = MorningFaultCodeSensor(self.coordinator, "M_123")
        self.assertEqual(fault_sensor.native_value, "NO_ERROR")

    async def test_water_level_sensor_restore_from_last_state(self):
        """Test water level restores from async_get_last_state when sensor data is None."""
        sensor = MorningEstimatedWaterLevelSensor(self.coordinator, "M_123")
        sensor.coordinator._water_level_seeded = {}
        sensor.async_get_last_sensor_data = AsyncMock(return_value=None)

        last_state = MagicMock()
        last_state.state = "511.0"
        sensor.async_get_last_state = AsyncMock(return_value=last_state)

        await sensor.async_added_to_hass()
        self.coordinator.set_estimated_water_level.assert_called_once_with("M_123", 511.0)

    async def test_brew_temperature_sensor_restore_from_last_state(self):
        """Test brew temperature sensor restores from last state when idle."""
        temp_sensor = MorningBrewTemperatureSensor(self.coordinator, "M_123")
        temp_sensor.async_get_last_sensor_data = AsyncMock(return_value=None)

        last_state = MagicMock()
        last_state.state = "93"
        temp_sensor.async_get_last_state = AsyncMock(return_value=last_state)

        await temp_sensor.async_added_to_hass()
        self.assertEqual(temp_sensor.native_value, 93)

    def test_status_sensor_reflects_live_iot_and_cancel_states(self):
        """Test status sensor immediately reflects active IoT stages and cancel reset."""
        import time

        from custom_components.morning.models import MorningLiveBrewTelemetry
        from custom_components.morning.sensor import MorningStatusSensor

        status_sensor = MorningStatusSensor(self.coordinator, "M_123")
        # Machine shadow is still ECO, but live IoT heating starts
        self.coordinator.data["M_123"] = dataclasses.replace(self.machine, status="ECO")
        self.coordinator.live_telemetry["M_123"] = MorningLiveBrewTelemetry(
            stage="heating", is_brewing=True, last_updated=time.time()
        )
        self.assertEqual(status_sensor.native_value, "heating")

        # Machine shadow was BREWING, then user cancels via live IoT (stage='idle', is_brewing=False)
        self.coordinator.data["M_123"] = dataclasses.replace(self.machine, status="BREWING")
        self.coordinator.live_telemetry["M_123"] = MorningLiveBrewTelemetry(
            stage="idle", is_brewing=False, last_updated=time.time()
        )
        self.assertEqual(status_sensor.native_value, "idle")

    async def test_async_setup_entry(self):
        """Test async_setup_entry adds all expected sensors."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {"machine_ids": ["M_123"]}

        hass.data = {"morning": {"test_entry": {"coordinator": self.coordinator}}}
        async_add_entities = MagicMock()

        await async_setup_entry(hass, entry, async_add_entities)
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        self.assertEqual(len(entities), 15)


if __name__ == "__main__":
    unittest.main()
