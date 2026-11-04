"""Support for Morning Coffee Machine integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
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
    CONF_USER_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import MorningDataUpdateCoordinator
from .iot import MorningIotListener
from .models import MorningAuthSession
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Morning Coffee Machine component."""
    await _async_register_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Morning Coffee Machine from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    await _async_register_frontend(hass)

    # Restore authentication session from stored tokens
    auth_session = MorningAuthSession(
        access_token=entry.data[CONF_ACCESS_TOKEN],
        id_token=entry.data[CONF_ID_TOKEN],
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        expires_at=entry.data[CONF_TOKEN_EXPIRES_AT],
        email=entry.data[CONF_EMAIL],
        user_id=entry.data.get(CONF_USER_ID),
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

    iot_listener = MorningIotListener(
        coordinator=coordinator,
        client=client,
        session=session,
    )
    iot_listener.start()

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "iot_listener": iot_listener,
        "options": dict(entry.options),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_services(hass)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info(
        "Successfully set up Morning Coffee Machine integration for %s",
        entry.data[CONF_EMAIL],
    )
    return True


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register custom Lovelace card static path and inject script into frontend."""
    import shutil
    from pathlib import Path

    card_path = Path(__file__).parent / "frontend" / "morning-coffee-card.js"
    if not card_path.exists():
        return

    def _prepare_frontend_assets() -> str:
        # Also mirror card into <config>/www/morning-card/ so /local/morning-card/ is
        # served by HA's core HTTP component before custom integrations finish booting.
        if hasattr(hass, "config") and hasattr(hass.config, "path"):
            try:
                www_dir = Path(hass.config.path("www")) / "morning-card"
                www_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(card_path, www_dir / "morning-coffee-card.js")
            except Exception:
                pass

        manifest_path = Path(__file__).parent / "manifest.json"
        if manifest_path.exists():
            import json

            try:
                manifest = json.loads(manifest_path.read_text())
                return str(manifest.get("version", "1.4.4"))
            except Exception:
                pass
        return "1.4.4"

    version = await hass.async_add_executor_job(_prepare_frontend_assets)

    if hass.data.get("morning_frontend_registered"):
        return

    url = "/morning-card/morning-coffee-card.js"
    versioned_url = f"{url}?v={version}"

    # Register HTTP static route if HTTP component is active
    static_registered = False
    if hasattr(hass, "http") and hass.http:
        try:
            if hasattr(hass.http, "async_register_static_paths"):
                from homeassistant.components.http import StaticPathConfig

                await hass.http.async_register_static_paths(
                    [StaticPathConfig(url, str(card_path), cache_headers=False)]
                )
                static_registered = True
            elif hasattr(hass.http, "register_static_path"):
                hass.http.register_static_path(url, str(card_path), cache_headers=False)
                static_registered = True
        except Exception as err:
            _LOGGER.warning("Could not register static path for morning-coffee-card: %s", err)

    if not static_registered:
        return

    # Inject extra JS URL into frontend with cache-busting version parameter
    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, versioned_url)
        _LOGGER.debug("Injected %s into Lovelace frontend", versioned_url)
    except Exception as err:
        _LOGGER.debug("Could not add_extra_js_url for morning-coffee-card: %s", err)

    hass.data["morning_frontend_registered"] = True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Morning config entry."""
    hass.data.pop("morning_frontend_registered", None)
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if entry_data and "iot_listener" in entry_data:
        await entry_data["iot_listener"].stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            await async_unload_services(hass)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload Morning config entry only when options change (not on token refresh)."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if entry_data is not None:
        current_options = dict(entry.options)
        if entry_data.get("options") == current_options:
            return
        entry_data["options"] = current_options
    await hass.config_entries.async_reload(entry.entry_id)
