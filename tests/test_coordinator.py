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
        self.assertEqual(self.coordinator.live_telemetry["M_123"].stage, "done")
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
        self.assertEqual(self.coordinator.live_telemetry["M_123"].stage, "done")
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
        self.assertEqual(self.coordinator.live_telemetry["M_123"].stage, "done")
        self.assertEqual(self.coordinator.live_telemetry["M_123"].water_output, 30.0)

    async def test_fallback_brew_and_flow_meter_reconciliation(self):
        """Test fallback brew deduction and subsequent flow meter reconciliation."""
        self.coordinator.set_estimated_water_level("M_123", 800.0)
        self.coordinator._previous_brew_counts["M_123"] = 10
        self.coordinator._previous_water_levels["M_123"] = "NORMAL"
        self.coordinator._previous_total_water["M_123"] = 1000
        self.coordinator._previous_statuses["M_123"] = "READY"

        # Poll 1: machine starts brewing
        m_brewing = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "NORMAL",
            "brewCount": 10,
            "status": "BREWING",
            "brew": {"count": 10, "ml": 1000},
        })
        self.client.get_machines = AsyncMock(return_value=[m_brewing])
        await self.coordinator._async_update_data()

        # Fallback 50ml assumed immediately: 800 - 50 = 750ml
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 750.0)
        self.assertEqual(self.coordinator.live_telemetry["M_123"].stage, "brewing")
        self.assertTrue(self.coordinator.live_telemetry["M_123"].is_brewing)

        # Poll 2: brew completes (brewCount increments, but status still BREWING while prompt active)
        m_done_prompt = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "NORMAL",
            "brewCount": 11,
            "status": "BREWING",
            "brew": {"count": 11, "ml": 1000},
        })
        self.client.get_machines = AsyncMock(return_value=[m_done_prompt])
        await self.coordinator._async_update_data()

        # No double deduction! Level stays 750ml, stage is done
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 750.0)
        self.assertEqual(self.coordinator.live_telemetry["M_123"].stage, "done")
        self.assertFalse(self.coordinator.live_telemetry["M_123"].is_brewing)

        # Poll 3: flow meter updates with true dispensed volume (1068 ml -> 68 ml dispensed)
        m_flow_update = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "NORMAL",
            "brewCount": 11,
            "status": "READY",
            "brew": {"count": 11, "ml": 1068},
        })
        self.client.get_machines = AsyncMock(return_value=[m_flow_update])
        await self.coordinator._async_update_data()

        # Reconciles: 750 + (50 assumed - 68 actual) = 732 ml
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 732.0)
        self.assertEqual(self.coordinator.live_telemetry["M_123"].water_output, 68.0)
        self.assertEqual(self.coordinator.live_telemetry["M_123"].stage, "done")

    async def test_live_espresso_brew_sticky_telemetry_and_lifetime_water(self):
        """Test live espresso brew updates dispensed water, preserves telemetry, and increments lifetime water."""
        self.coordinator.set_estimated_water_level("M_123", 850.0)
        self.coordinator.set_lifetime_water_ml("M_123", 1000.0)

        # 1. Active espresso brew (bypass 0, mass 36.5)
        t_active = MorningLiveBrewTelemetry(
            stage="brewing",
            is_brewing=True,
            water_output=36.5,
            mass_output=36.5,
            temperature=92,
        )
        self.coordinator.handle_live_brew_update("M_123", t_active)
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 813.5)

        # 2. Brew completes
        t_done = MorningLiveBrewTelemetry(
            stage="done",
            is_brewing=False,
            water_output=36.5,
            mass_output=36.5,
            temperature=92,
        )
        self.coordinator.handle_live_brew_update("M_123", t_done)
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 813.5)
        self.assertEqual(self.coordinator.get_lifetime_water_ml("M_123"), 1036.5)
        self.assertEqual(self.coordinator.live_telemetry["M_123"].water_output, 36.5)
        self.assertEqual(self.coordinator.live_telemetry["M_123"].mass_output, 36.5)

        # 3. REST polling runs and sees brew_count incremented
        self.coordinator._previous_brew_counts["M_123"] = 100
        self.coordinator._previous_water_levels["M_123"] = "NORMAL"
        m_poll = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "NORMAL",
            "brewCount": 101,
            "status": "ECO",
        })
        self.client.get_machines = AsyncMock(return_value=[m_poll])
        await self.coordinator._async_update_data()

        # Telemetry should NOT be overwritten by fallback 50.0 ml
        self.assertEqual(self.coordinator.live_telemetry["M_123"].water_output, 36.5)
        self.assertEqual(self.coordinator.live_telemetry["M_123"].mass_output, 36.5)
        self.assertEqual(self.coordinator.live_telemetry["M_123"].stage, "done")
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 813.5)
        self.assertEqual(self.coordinator.get_lifetime_water_ml("M_123"), 1036.5)

    async def test_purge_slosh_does_not_falsely_reset_water_level(self):
        """Test transient LOW water sensor during purge does not falsely clamp to 0 or refill to full."""
        self.coordinator.set_estimated_water_level("M_123", 500.0)
        self.coordinator._previous_brew_counts["M_123"] = 10
        self.coordinator._previous_water_levels["M_123"] = "NORMAL"
        self.coordinator._previous_total_water["M_123"] = 1000
        self.coordinator._previous_statuses["M_123"] = "READY"

        # 1. Machine enters PURGE with transient LOW sensor due to pump vibration/slosh
        m_slosh = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "LOW",
            "brewCount": 10,
            "status": "PURGE",
            "brew": {"count": 10, "ml": 1000},
        })
        self.client.get_machines = AsyncMock(return_value=[m_slosh])
        await self.coordinator._async_update_data()

        # Water level should NOT be clamped to 0.0 because machine is running
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 500.0)
        # _previous_water_levels should NOT be recorded as LOW
        self.assertEqual(self.coordinator._previous_water_levels["M_123"], "NORMAL")

        # 2. Machine finishes PURGE and returns to READY, sensor returns to NORMAL
        m_done = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "NORMAL",
            "brewCount": 10,
            "status": "READY",
            "brew": {"count": 10, "ml": 1000},
        })
        self.client.get_machines = AsyncMock(return_value=[m_done])
        await self.coordinator._async_update_data()

        # Decremented by 30ml purge, NOT reset to capacity (850ml)
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 470.0)
        self.assertEqual(self.coordinator.live_telemetry["M_123"].stage, "done")

    async def test_water_level_restored_from_hass_states_on_startup(self):
        """Test water level is restored from existing entity state on coordinator initialization."""
        coord = MorningDataUpdateCoordinator(
            self.hass, self.client, self.entry, update_interval=timedelta(seconds=30)
        )
        mock_state = MagicMock()
        mock_state.entity_id = "sensor.morning_m_123_water_tank_level"
        mock_state.state = "450.0"
        self.hass.states.async_all = MagicMock(return_value=[mock_state])

        m = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "NORMAL",
            "brewCount": 5,
            "status": "READY",
        })
        self.client.get_machines = AsyncMock(return_value=[m])
        await coord._async_update_data()

        self.assertEqual(coord.get_estimated_water_level("M_123"), 450.0)
        self.assertTrue(coord._water_level_seeded["M_123"])

    def test_live_brew_extraction_profile_recording(self):
        """Test active brewing records high-resolution extraction curve profile."""
        # 1. Brew starts
        t1 = MorningLiveBrewTelemetry(
            stage="brewing",
            is_brewing=True,
            water_output=0.0,
            mass_output=0.0,
            temperature=92,
        )
        self.coordinator.handle_live_brew_update("M_123", t1)
        prof = self.coordinator.get_brew_profile("M_123")
        self.assertEqual(len(prof), 1)
        self.assertEqual(prof[0]["water"], 0.0)

        # 2. Telemetry progresses
        t2 = MorningLiveBrewTelemetry(
            stage="brewing",
            is_brewing=True,
            water_output=15.0,
            mass_output=14.0,
            temperature=93,
        )
        self.coordinator.handle_live_brew_update("M_123", t2)
        prof = self.coordinator.get_brew_profile("M_123")
        self.assertGreaterEqual(len(prof), 2)
        self.assertEqual(prof[-1]["water"], 15.0)
        self.assertEqual(prof[-1]["mass"], 14.0)
        self.assertEqual(prof[-1]["temp"], 93)

        # 3. Brew completes
        t3 = MorningLiveBrewTelemetry(
            stage="done",
            is_brewing=False,
            water_output=36.0,
            mass_output=35.5,
            temperature=93,
        )
        self.coordinator.handle_live_brew_update("M_123", t3)
        final_prof = self.coordinator.get_brew_profile("M_123")
        self.assertGreaterEqual(len(final_prof), 2)
        self.assertEqual(final_prof[-1]["water"], 36.0)

        # 4. Passive shadow report to ready retains profile
        t4 = MorningLiveBrewTelemetry(
            stage="ready",
            is_brewing=False,
        )
        self.coordinator.handle_live_brew_update("M_123", t4)
        retained = self.coordinator.get_brew_profile("M_123")
        self.assertEqual(retained, final_prof)

    async def test_terminal_packet_guard_independent_temperature_preservation(self):
        """Test terminal packet with temperature=0 preserves peak temperature."""
        # Active brew packet with temperature 94
        t_active = MorningLiveBrewTelemetry(
            stage="brewing",
            is_brewing=True,
            water_output=50.0,
            mass_output=45.0,
            temperature=94,
        )
        self.coordinator.handle_live_brew_update("M_123", t_active)

        # Terminal packet with temperature=0 and non-zero water
        t_terminal = MorningLiveBrewTelemetry(
            stage="done",
            is_brewing=False,
            water_output=80.0,
            mass_output=75.0,
            temperature=0,  # Zeroed in terminal hardware packet
        )
        self.coordinator.handle_live_brew_update("M_123", t_terminal)

        final_telem = self.coordinator.live_telemetry["M_123"]
        self.assertEqual(final_telem.temperature, 94)
        self.assertEqual(final_telem.water_output, 80.0)
        self.assertEqual(final_telem.mass_output, 75.0)

    async def test_polling_heating_detection(self):
        """Test REST polling detects HEATING machine status."""
        self.coordinator._previous_statuses["M_123"] = "READY"
        m_heating = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "NORMAL",
            "brewCount": 10,
            "status": "HEATING",
            "temperature": 85,
        })
        self.client.get_machines = AsyncMock(return_value=[m_heating])
        await self.coordinator._async_update_data()

        telem = self.coordinator.live_telemetry.get("M_123")
        self.assertIsNotNone(telem)
        self.assertEqual(telem.stage, "heating")
        self.assertTrue(telem.is_brewing)
        self.assertEqual(telem.temperature, 85)

    async def test_polling_idle_clears_active_brewing(self):
        """Test REST polling transition to IDLE completes active brewing telemetry."""
        # Active brew was running
        self.coordinator.live_telemetry["M_123"] = MorningLiveBrewTelemetry(
            stage="brewing",
            is_brewing=True,
            water_output=60.0,
            mass_output=40.0,
            temperature=92,
        )
        self.coordinator._previous_statuses["M_123"] = "BREWING"

        # Machine now returns IDLE
        m_idle = MorningMachine.from_dict({
            "id": "M_123",
            "waterLevel": "NORMAL",
            "brewCount": 11,
            "status": "IDLE",
        })
        self.client.get_machines = AsyncMock(return_value=[m_idle])
        await self.coordinator._async_update_data()

        telem = self.coordinator.live_telemetry.get("M_123")
        self.assertIsNotNone(telem)
        self.assertEqual(telem.stage, "done")
        self.assertFalse(telem.is_brewing)
        self.assertEqual(telem.water_output, 60.0)
        self.assertEqual(telem.mass_output, 40.0)
        self.assertEqual(telem.temperature, 92)

    async def test_live_brew_cancel_resets_to_idle_and_reconciles_water(self):
        """Test that canceling a brew resets stage to idle and refunds unconsumed water."""
        mock_machine = MorningMachine.from_dict(
            {"id": "M_123", "name": "My Morning", "status": "IDLE", "waterLevel": "NORMAL", "brewCount": 10}
        )
        self.client.get_machines = AsyncMock(return_value=[mock_machine])
        await self.coordinator._async_update_data()
        initial_water = self.coordinator.get_estimated_water_level("M_123")

        # Start heating -> brewing via live IoT
        self.coordinator.handle_live_brew_update(
            "M_123",
            MorningLiveBrewTelemetry(
                stage="heating", temperature=90, water_output=0.0, mass_output=0.0, is_brewing=True
            ),
        )
        # Cancel before any water dispensed
        self.coordinator.handle_live_brew_update(
            "M_123",
            MorningLiveBrewTelemetry(
                stage="cancel", temperature=90, water_output=0.0, mass_output=0.0, is_brewing=False
            ),
        )

        telem = self.coordinator.live_telemetry["M_123"]
        self.assertEqual(telem.stage, "idle")
        self.assertFalse(telem.is_brewing)
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), initial_water)

    async def test_polling_brew_cancel_refunds_fallback_volume_and_resets_idle(self):
        """Test that a polling BREWING -> IDLE transition without brew count/water delta refunds fallback."""
        mock_machine = MorningMachine.from_dict(
            {"id": "M_123", "name": "My Morning", "status": "IDLE", "waterLevel": "NORMAL", "brewCount": 10}
        )
        self.client.get_machines = AsyncMock(return_value=[mock_machine])
        await self.coordinator._async_update_data()
        initial_water = self.coordinator.get_estimated_water_level("M_123")

        # Poll 1: Machine enters BREWING (offline fallback deducts 50 mL)
        brewing_machine = MorningMachine.from_dict(
            {"id": "M_123", "name": "My Morning", "status": "BREWING", "waterLevel": "NORMAL", "brewCount": 10}
        )
        self.client.get_machines = AsyncMock(return_value=[brewing_machine])
        await self.coordinator._async_update_data()
        self.assertEqual(self.coordinator.live_telemetry["M_123"].stage, "brewing")
        self.assertTrue(self.coordinator.live_telemetry["M_123"].is_brewing)
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), initial_water - 50.0)

        # Poll 2: User canceled brew -> machine returns to IDLE without brew_count or total_water_ml increment
        self.client.get_machines = AsyncMock(return_value=[mock_machine])
        await self.coordinator._async_update_data()
        telem = self.coordinator.live_telemetry["M_123"]
        self.assertEqual(telem.stage, "idle")
        self.assertFalse(telem.is_brewing)
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), initial_water)

    async def test_shadow_enrichment_and_physical_brew_progression(self):
        """Test Thing Shadow enrichment and 1s shadow-tracked physical brew progression."""
        m_initial = MorningMachine.from_dict(
            {"id": "M_123", "name": "My Morning", "status": "ECO", "waterLevel": "NORMAL", "brewCount": 10}
        )
        mock_iot = MagicMock()
        mock_iot.async_get_thing_shadow = AsyncMock(
            return_value={
                "state": {
                    "reported": {
                        "settings": {
                            "status": "ECO",
                            "waterLevel": "NORMAL",
                            "brew": {"count": 10, "ml": 140674},
                            "stm32Version": "1.0.4",
                            "pumpFlowrate": {"K1": 1.1, "P1": 2.75},
                        }
                    }
                }
            }
        )
        self.coordinator.iot_listener = mock_iot
        self.client.get_machines = AsyncMock(return_value=[m_initial])

        data = await self.coordinator._async_update_data()
        self.assertEqual(data["M_123"].total_water_ml, 140674)
        self.assertEqual(data["M_123"].stm32_version, "1.0.4")
        self.assertEqual(data["M_123"].pump_flow_rate_p1, 2.75)
        self.coordinator.data = data

        # 1. Physical dial triggers HEATING via Thing Shadow
        self.coordinator.handle_shadow_update(
            "M_123",
            {
                "state": {
                    "reported": {
                        "settings": {
                            "status": "HEATING",
                            "waterLevel": "NORMAL",
                            "brew": {"count": 10, "ml": 140674},
                        }
                    }
                }
            },
        )
        telem = self.coordinator.live_telemetry["M_123"]
        self.assertEqual(telem.stage, "heating")
        self.assertTrue(telem.is_brewing)
        self.assertEqual(telem.stages_seen, ["heating"])
        self.assertEqual(telem.source, "shadow")

        # 2. Physical dial enters BREWING (skipping blooming)
        self.coordinator.handle_shadow_update(
            "M_123",
            {
                "state": {
                    "reported": {
                        "settings": {
                            "status": "BREWING",
                            "waterLevel": "NORMAL",
                            "brew": {"count": 10, "ml": 140674},
                        }
                    }
                }
            },
        )
        telem = self.coordinator.live_telemetry["M_123"]
        self.assertEqual(telem.stage, "brewing")
        self.assertTrue(telem.is_brewing)
        self.assertEqual(telem.stages_seen, ["heating", "brewing"])
        self.assertNotIn("blooming", telem.stages_seen)
        self.assertGreaterEqual(len(self.coordinator.get_brew_profile("M_123")), 2)

        # 3. Physical dial completes brew -> READY with brew.count=11 and brew.ml=140716 (+42 mL)
        self.coordinator.handle_shadow_update(
            "M_123",
            {
                "state": {
                    "reported": {
                        "settings": {
                            "status": "READY",
                            "waterLevel": "NORMAL",
                            "brew": {"count": 11, "ml": 140716},
                        }
                    }
                }
            },
        )
        telem = self.coordinator.live_telemetry["M_123"]
        self.assertEqual(telem.stage, "done")
        self.assertFalse(telem.is_brewing)
        self.assertEqual(telem.water_output, 42.0)
        self.assertEqual(telem.mass_output, 42.0)
        self.assertEqual(telem.stages_seen, ["heating", "brewing", "done"])
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 850.0 - 42.0)
        final_prof = self.coordinator.get_brew_profile("M_123")
        self.assertGreaterEqual(len(final_prof), 2)
        self.assertEqual(final_prof[-1]["water"], 42.0)

        # Duplicate DONE packet arriving within 10s must not wipe stages_seen or profile
        self.coordinator.handle_live_brew_update(
            "M_123",
            MorningLiveBrewTelemetry(
                stage="done",
                is_brewing=False,
                water_output=42.0,
                mass_output=42.0,
                temperature=93,
                source="mqtt",
            ),
        )
        self.assertEqual(
            self.coordinator.live_telemetry["M_123"].stages_seen,
            ["heating", "brewing", "done"],
        )

    async def test_shadow_physical_brew_cancel_resets_to_idle(self):
        """Test physical brew canceled via Thing Shadow refunds water and resets to idle."""
        m_initial = MorningMachine.from_dict(
            {"id": "M_123", "name": "My Morning", "status": "ECO", "waterLevel": "NORMAL", "brewCount": 10}
        )
        self.client.get_machines = AsyncMock(return_value=[m_initial])
        self.coordinator.data = await self.coordinator._async_update_data()
        self.coordinator._previous_total_water["M_123"] = 140674

        # Start physical BREWING
        self.coordinator.handle_shadow_update(
            "M_123",
            {
                "state": {
                    "reported": {
                        "settings": {
                            "status": "BREWING",
                            "waterLevel": "NORMAL",
                            "brew": {"count": 10, "ml": 140674},
                        }
                    }
                }
            },
        )
        self.assertTrue(self.coordinator.live_telemetry["M_123"].is_brewing)

        # User cancels on physical dial -> status returns to ECO with no brew.count or brew.ml change
        self.coordinator.handle_shadow_update(
            "M_123",
            {
                "state": {
                    "reported": {
                        "settings": {
                            "status": "ECO",
                            "waterLevel": "NORMAL",
                            "brew": {"count": 10, "ml": 140674},
                        }
                    }
                }
            },
        )
        telem = self.coordinator.live_telemetry["M_123"]
        self.assertEqual(telem.stage, "idle")
        self.assertFalse(telem.is_brewing)
        self.assertEqual(self.coordinator.get_estimated_water_level("M_123"), 850.0)

    def test_recipe_catalog_dual_keys_and_defaults(self):
        """Test that get_recipe_catalog returns dual key aliases and non-empty defaults."""
        catalog = self.coordinator.get_recipe_catalog("M_123")

        # Verify dual keys exist and point to non-empty lists
        self.assertIn("favorite_profiles", catalog)
        self.assertIn("favorites", catalog)
        self.assertEqual(catalog["favorite_profiles"], catalog["favorites"])

        self.assertIn("recent_profiles", catalog)
        self.assertIn("recents", catalog)
        self.assertEqual(catalog["recent_profiles"], catalog["recents"])

        self.assertIn("machine_profiles", catalog)
        self.assertIn("machine", catalog)
        self.assertEqual(catalog["machine_profiles"], catalog["machine"])
        self.assertGreater(len(catalog["machine"]), 0)

        self.assertIn("quick_profiles", catalog)
        self.assertIn("quick", catalog)
        self.assertEqual(catalog["quick_profiles"], catalog["quick"])
        self.assertGreater(len(catalog["quick"]), 0)

        # Verify machine recipes include Americano and Bloom & Brew
        names = [p["name"] for p in catalog["machine"]]
        self.assertIn("Classic Espresso", names)
        self.assertIn("Bloom & Brew", names)
        self.assertIn("Americano", names)


if __name__ == "__main__":
    unittest.main()
