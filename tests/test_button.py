"""Unit tests for Morning button platform."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from custom_components.morning.button import (
    MorningCheckUpdatesButton,
    MorningRefillTankButton,
    MorningResetButton,
    async_setup_entry,
)
from custom_components.morning.coordinator import MorningDataUpdateCoordinator
from custom_components.morning.models import MorningMachine


class TestMorningButtons(unittest.IsolatedAsyncioTestCase):
    """Test button entities."""

    def setUp(self):
        """Set up test fixtures."""
        self.coordinator = MagicMock(spec=MorningDataUpdateCoordinator)
        self.coordinator.client = MagicMock()
        self.coordinator.client.reset_machine = AsyncMock()
        self.coordinator.client.check_updates = AsyncMock()
        self.coordinator.async_request_refresh = AsyncMock()
        self.coordinator.data = {
            "M_123": MorningMachine.from_dict({"id": "M_123", "type": "COFFEE"})
        }

    async def test_refill_button(self):
        """Test refill tank button calls coordinator.refill_tank."""
        btn = MorningRefillTankButton(self.coordinator, "M_123")
        await btn.async_press()
        self.coordinator.refill_tank.assert_called_once_with("M_123")

    async def test_reset_button(self):
        """Test reset machine button."""
        btn = MorningResetButton(self.coordinator, "M_123")
        await btn.async_press()
        self.coordinator.client.reset_machine.assert_called_once()
        self.coordinator.async_request_refresh.assert_called_once()

    async def test_check_updates_button(self):
        """Test check updates button."""
        btn = MorningCheckUpdatesButton(self.coordinator, "M_123")
        await btn.async_press()
        self.coordinator.client.check_updates.assert_called_once_with(machine_type="COFFEE")
        self.coordinator.async_request_refresh.assert_called_once()

    async def test_async_setup_entry(self):
        """Test async_setup_entry creates all 3 buttons."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {"machine_ids": ["M_123"]}
        hass.data = {"morning": {"test_entry": {"coordinator": self.coordinator}}}
        async_add_entities = MagicMock()

        await async_setup_entry(hass, entry, async_add_entities)
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        self.assertEqual(len(entities), 3)


if __name__ == "__main__":
    unittest.main()
