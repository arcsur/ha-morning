"""Unit tests for Morning sensor platform."""

import unittest
from unittest.mock import MagicMock

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
        self.coordinator.get_tank_capacity.return_value = 850
        self.coordinator.get_estimated_water_level.side_effect = (
            lambda mid: self.coordinator.water_tank_levels.get(mid, 850.0)
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

        # Active brewing telemetry arrives
        self.coordinator.live_telemetry["M_123"] = MorningLiveBrewTelemetry(
            stage="brewing",
            is_brewing=True,
            water_output=35.5,
            mass_output=34.2,
            temperature=93,
            bloom_lapse=10,
        )

        self.assertEqual(water_sensor.native_value, 35.5)
        self.assertEqual(mass_sensor.native_value, 34.2)
        self.assertEqual(temp_sensor.native_value, 93)
        self.assertEqual(stage_sensor.native_value, "brewing")
        self.assertEqual(bloom_sensor.native_value, 10)

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
