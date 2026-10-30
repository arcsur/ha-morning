"""DataUpdateCoordinator for the Morning Coffee Machine integration."""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import MorningAuthError, MorningClient, MorningConnectionError, MorningError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_FALLBACK_BREW_VOLUME,
    CONF_ID_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_TANK_CAPACITY,
    CONF_TOKEN_EXPIRES_AT,
    CONF_USER_ID,
    DEFAULT_FALLBACK_BREW_VOLUME,
    DEFAULT_TANK_CAPACITY,
    DOMAIN,
    WATER_LEVEL_LOW,
    WATER_LEVEL_NORMAL,
)
from .models import MorningLiveBrewTelemetry, MorningMachine

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

        # Water level estimation and live telemetry storage
        self.water_tank_levels: dict[str, float] = {}
        self.pre_brew_tank_levels: dict[str, float] = {}
        self.live_telemetry: dict[str, MorningLiveBrewTelemetry] = {}
        self._previous_brew_counts: dict[str, int] = {}
        self._previous_water_levels: dict[str, str] = {}
        self._pending_live_brew_accounted: dict[str, bool] = {}

    def get_tank_capacity(self, machine_id: str | None = None) -> int:
        """Return configured tank capacity in ml."""
        return int(
            self.config_entry.options.get(
                CONF_TANK_CAPACITY,
                self.config_entry.data.get(CONF_TANK_CAPACITY, DEFAULT_TANK_CAPACITY),
            )
        )

    def get_fallback_brew_volume(self, machine_id: str | None = None) -> int:
        """Return fallback brew volume in ml for polling delta calculation."""
        return int(
            self.config_entry.options.get(
                CONF_FALLBACK_BREW_VOLUME,
                self.config_entry.data.get(
                    CONF_FALLBACK_BREW_VOLUME, DEFAULT_FALLBACK_BREW_VOLUME
                ),
            )
        )

    def get_estimated_water_level(self, machine_id: str) -> float:
        """Return current estimated water level in ml."""
        if machine_id in self.water_tank_levels:
            return self.water_tank_levels[machine_id]
        capacity = float(self.get_tank_capacity(machine_id))
        self.water_tank_levels[machine_id] = capacity
        return capacity

    def set_estimated_water_level(self, machine_id: str, level: float) -> None:
        """Manually or restoratively set the estimated water level."""
        capacity = float(self.get_tank_capacity(machine_id))
        clamped = max(0.0, min(capacity, float(level)))
        self.water_tank_levels[machine_id] = clamped
        self.pre_brew_tank_levels[machine_id] = clamped

    def refill_tank(self, machine_id: str, amount_ml: int | None = None) -> None:
        """Refill water tank to capacity or by specific amount in ml."""
        capacity = float(self.get_tank_capacity(machine_id))
        if amount_ml is None:
            self.water_tank_levels[machine_id] = capacity
        else:
            current = self.get_estimated_water_level(machine_id)
            self.water_tank_levels[machine_id] = min(capacity, current + float(amount_ml))

        self.pre_brew_tank_levels[machine_id] = self.water_tank_levels[machine_id]
        _LOGGER.info(
            "Water tank refilled for machine %s: %.1f ml",
            machine_id,
            self.water_tank_levels[machine_id],
        )
        self.async_update_listeners()

    def handle_live_brew_update(
        self, machine_id: str, telem: MorningLiveBrewTelemetry
    ) -> None:
        """Handle incoming live telemetry update from IoT stream."""
        prev_telem = self.live_telemetry.get(machine_id)
        was_brewing = prev_telem.is_brewing if prev_telem else False

        # When brewing starts, snapshot current water level as pre-brew baseline
        if not was_brewing and telem.is_brewing:
            self.pre_brew_tank_levels[machine_id] = self.get_estimated_water_level(machine_id)

        # Dynamically decrement tank level during brew
        if telem.water_output > 0:
            pre_brew = self.pre_brew_tank_levels.get(
                machine_id, self.get_estimated_water_level(machine_id)
            )
            self.water_tank_levels[machine_id] = max(0.0, pre_brew - telem.water_output)

        # If brew just completed or stopped, mark live brew accounted for REST polling
        if was_brewing and not telem.is_brewing:
            self._pending_live_brew_accounted[machine_id] = True

        self.live_telemetry[machine_id] = telem
        self.async_update_listeners()

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

            machine_dict = {machine.id: machine for machine in machines}

            for machine in machines:
                mid = machine.id
                capacity = float(self.get_tank_capacity(mid))
                fallback_vol = float(self.get_fallback_brew_volume(mid))

                prev_level_status = self._previous_water_levels.get(mid)
                curr_level_status = machine.water_level.upper()

                # Physical capacitive sensor states
                if curr_level_status == WATER_LEVEL_LOW:
                    # Low water level sensor triggered -> clamp estimation to 0
                    self.water_tank_levels[mid] = 0.0
                    self.pre_brew_tank_levels[mid] = 0.0
                elif (
                    prev_level_status == WATER_LEVEL_LOW
                    and curr_level_status == WATER_LEVEL_NORMAL
                ):
                    # Reservoir refilled and reseated -> reset to full capacity
                    _LOGGER.info("Morning machine %s water tank refilled (LOW -> NORMAL)", mid)
                    self.water_tank_levels[mid] = capacity
                    self.pre_brew_tank_levels[mid] = capacity
                elif mid not in self.water_tank_levels:
                    # Initial seeding if not restored from prior state
                    self.water_tank_levels[mid] = capacity
                    self.pre_brew_tank_levels[mid] = capacity

                # Polling fallback: decrement volume if brew count incremented without live stream
                prev_brew_count = self._previous_brew_counts.get(mid)
                if prev_brew_count is not None and machine.brew_count > prev_brew_count:
                    delta = machine.brew_count - prev_brew_count
                    if self._pending_live_brew_accounted.pop(mid, False):
                        _LOGGER.debug(
                            "Brew count increment on %s already accounted for by live IoT stream",
                            mid,
                        )
                    else:
                        decrement = delta * fallback_vol
                        _LOGGER.debug(
                            "Brew count incremented by %d on %s without live stream; decrementing %.1f ml",
                            delta,
                            mid,
                            decrement,
                        )
                        self.water_tank_levels[mid] = max(
                            0.0, self.get_estimated_water_level(mid) - decrement
                        )
                        # Set sticky telemetry so brew sensors reflect the completed brew
                        self.live_telemetry[mid] = MorningLiveBrewTelemetry(
                            stage="done",
                            water_output=decrement,
                            is_brewing=False,
                            last_updated=time.time(),
                        )

                self._previous_water_levels[mid] = curr_level_status
                self._previous_brew_counts[mid] = machine.brew_count

            return machine_dict

        except MorningAuthError as err:
            _LOGGER.error("Authentication expired or invalid for Morning account: %s", err)
            raise ConfigEntryAuthFailed(err) from err
        except MorningConnectionError as err:
            _LOGGER.warning("Connection failure while updating Morning machine data: %s", err)
            raise UpdateFailed(err) from err
        except MorningError as err:
            _LOGGER.error("Error communicating with Morning API: %s", err)
            raise UpdateFailed(err) from err
