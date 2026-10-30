"""Unit tests for Morning custom services."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from custom_components.morning.const import (
    ATTR_AMOUNT_ML,
    DOMAIN,
    SERVICE_CHECK_UPDATES,
    SERVICE_RECORD_PURGE,
    SERVICE_REFILL_WATER,
    SERVICE_RESET_MACHINE,
    SERVICE_SET_STANDBY_TIMEOUT,
)
from custom_components.morning.coordinator import MorningDataUpdateCoordinator
from custom_components.morning.models import MorningMachine
from custom_components.morning.services import async_setup_services, async_unload_services


class TestMorningServices(unittest.IsolatedAsyncioTestCase):
    """Test custom service calls."""

    def setUp(self):
        """Set up test fixtures."""
        self.hass = MagicMock()
        self.registered_services = {}

        def mock_has_service(domain, service):
            return service in self.registered_services

        def mock_register(domain, service, handler, schema=None):
            self.registered_services[service] = handler

        def mock_remove(domain, service):
            self.registered_services.pop(service, None)

        self.hass.services.has_service.side_effect = mock_has_service
        self.hass.services.async_register.side_effect = mock_register
        self.hass.services.async_remove.side_effect = mock_remove

        self.coordinator = MagicMock(spec=MorningDataUpdateCoordinator)
        self.coordinator.data = {"M_123": MorningMachine.from_dict({"id": "M_123"})}
        self.coordinator.client = MagicMock()
        self.coordinator.client.set_standby_timeout = AsyncMock()
        self.coordinator.client.reset_machine = AsyncMock()
        self.coordinator.client.check_updates = AsyncMock()
        self.coordinator.async_request_refresh = AsyncMock()

        self.hass.data = {
            DOMAIN: {
                "test_entry": {
                    "coordinator": self.coordinator,
                    "client": self.coordinator.client,
                }
            }
        }

    async def test_setup_and_call_services(self):
        """Test registering services and invoking each service."""
        await async_setup_services(self.hass)
        self.assertIn(SERVICE_SET_STANDBY_TIMEOUT, self.registered_services)
        self.assertIn(SERVICE_RESET_MACHINE, self.registered_services)
        self.assertIn(SERVICE_CHECK_UPDATES, self.registered_services)
        self.assertIn(SERVICE_REFILL_WATER, self.registered_services)
        self.assertIn(SERVICE_RECORD_PURGE, self.registered_services)

        # 1. Test set_standby_timeout
        call = MagicMock()
        call.data = {"machine_id": "M_123", "timeout": 600}
        await self.registered_services[SERVICE_SET_STANDBY_TIMEOUT](call)
        self.coordinator.client.set_standby_timeout.assert_called_once_with("M_123", 600)

        # 2. Test reset_machine
        call = MagicMock()
        call.data = {"machine_id": "M_123"}
        await self.registered_services[SERVICE_RESET_MACHINE](call)
        self.coordinator.client.reset_machine.assert_called_once()

        # 3. Test check_updates
        call = MagicMock()
        call.data = {"machine_id": "M_123"}
        await self.registered_services[SERVICE_CHECK_UPDATES](call)
        self.coordinator.client.check_updates.assert_called_once()

        # 4. Test refill_water full
        call = MagicMock()
        call.data = {"machine_id": "M_123"}
        await self.registered_services[SERVICE_REFILL_WATER](call)
        self.coordinator.refill_tank.assert_called_once_with("M_123", amount_ml=None)

        # 5. Test refill_water specific amount
        call = MagicMock()
        call.data = {"machine_id": "M_123", ATTR_AMOUNT_ML: 250}
        await self.registered_services[SERVICE_REFILL_WATER](call)
        self.coordinator.refill_tank.assert_called_with("M_123", amount_ml=250)

        # 6. Test record_purge default amount
        call = MagicMock()
        call.data = {"machine_id": "M_123"}
        await self.registered_services[SERVICE_RECORD_PURGE](call)
        self.coordinator.record_purge.assert_called_once_with("M_123", amount_ml=None)

        # 7. Test record_purge explicit amount
        call = MagicMock()
        call.data = {"machine_id": "M_123", ATTR_AMOUNT_ML: 40}
        await self.registered_services[SERVICE_RECORD_PURGE](call)
        self.coordinator.record_purge.assert_called_with("M_123", amount_ml=40)

    async def test_unload_services(self):
        """Test unloading services."""
        await async_setup_services(self.hass)
        self.hass.data[DOMAIN] = {}  # simulate all entries unloaded
        await async_unload_services(self.hass)
        self.assertNotIn(SERVICE_SET_STANDBY_TIMEOUT, self.registered_services)
        self.assertNotIn(SERVICE_RECORD_PURGE, self.registered_services)
        self.assertNotIn(SERVICE_REFILL_WATER, self.registered_services)


if __name__ == "__main__":
    unittest.main()
