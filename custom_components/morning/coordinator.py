"""DataUpdateCoordinator for the Morning Coffee Machine integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import MorningAuthError, MorningClient, MorningConnectionError, MorningError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ID_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRES_AT,
    CONF_USER_ID,
    DOMAIN,
)
from .models import MorningMachine

_LOGGER = logging.getLogger(__name__)


class MorningDataUpdateCoordinator(DataUpdateCoordinator[dict[str, MorningMachine]]):
    """Class to manage fetching Morning machine data from cloud API."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: MorningClient,
        entry: ConfigEntry,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=update_interval,
        )
        self.client = client
        self.config_entry = entry

    async def _async_update_data(self) -> dict[str, MorningMachine]:
        """Fetch latest telemetry and status for all user machines."""
        try:
            machines = await self.client.get_machines()

            # If tokens were refreshed during requests, persist them to config entry
            if self.client.auth_session:
                current_tokens = self.client.auth_session
                if (
                    self.config_entry.data.get(CONF_ACCESS_TOKEN) != current_tokens.access_token
                    or self.config_entry.data.get(CONF_ID_TOKEN) != current_tokens.id_token
                ):
                    _LOGGER.debug("Persisting newly refreshed tokens to config entry")
                    new_data = dict(self.config_entry.data)
                    new_data.update(
                        {
                            CONF_ACCESS_TOKEN: current_tokens.access_token,
                            CONF_ID_TOKEN: current_tokens.id_token,
                            CONF_REFRESH_TOKEN: current_tokens.refresh_token,
                            CONF_TOKEN_EXPIRES_AT: current_tokens.expires_at,
                            CONF_USER_ID: current_tokens.user_id,
                        }
                    )
                    self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)

            return {machine.id: machine for machine in machines}

        except MorningAuthError as err:
            _LOGGER.error("Authentication expired or invalid for Morning account: %s", err)
            raise ConfigEntryAuthFailed(err) from err
        except MorningConnectionError as err:
            _LOGGER.warning("Connection failure while updating Morning machine data: %s", err)
            raise UpdateFailed(err) from err
        except MorningError as err:
            _LOGGER.error("Error communicating with Morning API: %s", err)
            raise UpdateFailed(err) from err
