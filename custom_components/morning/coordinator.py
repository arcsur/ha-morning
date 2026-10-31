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
    CONF_PURGE_VOLUME,
    CONF_REFRESH_TOKEN,
    CONF_TANK_CAPACITY,
    CONF_TOKEN_EXPIRES_AT,
    CONF_USER_ID,
    DEFAULT_FALLBACK_BREW_VOLUME,
    DEFAULT_PURGE_VOLUME,
    DEFAULT_TANK_CAPACITY,
    DOMAIN,
    STATUS_PURGE,
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
        self.lifetime_water_levels: dict[str, float] = {}
        self._previous_brew_counts: dict[str, int] = {}
        self._previous_water_levels: dict[str, str] = {}
        self._previous_statuses: dict[str, str] = {}
        self._previous_total_water: dict[str, int] = {}
        self._pending_live_brew_accounted: dict[str, bool] = {}
        self._last_live_brew_time: dict[str, float] = {}
        self._last_live_brew_volume: dict[str, float] = {}
        self._unreconciled_brew_volume: dict[str, float] = {}
        self._active_polling_brew: dict[str, bool] = {}

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

    def get_purge_volume(self, machine_id: str | None = None) -> int:
        """Return configured purge rinse volume in ml."""
        return int(
            self.config_entry.options.get(
                CONF_PURGE_VOLUME,
                self.config_entry.data.get(CONF_PURGE_VOLUME, DEFAULT_PURGE_VOLUME),
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

    def get_lifetime_water_ml(self, machine_id: str) -> float:
        """Return cumulative lifetime water pumped in ml."""
        return self.lifetime_water_levels.get(machine_id, 0.0)

    def set_lifetime_water_ml(self, machine_id: str, volume_ml: float) -> None:
        """Seed or restore lifetime water level in ml."""
        self.lifetime_water_levels[machine_id] = max(0.0, float(volume_ml))

    def add_lifetime_water_ml(self, machine_id: str, volume_ml: float) -> None:
        """Increment cumulative lifetime water pumped in ml."""
        if volume_ml > 0:
            self.lifetime_water_levels[machine_id] = (
                self.lifetime_water_levels.get(machine_id, 0.0) + float(volume_ml)
            )

    def record_purge(self, machine_id: str, amount_ml: int | None = None) -> None:
        """Record a purge rinse, decrementing reservoir water level."""
        volume = float(
            amount_ml if amount_ml is not None else self.get_purge_volume(machine_id)
        )
        current = self.get_estimated_water_level(machine_id)
        self.water_tank_levels[machine_id] = max(0.0, current - volume)
        self.pre_brew_tank_levels[machine_id] = self.water_tank_levels[machine_id]
        self.live_telemetry[machine_id] = MorningLiveBrewTelemetry(
            stage="purge",
            water_output=volume,
            is_brewing=False,
            last_updated=time.time(),
        )
        self.add_lifetime_water_ml(machine_id, volume)
        _LOGGER.info(
            "Purge rinse recorded for machine %s: -%.1f ml (remaining: %.1f ml)",
            machine_id,
            volume,
            self.water_tank_levels[machine_id],
        )
        self.async_update_listeners()

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

        # Dynamically decrement tank level during brew using water_output (or mass_output)
        dispensed = telem.water_output if telem.water_output > 0 else telem.mass_output
        if dispensed > 0:
            pre_brew = self.pre_brew_tank_levels.get(
                machine_id, self.get_estimated_water_level(machine_id)
            )
            self.water_tank_levels[machine_id] = max(0.0, pre_brew - dispensed)

        # If brew just completed or stopped, mark live brew accounted for REST polling
        if was_brewing and not telem.is_brewing:
            self._pending_live_brew_accounted[machine_id] = True
            self._last_live_brew_time[machine_id] = time.time()
            self._last_live_brew_volume[machine_id] = dispensed

            # If purge completed without stream flow meter data, decrement configured purge volume
            if prev_telem and prev_telem.stage == "purge" and dispensed == 0:
                purge_vol = float(self.get_purge_volume(machine_id))
                pre_brew = self.pre_brew_tank_levels.get(
                    machine_id, self.get_estimated_water_level(machine_id)
                )
                self.water_tank_levels[machine_id] = max(0.0, pre_brew - purge_vol)
                dispensed = purge_vol
                telem = MorningLiveBrewTelemetry(
                    stage="purge",
                    water_output=purge_vol,
                    is_brewing=False,
                    last_updated=time.time(),
                )

            # Preserve previous final values if terminal packet had 0
            if telem.water_output == 0 and prev_telem and prev_telem.water_output > 0:
                telem = MorningLiveBrewTelemetry(
                    stage=telem.stage if telem.stage not in ("", "idle") else "done",
                    temperature=telem.temperature or prev_telem.temperature,
                    water_output=prev_telem.water_output,
                    mass_output=prev_telem.mass_output,
                    bloom_lapse=telem.bloom_lapse or prev_telem.bloom_lapse,
                    is_brewing=False,
                    last_updated=time.time(),
                )

            if dispensed > 0:
                self.add_lifetime_water_ml(machine_id, dispensed)

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

                prev_status = self._previous_statuses.get(mid)
                curr_status = machine.status.upper()
                live_active = bool(
                    self.live_telemetry.get(mid) and self.live_telemetry[mid].is_brewing
                )

                # Polling fallback: detect active brewing start if live stream not connected
                if (
                    curr_status == "BREWING"
                    and prev_status != "BREWING"
                    and not live_active
                    and not self._active_polling_brew.get(mid, False)
                ):
                    self._active_polling_brew[mid] = True
                    assumed = fallback_vol
                    self._unreconciled_brew_volume[mid] = (
                        self._unreconciled_brew_volume.get(mid, 0.0) + assumed
                    )
                    self.water_tank_levels[mid] = max(
                        0.0, self.get_estimated_water_level(mid) - assumed
                    )
                    self.live_telemetry[mid] = MorningLiveBrewTelemetry(
                        stage="brewing",
                        water_output=assumed,
                        is_brewing=True,
                        last_updated=time.time(),
                    )
                    _LOGGER.debug(
                        "Brew started on %s via polling; deducted fallback %.1f ml",
                        mid,
                        assumed,
                    )

                # Polling fallback: decrement volume if brew count incremented without live stream
                prev_brew_count = self._previous_brew_counts.get(mid)
                brew_count_incremented = (
                    prev_brew_count is not None and machine.brew_count > prev_brew_count
                )
                live_accounted = self._pending_live_brew_accounted.pop(mid, False)
                recent_live_brew = (time.time() - self._last_live_brew_time.get(mid, 0.0)) < 120.0

                if brew_count_incremented:
                    delta = machine.brew_count - prev_brew_count
                    if live_accounted or recent_live_brew:
                        _LOGGER.debug(
                            "Brew count increment on %s already accounted for by live IoT stream (delta=%d)",
                            mid,
                            delta,
                        )
                        self._active_polling_brew.pop(mid, None)
                        self._unreconciled_brew_volume.pop(mid, None)
                        # Keep existing live telemetry from IoT stream intact
                    else:
                        if self._active_polling_brew.pop(mid, False):
                            # Already deducted assumed volume on BREWING status transition
                            assumed = self._unreconciled_brew_volume.get(mid, fallback_vol)
                        else:
                            # Missed BREWING status, deduct assumed volume now
                            assumed = delta * fallback_vol
                            self._unreconciled_brew_volume[mid] = (
                                self._unreconciled_brew_volume.get(mid, 0.0) + assumed
                            )
                            self.water_tank_levels[mid] = max(
                                0.0, self.get_estimated_water_level(mid) - assumed
                            )
                            _LOGGER.debug(
                                "Brew count incremented by %d on %s without live stream; assumed %.1f ml",
                                delta,
                                mid,
                                assumed,
                            )

                        # Set sticky telemetry to 'done' for offline polling brew
                        self.live_telemetry[mid] = MorningLiveBrewTelemetry(
                            stage="done",
                            water_output=assumed,
                            is_brewing=False,
                            last_updated=time.time(),
                        )
                        self.add_lifetime_water_ml(mid, assumed)

                # Flow meter delta reconciliation (total_water_ml)
                prev_total_water = self._previous_total_water.get(mid)

                if prev_total_water is not None and machine.total_water_ml > prev_total_water:
                    water_delta = float(machine.total_water_ml - prev_total_water)
                    unreconciled = self._unreconciled_brew_volume.pop(mid, 0.0)
                    self.add_lifetime_water_ml(mid, water_delta)

                    if live_accounted or (
                        (prev_telem := self.live_telemetry.get(mid)) and prev_telem.is_brewing
                    ):
                        _LOGGER.debug(
                            "Total water increment of %.1f ml on %s correlated with live brew",
                            water_delta,
                            mid,
                        )
                    elif unreconciled > 0:
                        # Reconcile assumed fallback volume with actual dispensed water from flow meter
                        correction = unreconciled - water_delta
                        self.water_tank_levels[mid] = max(
                            0.0, min(capacity, self.water_tank_levels[mid] + correction)
                        )
                        self.live_telemetry[mid] = MorningLiveBrewTelemetry(
                            stage="done",
                            water_output=water_delta,
                            is_brewing=False,
                            last_updated=time.time(),
                        )
                        _LOGGER.info(
                            "Reconciled fallback brew volume on %s: assumed %.1f ml -> actual %.1f ml (tank level: %.1f ml)",
                            mid,
                            unreconciled,
                            water_delta,
                            self.water_tank_levels[mid],
                        )
                    elif brew_count_incremented:
                        _LOGGER.debug(
                            "Total water increment of %.1f ml on %s correlated with brew count increment",
                            water_delta,
                            mid,
                        )
                    else:
                        _LOGGER.info(
                            "Flow meter dispensed %.1f ml outside recipe on %s (purge/rinse)",
                            water_delta,
                            mid,
                        )
                        self.water_tank_levels[mid] = max(
                            0.0, self.get_estimated_water_level(mid) - water_delta
                        )
                        self.live_telemetry[mid] = MorningLiveBrewTelemetry(
                            stage="purge",
                            water_output=water_delta,
                            is_brewing=False,
                            last_updated=time.time(),
                        )
                elif prev_status == STATUS_PURGE and curr_status != STATUS_PURGE:
                    purge_vol = float(self.get_purge_volume(mid))
                    _LOGGER.info(
                        "Purge cycle completed on %s (PURGE -> %s); decrementing %.1f ml",
                        mid,
                        curr_status,
                        purge_vol,
                    )
                    self.water_tank_levels[mid] = max(
                        0.0, self.get_estimated_water_level(mid) - purge_vol
                    )
                    self.live_telemetry[mid] = MorningLiveBrewTelemetry(
                        stage="purge",
                        water_output=purge_vol,
                        is_brewing=False,
                        last_updated=time.time(),
                    )

                if curr_status != "BREWING":
                    self._active_polling_brew.pop(mid, None)

                self._previous_water_levels[mid] = curr_level_status
                self._previous_brew_counts[mid] = machine.brew_count
                self._previous_statuses[mid] = curr_status
                self._previous_total_water[mid] = machine.total_water_ml

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
