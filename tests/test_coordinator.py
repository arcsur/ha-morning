"""Unit tests for Morning DataUpdateCoordinator."""

import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from custom_components.morning.client import MorningClient
from custom_components.morning.coordinator import MorningDataUpdateCoordinator
from custom_components.morning.models import (
    MorningAuthSession,
    MorningLiveBrewTelemetry,
    MorningMachine,
)


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
        self.entry.options = {}
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
            user_id="user_uuid_123",
        )

        await self.coordinator._async_update_data()

        self.hass.config_entries.async_update_entry.assert_called_once()
        _, kwargs = self.hass.config_entries.async_update_entry.call_args
        self.assertEqual(kwargs["data"]["access_token"], "new_acc")
        self.assertEqual(kwargs["data"]["id_token"], "new_id")
        self.assertEqual(kwargs["data"]["user_id"], "user_uuid_123")

    async def test_water_level_initial_seeding_and_clamping(self):
        """Test water level initial seeding and LOW water clamping."""
        # Initial machine with NORMAL water level
        m_normal = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "NORMAL",
            "brewCount": 5,
        })
        self.client.get_machines = AsyncMock(return_value=[m_normal])
        await self.coordinator._async_update_data()
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 850.0)

        # Machine drops to LOW water level
        m_low = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "LOW",
            "brewCount": 5,
        })
        self.client.get_machines = AsyncMock(return_value=[m_low])
        await self.coordinator._async_update_data()
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 0.0)

    async def test_water_level_low_to_normal_refill(self):
        """Test tank reseating transition from LOW to NORMAL resets water level to capacity."""
        m_low = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "LOW",
            "brewCount": 5,
        })
        self.client.get_machines = AsyncMock(return_value=[m_low])
        await self.coordinator._async_update_data()
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 0.0)

        # User fills tank and reseats -> NORMAL
        m_normal = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "NORMAL",
            "brewCount": 5,
        })
        self.client.get_machines = AsyncMock(return_value=[m_normal])
        await self.coordinator._async_update_data()
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 850.0)

    async def test_water_level_manual_refill(self):
        """Test manual refill methods."""
        self.coordinator.set_estimated_water_level("M_123", 200.0)
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 200.0)

        # Partial refill
        self.coordinator.refill_tank("M_123", amount_ml=300)
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 500.0)

        # Full refill
        self.coordinator.refill_tank("M_123")
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 850.0)

    async def test_live_brew_telemetry_and_no_double_decrement(self):
        """Test live brew updates decrement tank level and prevent REST poll double decrement."""
        self.coordinator.set_estimated_water_level("M_123", 800.0)

        # Brew starts
        t1 = MorningLiveBrewTelemetry(
            stage="brewing",
            is_brewing=True,
            water_output=30.0,
            mass_output=28.5,
            temperature=92,
        )
        self.coordinator.handle_live_brew_update("M_123", t1)
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 770.0)
        self.assertEqual(self.coordinator.live_telemetry["M_123"].water_output, 30.0)

        # Brew in progress
        t2 = MorningLiveBrewTelemetry(
            stage="brewing",
            is_brewing=True,
            water_output=120.0,
            mass_output=118.0,
            temperature=93,
        )
        self.coordinator.handle_live_brew_update("M_123", t2)
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 680.0)

        # Brew finishes
        t3 = MorningLiveBrewTelemetry(
            stage="done",
            is_brewing=False,
            water_output=120.0,
            mass_output=118.0,
            temperature=91,
        )
        self.coordinator.handle_live_brew_update("M_123", t3)
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 680.0)
        # Value freezes and stays fixed
        self.assertEqual(self.coordinator.live_telemetry["M_123"].stage, "done")
        self.assertEqual(self.coordinator.live_telemetry["M_123"].water_output, 120.0)

        # Now REST poll runs and detects brew_count incremented from 10 to 11
        self.coordinator._previous_brew_counts["M_123"] = 10
        self.coordinator._previous_water_levels["M_123"] = "NORMAL"
        m_done = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "NORMAL",
            "brewCount": 11,
        })
        self.client.get_machines = AsyncMock(return_value=[m_done])
        await self.coordinator._async_update_data()

        # Water level should STILL be 680.0 (not decremented by fallback 50 ml)
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 680.0)

    async def test_polling_fallback_brew_decrement(self):
        """Test polling fallback decrements water level when brew count increases without live stream."""
        self.coordinator.set_estimated_water_level("M_123", 850.0)
        self.coordinator._previous_brew_counts["M_123"] = 20
        self.coordinator._previous_water_levels["M_123"] = "NORMAL"

        m_poll = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "NORMAL",
            "brewCount": 22,  # 2 new brews
        })
        self.client.get_machines = AsyncMock(return_value=[m_poll])
        await self.coordinator._async_update_data()

        # 2 brews * 50ml fallback = 100ml decrement -> 750ml
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 750.0)
        self.assertEqual(self.coordinator.live_telemetry["M_123"].water_output, 100.0)
        self.assertEqual(self.coordinator.live_telemetry["M_123"].stage, "done")

    def test_record_purge_manual(self):
        """Test manually recording a purge rinse decrements water level."""
        self.coordinator.set_estimated_water_level("M_123", 800.0)
        # Default purge volume is 30ml
        self.coordinator.record_purge("M_123")
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 770.0)
        self.assertEqual(self.coordinator.live_telemetry["M_123"].stage, "purge")
        self.assertEqual(self.coordinator.live_telemetry["M_123"].water_output, 30.0)

        # Explicit amount
        self.coordinator.record_purge("M_123", amount_ml=50)
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 720.0)
        self.assertEqual(self.coordinator.live_telemetry["M_123"].water_output, 50.0)

    async def test_flow_meter_delta_purge_reconciliation(self):
        """Test flow meter total_water_ml increase without brew decrements exact delta."""
        self.coordinator.set_estimated_water_level("M_123", 800.0)
        self.coordinator._previous_brew_counts["M_123"] = 10
        self.coordinator._previous_water_levels["M_123"] = "NORMAL"
        self.coordinator._previous_total_water["M_123"] = 1000
        self.coordinator._previous_statuses["M_123"] = "READY"

        m_purge = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "NORMAL",
            "brewCount": 10,  # Brew count unchanged!
            "status": "READY",
            "brew": {"count": 10, "ml": 1028},  # 28ml dispensed by flow meter
        })
        self.client.get_machines = AsyncMock(return_value=[m_purge])
        await self.coordinator._async_update_data()

        # 800 - 28 = 772 ml
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 772.0)
        self.assertEqual(self.coordinator.live_telemetry["M_123"].stage, "purge")
        self.assertEqual(self.coordinator.live_telemetry["M_123"].water_output, 28.0)

    async def test_purge_status_edge_detection(self):
        """Test status transitioning from PURGE to READY decrements configured purge volume."""
        self.coordinator.set_estimated_water_level("M_123", 800.0)
        self.coordinator._previous_brew_counts["M_123"] = 10
        self.coordinator._previous_water_levels["M_123"] = "NORMAL"
        self.coordinator._previous_total_water["M_123"] = 1000
        self.coordinator._previous_statuses["M_123"] = "PURGE"

        m_ready = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "NORMAL",
            "brewCount": 10,
            "status": "READY",
            "brew": {"count": 10, "ml": 1000},  # total water didn't change
        })
        self.client.get_machines = AsyncMock(return_value=[m_ready])
        await self.coordinator._async_update_data()

        # 800 - 30 (default purge vol) = 770 ml
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 770.0)
        self.assertEqual(self.coordinator.live_telemetry["M_123"].stage, "purge")
        self.assertEqual(self.coordinator.live_telemetry["M_123"].water_output, 30.0)


if __name__ == "__main__":
    unittest.main()
