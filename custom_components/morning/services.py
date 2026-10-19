"""Custom services for the Morning Coffee Machine integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .client import MorningClient
from .const import (
    DOMAIN,
    SERVICE_CHECK_UPDATES,
    SERVICE_RESET_MACHINE,
    SERVICE_SET_STANDBY_TIMEOUT,
)
from .coordinator import MorningDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

ATTR_DEVICE_ID = "device_id"
ATTR_MACHINE_ID = "machine_id"
ATTR_TIMEOUT = "timeout"

SET_STANDBY_TIMEOUT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_DEVICE_ID): cv.string,
        vol.Optional(ATTR_MACHINE_ID): cv.string,
        vol.Required(ATTR_TIMEOUT): vol.All(vol.Coerce(int), vol.Range(min=300, max=7200)),
    }
)

MACHINE_ACTION_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_DEVICE_ID): cv.string,
        vol.Optional(ATTR_MACHINE_ID): cv.string,
    }
)


def _get_machine_id(hass: HomeAssistant, call: ServiceCall) -> str | None:
    """Resolve machine_id from direct argument or device_id."""
    if ATTR_MACHINE_ID in call.data:
        return str(call.data[ATTR_MACHINE_ID])

    if ATTR_DEVICE_ID in call.data:
        device_reg = dr.async_get(hass)
        device_entry = device_reg.async_get(call.data[ATTR_DEVICE_ID])
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


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Morning services."""
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_SET_STANDBY_TIMEOUT)
        hass.services.async_remove(DOMAIN, SERVICE_RESET_MACHINE)
        hass.services.async_remove(DOMAIN, SERVICE_CHECK_UPDATES)
