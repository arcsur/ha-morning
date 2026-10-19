"""Unit tests for Morning DataUpdateCoordinator."""

from datetime import timedelta
import unittest
from unittest.mock import AsyncMock, MagicMock

from custom_components.morning.client import MorningAuthError, MorningClient, MorningConnectionError
from custom_components.morning.coordinator import MorningDataUpdateCoordinator
from custom_components.morning.models import MorningAuthSession, MorningMachine


class TestMorningCoordinator(unittest.IsolatedAsyncioTestCase):
    """Test coordinator update data and token persistence."""

    def setUp(self):
        """Set up test fixtures."""
        self.hass = MagicMock()
        self.client = MagicMock(spec=MorningClient)
        self.client.auth_session = MorningAuthSession(
            access_token="acc",
            id_token="id",
            refresh_token="ref",
            expires_at=9999999999.0,
            email="test@example.com",
        )
        self.entry = MagicMock()
        self.entry.entry_id = "test_entry_id"
        self.entry.data = {
            "email": "test@example.com",
            "access_token": "acc",
            "id_token": "id",
            "refresh_token": "ref",
            "token_expires_at": 9999999999.0,
        }
        self.coordinator = MorningDataUpdateCoordinator(
            hass=self.hass,
            client=self.client,
            entry=self.entry,
            update_interval=timedelta(seconds=30),
        )

    async def test_update_data_success(self):
        """Test successful coordinator update."""
        mock_machine = MorningMachine.from_dict(
            {
                "id": "M_123",
                "name": "My Morning",
                "model": "MM-730",
                "status": "ECO",
                "waterLevel": "NORMAL",
                "brewCount": 10,
                "limeScale": 50,
                "energySaveTimeOut": 1800,
            }
        )
        self.client.get_machines = AsyncMock(return_value=[mock_machine])

        data = await self.coordinator._async_update_data()
        self.assertIn("M_123", data)
        self.assertEqual(data["M_123"].name, "My Morning")
        self.assertEqual(data["M_123"].status, "ECO")

    async def test_update_data_token_persistence(self):
        """Test coordinator persists newly refreshed tokens into config entry."""
        mock_machine = MorningMachine.from_dict({"id": "M_123"})
        self.client.get_machines = AsyncMock(return_value=[mock_machine])

        # Simulate that tokens were refreshed
        self.client.auth_session = MorningAuthSession(
            access_token="new_acc",
            id_token="new_id",
            refresh_token="new_ref",
            expires_at=123456789.0,
            email="test@example.com",
        )

        await self.coordinator._async_update_data()

        self.hass.config_entries.async_update_entry.assert_called_once()
        _, kwargs = self.hass.config_entries.async_update_entry.call_args
        self.assertEqual(kwargs["data"]["access_token"], "new_acc")
        self.assertEqual(kwargs["data"]["id_token"], "new_id")


if __name__ == "__main__":
    unittest.main()
