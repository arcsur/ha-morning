"""Support for Morning Coffee Machine integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import MorningClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EMAIL,
    CONF_ID_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN_EXPIRES_AT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import MorningDataUpdateCoordinator
from .models import MorningAuthSession
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Morning Coffee Machine from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Restore authentication session from stored tokens
    auth_session = MorningAuthSession(
        access_token=entry.data[CONF_ACCESS_TOKEN],
        id_token=entry.data[CONF_ID_TOKEN],
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        expires_at=entry.data[CONF_TOKEN_EXPIRES_AT],
        email=entry.data[CONF_EMAIL],
    )

    session = async_get_clientsession(hass)
    client = MorningClient(session=session, auth_session=auth_session)

    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    coordinator = MorningDataUpdateCoordinator(
        hass=hass,
        client=client,
        entry=entry,
        update_interval=timedelta(seconds=scan_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_services(hass)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info(
        "Successfully set up Morning Coffee Machine integration for %s",
        entry.data[CONF_EMAIL],
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Morning config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            await async_unload_services(hass)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload Morning config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
