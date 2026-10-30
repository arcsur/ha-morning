"""Unit tests for Morning binary sensor platform."""

import unittest
from unittest.mock import MagicMock

from custom_components.morning.binary_sensor import (
    MorningBrewingBinarySensor,
    MorningChildLockBinarySensor,
    MorningConnectivityBinarySensor,
    MorningWaterLowBinarySensor,
    async_setup_entry,
)
from custom_components.morning.coordinator import MorningDataUpdateCoordinator
from custom_components.morning.models import MorningMachine


class TestMorningBinarySensors(unittest.IsolatedAsyncioTestCase):
    """Test binary sensor entities."""

    def setUp(self):
        """Set up test fixtures."""
        self.coordinator = MagicMock(spec=MorningDataUpdateCoordinator)
        self.machine = MorningMachine.from_dict({
            "id": "M_123",
            "online": True,
            "status": "BREWING",
            "waterLevel": "LOW",
            "childLock": True,
        })
        self.coordinator.data = {"M_123": self.machine}

    def test_binary_sensors_states(self):
        """Test states of all binary sensors."""
        water_low = MorningWaterLowBinarySensor(self.coordinator, "M_123")
        conn = MorningConnectivityBinarySensor(self.coordinator, "M_123")
        brewing = MorningBrewingBinarySensor(self.coordinator, "M_123")
        child_lock = MorningChildLockBinarySensor(self.coordinator, "M_123")

        self.assertTrue(water_low.is_on)
        self.assertTrue(conn.is_on)
        self.assertTrue(brewing.is_on)
        self.assertTrue(child_lock.is_on)

    async def test_async_setup_entry(self):
        """Test async_setup_entry creates all 4 binary sensors."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {"machine_ids": ["M_123"]}
        hass.data = {"morning": {"test_entry": {"coordinator": self.coordinator}}}
        async_add_entities = MagicMock()

        await async_setup_entry(hass, entry, async_add_entities)
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        self.assertEqual(len(entities), 4)


if __name__ == "__main__":
    unittest.main()
