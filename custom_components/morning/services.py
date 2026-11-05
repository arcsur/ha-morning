"""Custom services for the Morning Coffee Machine integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .client import MorningClient
from .const import (
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
from .coordinator import MorningDataUpdateCoordinator
from .models import MorningRecipe

_LOGGER = logging.getLogger(__name__)

ATTR_DEVICE_ID = "device_id"
ATTR_MACHINE_ID = "machine_id"
ATTR_TIMEOUT = "timeout"

BASE_TARGET_SCHEMA: dict[Any, Any] = {
    vol.Optional(ATTR_ENTITY_ID): cv.entity_ids_or_uuids,
    vol.Optional(ATTR_DEVICE_ID): cv.string,
    vol.Optional(ATTR_MACHINE_ID): cv.string,
}

SET_STANDBY_TIMEOUT_SCHEMA = vol.Schema(
    {
        **BASE_TARGET_SCHEMA,
        vol.Required(ATTR_TIMEOUT): vol.All(vol.Coerce(int), vol.Range(min=300, max=7200)),
    }
)

MACHINE_ACTION_SCHEMA = vol.Schema(
    {
        **BASE_TARGET_SCHEMA,
    }
)

REFILL_WATER_SCHEMA = vol.Schema(
    {
        **BASE_TARGET_SCHEMA,
        vol.Optional(ATTR_AMOUNT_ML): vol.All(vol.Coerce(int), vol.Range(min=1, max=3000)),
    }
)

RECORD_PURGE_SCHEMA = vol.Schema(
    {
        **BASE_TARGET_SCHEMA,
        vol.Optional(ATTR_AMOUNT_ML): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
    }
)

BREW_RECIPE_SCHEMA = vol.Schema(
    {
        **BASE_TARGET_SCHEMA,
        vol.Optional("profile_id"): vol.Any(cv.string, vol.Coerce(int)),
        vol.Optional("name"): cv.string,
        vol.Optional("temperature"): vol.All(vol.Coerce(int), vol.Range(min=65, max=100)),
        vol.Optional("mass_output"): vol.All(vol.Coerce(int), vol.Range(min=10, max=250)),
        vol.Optional("water_output"): vol.All(vol.Coerce(int), vol.Range(min=0, max=300)),
        vol.Optional("bloom_duration"): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
        vol.Optional("stages"): vol.All(cv.ensure_list, [dict]),
        vol.Optional("stage1_pressure"): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
        vol.Optional("stage2_weight"): vol.All(vol.Coerce(int), vol.Range(min=0, max=250)),
        vol.Optional("stage2_pressure"): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
        vol.Optional("stage3_weight"): vol.All(vol.Coerce(int), vol.Range(min=0, max=250)),
        vol.Optional("stage3_pressure"): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
    }
)

CANCEL_BREW_SCHEMA = vol.Schema(
    {
        **BASE_TARGET_SCHEMA,
    }
)

SEARCH_RECIPES_SCHEMA = vol.Schema(
    {
        **BASE_TARGET_SCHEMA,
        vol.Required("query"): cv.string,
        vol.Optional("page_size"): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
    }
)

SAVE_PROFILE_SCHEMA = vol.Schema(
    {
        **BASE_TARGET_SCHEMA,
        vol.Required("name"): cv.string,
        vol.Optional("temperature"): vol.All(vol.Coerce(int), vol.Range(min=65, max=100)),
        vol.Optional("mass_output"): vol.All(vol.Coerce(int), vol.Range(min=10, max=250)),
        vol.Optional("water_output"): vol.All(vol.Coerce(int), vol.Range(min=0, max=300)),
        vol.Optional("bloom_duration"): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
        vol.Optional("stages"): vol.All(cv.ensure_list, [dict]),
        vol.Optional("is_favorite"): cv.boolean,
    }
)

TOGGLE_FAVORITE_SCHEMA = vol.Schema(
    {
        **BASE_TARGET_SCHEMA,
        vol.Required("profile_id"): vol.Any(cv.string, vol.Coerce(int)),
        vol.Optional("is_favorite"): cv.boolean,
        vol.Optional("recipe"): dict,
    }
)


def _get_machine_id(hass: HomeAssistant, call: ServiceCall) -> str | None:
    """Resolve machine_id from direct argument, device_id, or entity_id."""
    if ATTR_MACHINE_ID in call.data:
        return str(call.data[ATTR_MACHINE_ID])

    device_id = call.data.get(ATTR_DEVICE_ID)

    if not device_id and ATTR_ENTITY_ID in call.data:
        ent_reg = er.async_get(hass)
        raw_entities = call.data[ATTR_ENTITY_ID]
        entity_ids = [raw_entities] if isinstance(raw_entities, str) else list(raw_entities)
        for entity_id in entity_ids:
            entity_entry = ent_reg.async_get(str(entity_id))
            if entity_entry and entity_entry.device_id:
                device_id = entity_entry.device_id
                break

    if device_id:
        device_reg = dr.async_get(hass)
        device_entry = device_reg.async_get(device_id)
        if device_entry:
            for domain, identifier in device_entry.identifiers:
                if domain == DOMAIN:
                    return identifier

    return None


def _get_coordinator_for_machine(
    hass: HomeAssistant, machine_id: str | None
) -> tuple[MorningDataUpdateCoordinator, MorningClient] | None:
    """Find coordinator and client for given machine."""
    entries = hass.data.get(DOMAIN, {})
    for entry_id, data in entries.items():
        if isinstance(data, dict) and "coordinator" in data:
            coord: MorningDataUpdateCoordinator = data["coordinator"]
            if machine_id is None or (coord.data and machine_id in coord.data):
                return coord, data["client"]

    # Fallback to first available coordinator
    for entry_id, data in entries.items():
        if isinstance(data, dict) and "coordinator" in data:
            return data["coordinator"], data["client"]

    return None


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register Morning services."""

    async def handle_set_standby_timeout(call: ServiceCall) -> None:
        """Handle setting standby timeout."""
        machine_id = _get_machine_id(hass, call)
        timeout = call.data[ATTR_TIMEOUT]

        found = _get_coordinator_for_machine(hass, machine_id)
        if not found:
            _LOGGER.error("Cannot find Morning machine for service call")
            return

        coordinator, client = found
        target_id = machine_id or (next(iter(coordinator.data.keys())) if coordinator.data else None)
        if not target_id:
            _LOGGER.error("No target Morning machine identified")
            return

        _LOGGER.info("Setting standby timeout for %s to %s s", target_id, timeout)
        await client.set_standby_timeout(target_id, timeout)
        await coordinator.async_request_refresh()

    async def handle_reset_machine(call: ServiceCall) -> None:
        """Handle machine reset."""
        machine_id = _get_machine_id(hass, call)
        found = _get_coordinator_for_machine(hass, machine_id)
        if not found:
            _LOGGER.error("Cannot find Morning machine for reset service call")
            return

        coordinator, client = found
        _LOGGER.info("Sending reset command to machine")
        await client.reset_machine()
        await coordinator.async_request_refresh()

    async def handle_check_updates(call: ServiceCall) -> None:
        """Handle check firmware updates."""
        machine_id = _get_machine_id(hass, call)
        found = _get_coordinator_for_machine(hass, machine_id)
        if not found:
            _LOGGER.error("Cannot find Morning machine for check_updates service call")
            return

        coordinator, client = found
        target_id = machine_id or (next(iter(coordinator.data.keys())) if coordinator.data else None)
        machine = coordinator.data.get(target_id) if target_id and coordinator.data else None
        m_type = machine.type if machine else "COFFEE"

        _LOGGER.info("Checking firmware updates for %s", target_id or "COFFEE")
        await client.check_updates(machine_type=m_type)
        await coordinator.async_request_refresh()

    async def handle_refill_water(call: ServiceCall) -> None:
        """Handle refilling water tank."""
        machine_id = _get_machine_id(hass, call)
        amount_ml = call.data.get(ATTR_AMOUNT_ML)

        found = _get_coordinator_for_machine(hass, machine_id)
        if not found:
            _LOGGER.error("Cannot find Morning machine for refill_water service call")
            return

        coordinator, _ = found
        target_id = machine_id or (next(iter(coordinator.data.keys())) if coordinator.data else None)
        if not target_id:
            _LOGGER.error("No target Morning machine identified for refill")
            return

        _LOGGER.info("Refilling water tank for %s (amount: %s ml)", target_id, amount_ml or "full")
        coordinator.refill_tank(target_id, amount_ml=amount_ml)

    async def handle_record_purge(call: ServiceCall) -> None:
        """Handle recording a purge rinse."""
        machine_id = _get_machine_id(hass, call)
        amount_ml = call.data.get(ATTR_AMOUNT_ML)

        found = _get_coordinator_for_machine(hass, machine_id)
        if not found:
            _LOGGER.error("Cannot find Morning machine for record_purge service call")
            return

        coordinator, _ = found
        target_id = machine_id or (next(iter(coordinator.data.keys())) if coordinator.data else None)
        if not target_id:
            _LOGGER.error("No target Morning machine identified for purge")
            return

        _LOGGER.info("Recording purge rinse for %s (amount: %s ml)", target_id, amount_ml or "default")
        coordinator.record_purge(target_id, amount_ml=amount_ml)

    async def handle_brew_recipe(call: ServiceCall) -> None:
        """Handle initiating coffee extraction."""
        machine_id = _get_machine_id(hass, call)
        res = _get_coordinator_for_machine(hass, machine_id)
        if not res:
            _LOGGER.error("No coordinator found for Morning brew request")
            return
        coordinator, _ = res
        target_id = machine_id or (next(iter(coordinator.data.keys())) if coordinator.data else None)
        if not target_id:
            _LOGGER.error("No target Morning machine identified for brew")
            return

        # 1. Check if profile_id provided in catalog
        recipe: MorningRecipe | None = None
        profile_id = call.data.get("profile_id")
        if profile_id is not None:
            catalog = coordinator.get_recipe_catalog(target_id)
            all_profiles = (
                catalog.get("quick_profiles", [])
                + catalog.get("favorite_profiles", [])
                + catalog.get("recent_profiles", [])
                + catalog.get("machine_profiles", [])
                + catalog.get("custom_profiles", [])
            )
            for p in all_profiles:
                if str(p.get("id")) == str(profile_id) or p.get("name") == str(profile_id):
                    recipe = MorningRecipe.from_dict(p)
                    break

        # 2. Build or override recipe
        if recipe is None:
            recipe_dict = dict(call.data)
            recipe = MorningRecipe.from_dict(recipe_dict)
        else:
            if "name" in call.data:
                recipe.name = str(call.data["name"])
            if "temperature" in call.data:
                recipe.temperature = int(call.data["temperature"])
            if "mass_output" in call.data:
                recipe.mass_output = int(call.data["mass_output"])
            if "water_output" in call.data:
                recipe.water_output = int(call.data["water_output"])
            if "bloom_duration" in call.data:
                recipe.bloom_duration = int(call.data["bloom_duration"])

        # Check for stage overrides
        if any(
            k in call.data
            for k in (
                "stage1_pressure",
                "stage2_pressure",
                "stage3_pressure",
                "stage2_weight",
                "stage3_weight",
            )
        ):
            s1_p = int(call.data.get("stage1_pressure", recipe.stages[0]["pressure"] if len(recipe.stages) > 0 else 3))
            s2_p = int(call.data.get("stage2_pressure", recipe.stages[1]["pressure"] if len(recipe.stages) > 1 else 7))
            s3_p = int(call.data.get("stage3_pressure", recipe.stages[2]["pressure"] if len(recipe.stages) > 2 else 5))
            s2_w = int(call.data.get("stage2_weight", recipe.stages[1]["output"] if len(recipe.stages) > 1 else 5))
            s3_w = int(
                call.data.get(
                    "stage3_weight",
                    recipe.stages[2]["output"] if len(recipe.stages) > 2 else max(5, recipe.mass_output - 5),
                )
            )
            recipe.stages = [
                {"id": 0, "output": 0, "pressure": s1_p},
                {"id": 1, "output": s2_w, "pressure": s2_p},
                {"id": 2, "output": s3_w, "pressure": s3_p},
            ]

        _LOGGER.info(
            "Initiating brew on %s: %s (%d°C, %dg)",
            target_id,
            recipe.name,
            recipe.temperature,
            recipe.mass_output,
        )
        await coordinator.async_brew_recipe(target_id, recipe)

    async def handle_cancel_brew(call: ServiceCall) -> None:
        """Handle cancelling coffee extraction."""
        machine_id = _get_machine_id(hass, call)
        res = _get_coordinator_for_machine(hass, machine_id)
        if not res:
            _LOGGER.error("No coordinator found for Morning cancel brew request")
            return
        coordinator, _ = res
        target_id = machine_id or (next(iter(coordinator.data.keys())) if coordinator.data else None)
        if not target_id:
            _LOGGER.error("No target Morning machine identified for cancel brew")
            return

        _LOGGER.info("Cancelling brew on %s", target_id)
        await coordinator.async_cancel_brew(target_id)

    async def handle_search_recipes(call: ServiceCall) -> dict[str, Any]:
        """Handle searching Morning Cloud recipes."""
        res = _get_coordinator_for_machine(hass, None)
        if not res:
            return {"recipes": []}
        _, client = res
        query = str(call.data.get("query", "")).strip()
        page_size = int(call.data.get("page_size", 20))
        if not query:
            return {"recipes": []}

        recipes = await client.search_recipes(query, page_size=page_size)
        return {"recipes": [r.to_dict() for r in recipes]}

    async def handle_save_profile(call: ServiceCall) -> dict[str, Any]:
        """Handle saving a custom brew profile."""
        machine_id = _get_machine_id(hass, call)
        res = _get_coordinator_for_machine(hass, machine_id)
        if not res:
            return {}
        coordinator, _ = res
        recipe = await coordinator.async_save_profile(dict(call.data))
        return {"profile": recipe.to_dict()}

    async def handle_toggle_favorite(call: ServiceCall) -> dict[str, Any]:
        """Handle toggling favorite on a profile."""
        machine_id = _get_machine_id(hass, call)
        res = _get_coordinator_for_machine(hass, machine_id)
        if not res:
            return {"is_favorite": False}
        coordinator, _ = res
        profile_id = call.data["profile_id"]
        recipe_dict = call.data.get("recipe")
        is_fav = await coordinator.async_toggle_favorite(profile_id, recipe_dict)
        return {"is_favorite": is_fav}

    if not hass.services.has_service(DOMAIN, SERVICE_SET_STANDBY_TIMEOUT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_STANDBY_TIMEOUT,
            handle_set_standby_timeout,
            schema=SET_STANDBY_TIMEOUT_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_RESET_MACHINE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESET_MACHINE,
            handle_reset_machine,
            schema=MACHINE_ACTION_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_CHECK_UPDATES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CHECK_UPDATES,
            handle_check_updates,
            schema=MACHINE_ACTION_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_REFILL_WATER):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFILL_WATER,
            handle_refill_water,
            schema=REFILL_WATER_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_RECORD_PURGE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RECORD_PURGE,
            handle_record_purge,
            schema=RECORD_PURGE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_BREW_RECIPE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_BREW_RECIPE,
            handle_brew_recipe,
            schema=BREW_RECIPE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_CANCEL_BREW):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CANCEL_BREW,
            handle_cancel_brew,
            schema=CANCEL_BREW_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SEARCH_RECIPES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SEARCH_RECIPES,
            handle_search_recipes,
            schema=SEARCH_RECIPES_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SAVE_PROFILE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SAVE_PROFILE,
            handle_save_profile,
            schema=SAVE_PROFILE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_TOGGLE_FAVORITE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_TOGGLE_FAVORITE,
            handle_toggle_favorite,
            schema=TOGGLE_FAVORITE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Morning services."""
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_SET_STANDBY_TIMEOUT)
        hass.services.async_remove(DOMAIN, SERVICE_RESET_MACHINE)
        hass.services.async_remove(DOMAIN, SERVICE_CHECK_UPDATES)
        hass.services.async_remove(DOMAIN, SERVICE_REFILL_WATER)
        hass.services.async_remove(DOMAIN, SERVICE_RECORD_PURGE)
        hass.services.async_remove(DOMAIN, SERVICE_BREW_RECIPE)
        hass.services.async_remove(DOMAIN, SERVICE_CANCEL_BREW)
        hass.services.async_remove(DOMAIN, SERVICE_SEARCH_RECIPES)
        hass.services.async_remove(DOMAIN, SERVICE_SAVE_PROFILE)
        hass.services.async_remove(DOMAIN, SERVICE_TOGGLE_FAVORITE)
