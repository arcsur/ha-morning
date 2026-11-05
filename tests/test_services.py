"""Unit tests for Morning custom services."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from custom_components.morning.const import (
    ATTR_AMOUNT_ML,
    DOMAIN,
    SERVICE_BREW_RECIPE,
    SERVICE_CANCEL_BREW,
    SERVICE_CHECK_UPDATES,
    SERVICE_RECORD_PURGE,
    SERVICE_REFILL_WATER,
    SERVICE_RESET_MACHINE,
    SERVICE_SAVE_PROFILE,
    SERVICE_SEARCH_RECIPES,
    SERVICE_SET_STANDBY_TIMEOUT,
    SERVICE_TOGGLE_FAVORITE,
)
from custom_components.morning.coordinator import MorningDataUpdateCoordinator
from custom_components.morning.models import MorningMachine, MorningRecipe
from custom_components.morning.services import async_setup_services, async_unload_services


class TestMorningServices(unittest.IsolatedAsyncioTestCase):
    """Test custom service calls."""

    def setUp(self):
        """Set up test fixtures."""
        self.hass = MagicMock()
        self.registered_services = {}

        def mock_has_service(domain, service):
            return service in self.registered_services

        def mock_register(domain, service, handler, schema=None, **kwargs):
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
        self.coordinator.client.search_recipes = AsyncMock(
            return_value=[MorningRecipe(name="Onyx Espresso", temperature=93, mass_output=38)]
        )
        self.coordinator.async_request_refresh = AsyncMock()
        self.coordinator.async_brew_recipe = AsyncMock()
        self.coordinator.async_cancel_brew = AsyncMock()
        self.coordinator.async_save_profile = AsyncMock(
            return_value=MorningRecipe(name="Saved Test", temperature=94, mass_output=40)
        )
        self.coordinator.async_toggle_favorite = AsyncMock(return_value=True)
        self.coordinator.get_recipe_catalog = MagicMock(
            return_value={
                "quick_profiles": [{"id": 1, "name": "Catalog Recipe", "temperature": 94, "mass_output": 40}]
            }
        )

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

        # 8. Test brew_recipe with custom params
        call = MagicMock()
        call.data = {"machine_id": "M_123", "name": "Espresso Shot", "temperature": 95, "mass_output": 36}
        await self.registered_services[SERVICE_BREW_RECIPE](call)
        self.coordinator.async_brew_recipe.assert_called_once()
        brewed_recipe = self.coordinator.async_brew_recipe.call_args[0][1]
        self.assertEqual(brewed_recipe.name, "Espresso Shot")
        self.assertEqual(brewed_recipe.temperature, 95)
        self.assertEqual(brewed_recipe.mass_output, 36)

        # 9. Test brew_recipe recalling catalog profile
        call = MagicMock()
        call.data = {"machine_id": "M_123", "profile_id": 1}
        await self.registered_services[SERVICE_BREW_RECIPE](call)
        self.assertEqual(self.coordinator.async_brew_recipe.call_count, 2)

        # 10. Test cancel_brew
        call = MagicMock()
        call.data = {"machine_id": "M_123"}
        await self.registered_services[SERVICE_CANCEL_BREW](call)
        self.coordinator.async_cancel_brew.assert_called_once_with("M_123")

        # 11. Test search_recipes
        call = MagicMock()
        call.data = {"query": "Onyx"}
        search_res = await self.registered_services[SERVICE_SEARCH_RECIPES](call)
        self.assertIn("recipes", search_res)
        self.assertEqual(len(search_res["recipes"]), 1)
        self.assertEqual(search_res["recipes"][0]["name"], "Onyx Espresso")

        # 12. Test save_profile
        call = MagicMock()
        call.data = {"name": "Saved Test", "temperature": 94, "mass_output": 40}
        save_res = await self.registered_services[SERVICE_SAVE_PROFILE](call)
        self.coordinator.async_save_profile.assert_called_once()
        self.assertIn("profile", save_res)

        # 13. Test toggle_favorite
        call = MagicMock()
        call.data = {"profile_id": 123}
        fav_res = await self.registered_services[SERVICE_TOGGLE_FAVORITE](call)
        self.coordinator.async_toggle_favorite.assert_called_once_with(123, None)
        self.assertTrue(fav_res["is_favorite"])

    async def test_service_schemas_allow_entity_id(self):
        """Test that voluptuous schemas accept entity_id without extra key errors."""
        from custom_components.morning.services import (
            BREW_RECIPE_SCHEMA,
            CANCEL_BREW_SCHEMA,
            SAVE_PROFILE_SCHEMA,
            TOGGLE_FAVORITE_SCHEMA,
        )

        # toggle_favorite schema allows entity_id
        valid_fav = TOGGLE_FAVORITE_SCHEMA(
            {"entity_id": "sensor.dagusmorning_status", "profile_id": "fav-1", "recipe": {"name": "Test"}}
        )
        self.assertEqual(valid_fav["entity_id"], ["sensor.dagusmorning_status"])

        # save_profile schema allows entity_id
        valid_save = SAVE_PROFILE_SCHEMA(
            {"entity_id": "sensor.dagusmorning_status", "name": "Custom Profile", "temperature": 94}
        )
        self.assertEqual(valid_save["entity_id"], ["sensor.dagusmorning_status"])

        # brew_recipe schema allows entity_id
        valid_brew = BREW_RECIPE_SCHEMA(
            {"entity_id": "sensor.dagusmorning_status", "name": "Espresso", "temperature": 94, "mass_output": 36}
        )
        self.assertEqual(valid_brew["entity_id"], ["sensor.dagusmorning_status"])

        # cancel_brew schema allows entity_id
        valid_cancel = CANCEL_BREW_SCHEMA({"entity_id": "sensor.dagusmorning_status"})
        self.assertEqual(valid_cancel["entity_id"], ["sensor.dagusmorning_status"])

    async def test_unload_services(self):
        """Test unloading services."""
        await async_setup_services(self.hass)
        self.hass.data[DOMAIN] = {}  # simulate all entries unloaded
        await async_unload_services(self.hass)
        self.assertNotIn(SERVICE_SET_STANDBY_TIMEOUT, self.registered_services)
        self.assertNotIn(SERVICE_RECORD_PURGE, self.registered_services)
        self.assertNotIn(SERVICE_REFILL_WATER, self.registered_services)
        self.assertNotIn(SERVICE_BREW_RECIPE, self.registered_services)
        self.assertNotIn(SERVICE_CANCEL_BREW, self.registered_services)
        self.assertNotIn(SERVICE_SEARCH_RECIPES, self.registered_services)
        self.assertNotIn(SERVICE_SAVE_PROFILE, self.registered_services)
        self.assertNotIn(SERVICE_TOGGLE_FAVORITE, self.registered_services)


if __name__ == "__main__":
    unittest.main()
