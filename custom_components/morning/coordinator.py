"""DataUpdateCoordinator for the Morning Coffee Machine integration."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

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
    STATUS_ECO,
    STATUS_HEATING,
    STATUS_IDLE,
    STATUS_PURGE,
    STATUS_READY,
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
        self._water_level_seeded: dict[str, bool] = {}
        self._previous_brew_counts: dict[str, int] = {}
        self._previous_water_levels: dict[str, str] = {}
        self._previous_statuses: dict[str, str] = {}
        self._previous_total_water: dict[str, int] = {}
        self._pending_live_brew_accounted: dict[str, bool] = {}
        self._last_live_brew_time: dict[str, float] = {}
        self._last_live_brew_volume: dict[str, float] = {}
        self._unreconciled_brew_volume: dict[str, float] = {}
        self._active_polling_brew: dict[str, bool] = {}
        self._brew_start_time: dict[str, float] = {}
        self._active_brew_profile: dict[str, list[dict[str, Any]]] = {}
        self._last_brew_profile: dict[str, list[dict[str, Any]]] = {}
        self._active_stages_seen: dict[str, list[str]] = {}
        self._mqtt_live_active: dict[str, bool] = {}
        self._last_mqtt_packet_ts: dict[str, float] = {}
        self.iot_listener: Any = None

    def _record_stage(self, machine_id: str, stage: str) -> list[str]:
        """Record an observed brew stage in chronological order for a machine."""
        stages = self._active_stages_seen.setdefault(machine_id, [])
        if stage and stage not in stages:
            stages.append(stage)
        return list(stages)

    def get_brew_profile(self, machine_id: str) -> list[dict[str, Any]]:
        """Return active or last recorded brew extraction profile."""
        telem = self.live_telemetry.get(machine_id)
        if telem and telem.profile:
            return telem.profile
        return self._last_brew_profile.get(machine_id, [])

    def set_restored_brew_profile(
        self, machine_id: str, profile: list[dict[str, Any]]
    ) -> None:
        """Seed or restore last brew extraction profile."""
        if profile and isinstance(profile, list):
            self._last_brew_profile[machine_id] = profile
            if machine_id in self.live_telemetry:
                self.live_telemetry[machine_id].profile = profile

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
        self._water_level_seeded[machine_id] = True
        self.async_update_listeners()

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
            stage="done",
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

        # If a polling fallback brew was active, refund its assumed volume now that live IoT arrived
        if self._active_polling_brew.pop(machine_id, False):
            refund = self._unreconciled_brew_volume.pop(machine_id, 0.0)
            if refund > 0:
                capacity = float(self.get_tank_capacity(machine_id))
                restored = min(capacity, self.get_estimated_water_level(machine_id) + refund)
                self.water_tank_levels[machine_id] = restored
                self.pre_brew_tank_levels[machine_id] = restored

        # Handle explicit cancel / abort from machine immediately
        if telem.stage in ("cancel", "cancelled", "canceled", "abort", "aborted"):
            self._mqtt_live_active[machine_id] = False
            dispensed = telem.water_output if telem.water_output > 0 else telem.mass_output
            if dispensed == 0 and prev_telem and prev_telem.is_brewing:
                dispensed = (
                    prev_telem.water_output
                    if prev_telem.water_output > 0
                    else prev_telem.mass_output
                )
            if machine_id in self.pre_brew_tank_levels:
                pre_brew = self.pre_brew_tank_levels.pop(machine_id)
                self.water_tank_levels[machine_id] = max(0.0, pre_brew - dispensed)
            if dispensed > 0:
                self.add_lifetime_water_ml(machine_id, dispensed)
            self._active_brew_profile.pop(machine_id, None)
            self._active_stages_seen.pop(machine_id, None)
            self._pending_live_brew_accounted[machine_id] = True
            self._last_live_brew_time[machine_id] = time.time()
            self._last_live_brew_volume[machine_id] = dispensed
            self.live_telemetry[machine_id] = MorningLiveBrewTelemetry(
                stage="idle",
                temperature=telem.temperature or (prev_telem.temperature if prev_telem else 0),
                water_output=dispensed,
                mass_output=telem.mass_output or (prev_telem.mass_output if prev_telem else 0.0),
                bloom_lapse=telem.bloom_lapse or (prev_telem.bloom_lapse if prev_telem else 0),
                is_brewing=False,
                last_updated=time.time(),
                profile=self._last_brew_profile.get(machine_id, []),
                stages_seen=[],
                source=telem.source or "mqtt",
            )
            self.async_update_listeners()
            return

        # Ignore passive shadow reports (ready/idle/eco) unless actively finishing a brew/purge
        if not telem.is_brewing and telem.stage in ("ready", "idle", "eco"):
            if not was_brewing:
                if prev_telem and prev_telem.stage in ("cancel", "cancelled"):
                    prev_telem.stage = "idle"
                    self.async_update_listeners()
                return
            self._mqtt_live_active[machine_id] = False
            # Machine was active and now returned to idle/ready/eco
            final_prof = self._active_brew_profile.pop(
                machine_id, self._last_brew_profile.get(machine_id, [])
            )
            if final_prof:
                self._last_brew_profile[machine_id] = final_prof
            stages_seen = self._record_stage(machine_id, "done")
            self._active_stages_seen.pop(machine_id, None)

            if prev_telem and prev_telem.stage == "purge":
                purge_vol = float(self.get_purge_volume(machine_id))
                pre_brew = self.pre_brew_tank_levels.get(
                    machine_id, self.get_estimated_water_level(machine_id)
                )
                self.water_tank_levels[machine_id] = max(0.0, pre_brew - purge_vol)
                self.add_lifetime_water_ml(machine_id, purge_vol)
                telem = MorningLiveBrewTelemetry(
                    stage="done",
                    water_output=purge_vol,
                    is_brewing=False,
                    last_updated=time.time(),
                    profile=self._last_brew_profile.get(machine_id, []),
                    stages_seen=stages_seen,
                    source=prev_telem.source or "mqtt",
                )
            else:
                telem = MorningLiveBrewTelemetry(
                    stage="done",
                    temperature=prev_telem.temperature if prev_telem else 0,
                    water_output=prev_telem.water_output if prev_telem else 0.0,
                    mass_output=prev_telem.mass_output if prev_telem else 0.0,
                    bloom_lapse=prev_telem.bloom_lapse if prev_telem else 0,
                    is_brewing=False,
                    last_updated=time.time(),
                    profile=self._last_brew_profile.get(machine_id, []),
                    stages_seen=stages_seen,
                    source=prev_telem.source if prev_telem else "mqtt",
                )
            self._pending_live_brew_accounted[machine_id] = True
            self._last_live_brew_time[machine_id] = time.time()
            self._last_live_brew_volume[machine_id] = telem.water_output
            self.live_telemetry[machine_id] = telem
            self.async_update_listeners()
            return

        if telem.source == "mqtt":
            self._mqtt_live_active[machine_id] = telem.is_brewing
            self._last_mqtt_packet_ts[machine_id] = time.time()

        # When brewing starts, snapshot current water level as pre-brew baseline
        if not was_brewing and telem.is_brewing:
            self.pre_brew_tank_levels[machine_id] = self.get_estimated_water_level(machine_id)
            self._brew_start_time[machine_id] = time.time()
            self._active_stages_seen[machine_id] = []
            self._active_brew_profile[machine_id] = [
                {
                    "t": 0.0,
                    "water": round(telem.water_output, 1),
                    "mass": round(telem.mass_output, 1),
                    "temp": int(telem.temperature),
                    "flow": 0.0,
                    "stage": telem.stage,
                }
            ]

        # While brewing, record real-time extraction curve profile
        if telem.is_brewing:
            # Promote 'brewing' to 'blooming' while bloom_lapse timer is actively incrementing
            if (
                telem.stage == "brewing"
                and telem.bloom_lapse > 0
                and (
                    prev_telem is None
                    or telem.bloom_lapse > prev_telem.bloom_lapse
                    or telem.water_output <= 5.0
                )
            ):
                telem.stage = "blooming"

            if telem.bloom_lapse > 0:
                self._record_stage(machine_id, "blooming")
            stages_seen = self._record_stage(machine_id, telem.stage)
            telem.stages_seen = stages_seen

            # Preserve temperature if current packet has 0 but prev had valid temperature
            if telem.temperature <= 0 and prev_telem and prev_telem.temperature > 0:
                telem.temperature = prev_telem.temperature

            start_t = self._brew_start_time.setdefault(machine_id, time.time())
            elapsed = round(max(0.0, time.time() - start_t), 1)
            prof = self._active_brew_profile.setdefault(machine_id, [])

            flow = 0.0
            if prof:
                last_pt = prof[-1]
                dt = elapsed - last_pt["t"]
                if dt >= 0.2:
                    dw = telem.water_output - last_pt["water"]
                    flow = round(max(0.0, dw / dt), 1)
                else:
                    flow = last_pt.get("flow", 0.0)

            if (
                not prof
                or (elapsed - prof[-1]["t"] >= 0.5)
                or (telem.water_output != prof[-1]["water"])
            ):
                prof.append(
                    {
                        "t": elapsed,
                        "water": round(telem.water_output, 1),
                        "mass": round(telem.mass_output, 1),
                        "temp": int(telem.temperature),
                        "flow": flow,
                        "stage": telem.stage,
                    }
                )
            telem.profile = list(prof)

        # Dynamically decrement tank level during brew using water_output (or mass_output)
        dispensed = telem.water_output if telem.water_output > 0 else telem.mass_output
        if dispensed > 0:
            pre_brew = self.pre_brew_tank_levels.get(
                machine_id, self.get_estimated_water_level(machine_id)
            )
            self.water_tank_levels[machine_id] = max(0.0, pre_brew - dispensed)

        # If brew just completed or stopped, mark live brew accounted for REST polling
        if was_brewing and not telem.is_brewing:
            self._mqtt_live_active[machine_id] = False
            self._pending_live_brew_accounted[machine_id] = True
            self._last_live_brew_time[machine_id] = time.time()
            self._last_live_brew_volume[machine_id] = dispensed

            final_prof = self._active_brew_profile.pop(machine_id, [])
            if final_prof:
                start_t = self._brew_start_time.get(machine_id, time.time())
                elapsed = round(max(0.0, time.time() - start_t), 1)
                if not final_prof or final_prof[-1]["water"] != telem.water_output:
                    final_prof.append(
                        {
                            "t": elapsed,
                            "water": round(telem.water_output, 1),
                            "mass": round(telem.mass_output, 1),
                            "temp": int(
                                telem.temperature
                                or (prev_telem.temperature if prev_telem else 0)
                            ),
                            "flow": 0.0,
                            "stage": "done",
                        }
                    )
                self._last_brew_profile[machine_id] = final_prof
            telem.profile = self._last_brew_profile.get(machine_id, [])
            stages_seen = self._record_stage(machine_id, "done")
            self._active_stages_seen.pop(machine_id, None)

            # If purge completed without stream flow meter data, decrement configured purge volume
            if prev_telem and prev_telem.stage == "purge" and dispensed == 0:
                purge_vol = float(self.get_purge_volume(machine_id))
                pre_brew = self.pre_brew_tank_levels.get(
                    machine_id, self.get_estimated_water_level(machine_id)
                )
                self.water_tank_levels[machine_id] = max(0.0, pre_brew - purge_vol)
                dispensed = purge_vol
                telem = MorningLiveBrewTelemetry(
                    stage="done",
                    water_output=purge_vol,
                    is_brewing=False,
                    last_updated=time.time(),
                    profile=self._last_brew_profile.get(machine_id, []),
                    stages_seen=stages_seen,
                    source=telem.source or "mqtt",
                )

            # Preserve previous final values if terminal packet had 0 (Terminal Packet Guard)
            term_water = (
                telem.water_output
                if telem.water_output > 0
                else (prev_telem.water_output if prev_telem else 0.0)
            )
            term_mass = (
                telem.mass_output
                if telem.mass_output > 0
                else (prev_telem.mass_output if prev_telem else 0.0)
            )
            term_temp = (
                telem.temperature
                if telem.temperature > 0
                else (prev_telem.temperature if prev_telem else 0)
            )
            term_bloom = (
                telem.bloom_lapse
                if telem.bloom_lapse > 0
                else (prev_telem.bloom_lapse if prev_telem else 0)
            )
            term_stage = telem.stage if telem.stage not in ("", "idle") else "done"
            term_profile = telem.profile or (
                prev_telem.profile
                if prev_telem
                else self._last_brew_profile.get(machine_id, [])
            )

            telem = MorningLiveBrewTelemetry(
                stage=term_stage,
                temperature=term_temp,
                water_output=term_water,
                mass_output=term_mass,
                bloom_lapse=term_bloom,
                is_brewing=False,
                last_updated=time.time(),
                profile=term_profile,
                stages_seen=stages_seen,
                source=telem.source or (prev_telem.source if prev_telem else "mqtt"),
            )

            if dispensed > 0:
                self.add_lifetime_water_ml(machine_id, dispensed)

        self.live_telemetry[machine_id] = telem
        self.async_update_listeners()

    def handle_shadow_update(
        self, machine_id: str, shadow_doc: dict[str, Any]
    ) -> None:
        """Handle real-time AWS IoT Thing Shadow update for physical-dial brews and hardware metrics."""
        if not self.data or machine_id not in self.data:
            return

        old_machine = self.data[machine_id]
        machine = old_machine.with_shadow_doc(shadow_doc)
        self.data[machine_id] = machine

        prev_status = self._previous_statuses.get(machine_id, old_machine.status.upper())
        curr_status = machine.status.upper()
        prev_total_water = self._previous_total_water.get(machine_id, old_machine.total_water_ml)
        prev_brew_count = self._previous_brew_counts.get(machine_id, old_machine.brew_count)

        mqtt_active = self._mqtt_live_active.get(machine_id, False) and (
            time.time() - self._last_mqtt_packet_ts.get(machine_id, 0.0) < 15.0
        )
        prev_t = self.live_telemetry.get(machine_id)
        was_brewing = bool(prev_t and prev_t.is_brewing)

        water_delta = (
            float(machine.total_water_ml - prev_total_water)
            if (prev_total_water > 0 and machine.total_water_ml > prev_total_water)
            else 0.0
        )
        brew_count_incremented = (
            prev_brew_count > 0 and machine.brew_count > prev_brew_count
        )

        changed = (
            machine != old_machine
            or curr_status != prev_status
            or water_delta > 0
            or brew_count_incremented
        )

        if not mqtt_active:
            if curr_status == "HEATING":
                if not was_brewing or (prev_t and prev_t.stage != "heating"):
                    self.pre_brew_tank_levels[machine_id] = self.get_estimated_water_level(
                        machine_id
                    )
                    self._brew_start_time[machine_id] = time.time()
                    self._active_stages_seen[machine_id] = ["heating"]
                    self._active_brew_profile[machine_id] = [
                        {
                            "t": 0.0,
                            "water": 0.0,
                            "mass": 0.0,
                            "temp": int(machine.temperature or (prev_t.temperature if prev_t else 0)),
                            "flow": 0.0,
                            "stage": "heating",
                        }
                    ]
                stages_seen = self._record_stage(machine_id, "heating")
                self.live_telemetry[machine_id] = MorningLiveBrewTelemetry(
                    stage="heating",
                    temperature=int(machine.temperature or (prev_t.temperature if prev_t else 0)),
                    water_output=0.0,
                    mass_output=0.0,
                    is_brewing=True,
                    last_updated=time.time(),
                    profile=list(self._active_brew_profile.get(machine_id, [])),
                    stages_seen=stages_seen,
                    source="shadow",
                )
                changed = True

            elif curr_status == "BREWING":
                if prev_status != "BREWING" or not self._active_polling_brew.get(machine_id, False):
                    if prev_status != "HEATING":
                        self.pre_brew_tank_levels[machine_id] = self.get_estimated_water_level(
                            machine_id
                        )
                        self._active_stages_seen[machine_id] = []
                    self._brew_start_time[machine_id] = time.time()
                    self._active_polling_brew[machine_id] = True
                    self._active_brew_profile[machine_id] = [
                        {
                            "t": 0.0,
                            "water": 0.0,
                            "mass": 0.0,
                            "temp": int(machine.temperature or 93),
                            "flow": 0.0,
                            "stage": "brewing",
                        }
                    ]

                stages_seen = self._record_stage(machine_id, "brewing")
                start_t = self._brew_start_time.setdefault(machine_id, time.time())
                elapsed = round(max(0.5, time.time() - start_t), 1)
                flow_rate = float(machine.pump_flow_rate_p1 or 2.75)
                est_water = (
                    water_delta
                    if water_delta > 0
                    else round(min(250.0, elapsed * flow_rate), 1)
                )
                pre_brew = self.pre_brew_tank_levels.get(
                    machine_id, self.get_estimated_water_level(machine_id)
                )
                self.water_tank_levels[machine_id] = max(0.0, pre_brew - est_water)
                self._unreconciled_brew_volume[machine_id] = est_water

                prof = self._active_brew_profile.setdefault(machine_id, [])
                temp_val = int(
                    machine.temperature or (prev_t.temperature if prev_t and prev_t.temperature > 0 else 93)
                )
                if not prof or elapsed > prof[-1]["t"]:
                    prof.append(
                        {
                            "t": elapsed,
                            "water": est_water,
                            "mass": est_water,
                            "temp": temp_val,
                            "flow": round(flow_rate, 1),
                            "stage": "brewing",
                        }
                    )

                self.live_telemetry[machine_id] = MorningLiveBrewTelemetry(
                    stage="brewing",
                    temperature=temp_val,
                    water_output=est_water,
                    mass_output=est_water,
                    is_brewing=True,
                    last_updated=time.time(),
                    profile=list(prof),
                    stages_seen=stages_seen,
                    source="shadow",
                )
                changed = True

            elif curr_status == "PURGE":
                stages_seen = self._record_stage(machine_id, "purge")
                self.live_telemetry[machine_id] = MorningLiveBrewTelemetry(
                    stage="purge",
                    is_brewing=True,
                    last_updated=time.time(),
                    stages_seen=stages_seen,
                    source="shadow",
                )
                changed = True

            elif curr_status in ("READY", "IDLE", "ECO", "POWER_OFF"):
                was_poll_brew = self._active_polling_brew.pop(machine_id, False)
                unreconciled = self._unreconciled_brew_volume.pop(machine_id, 0.0)
                live_accounted = self._pending_live_brew_accounted.pop(machine_id, False)

                if (water_delta > 0 or brew_count_incremented) and not live_accounted:
                    actual_vol = (
                        water_delta
                        if water_delta > 0
                        else (unreconciled if unreconciled > 0 else float(self.get_fallback_brew_volume(machine_id)))
                    )
                    pre_brew = self.pre_brew_tank_levels.get(
                        machine_id, self.get_estimated_water_level(machine_id)
                    )
                    self.water_tank_levels[machine_id] = max(0.0, pre_brew - actual_vol)
                    self.pre_brew_tank_levels[machine_id] = self.water_tank_levels[machine_id]
                    self.add_lifetime_water_ml(machine_id, actual_vol)

                    final_prof = self._active_brew_profile.pop(machine_id, [])
                    flow_rate = float(machine.pump_flow_rate_p1 or 2.75)
                    temp_val = int(
                        machine.temperature or (prev_t.temperature if prev_t and prev_t.temperature > 0 else 93)
                    )
                    if final_prof:
                        last_w = final_prof[-1]["water"]
                        if last_w > 0 and abs(last_w - actual_vol) > 0.5:
                            scale = actual_vol / last_w
                            for pt in final_prof:
                                pt["water"] = round(pt["water"] * scale, 1)
                                pt["mass"] = round(pt["mass"] * scale, 1)
                        final_prof[-1]["stage"] = "done"
                    else:
                        est_dur = round(max(1.0, actual_vol / flow_rate), 1)
                        final_prof = [
                            {"t": 0.0, "water": 0.0, "mass": 0.0, "temp": temp_val, "flow": 0.0, "stage": "brewing"},
                            {"t": est_dur, "water": round(actual_vol, 1), "mass": round(actual_vol, 1), "temp": temp_val, "flow": round(flow_rate, 1), "stage": "done"},
                        ]
                    self._last_brew_profile[machine_id] = final_prof
                    stages_seen = self._record_stage(machine_id, "done")
                    self._active_stages_seen.pop(machine_id, None)

                    self.live_telemetry[machine_id] = MorningLiveBrewTelemetry(
                        stage="done",
                        temperature=temp_val,
                        water_output=round(actual_vol, 1),
                        mass_output=round(actual_vol, 1),
                        bloom_lapse=prev_t.bloom_lapse if prev_t else 0,
                        is_brewing=False,
                        last_updated=time.time(),
                        profile=list(final_prof),
                        stages_seen=stages_seen,
                        source="shadow",
                    )
                    changed = True

                elif prev_status == "PURGE":
                    purge_vol = water_delta if water_delta > 0 else float(self.get_purge_volume(machine_id))
                    self.water_tank_levels[machine_id] = max(
                        0.0, self.get_estimated_water_level(machine_id) - purge_vol
                    )
                    self.pre_brew_tank_levels[machine_id] = self.water_tank_levels[machine_id]
                    self.add_lifetime_water_ml(machine_id, purge_vol)
                    stages_seen = self._record_stage(machine_id, "done")
                    self._active_stages_seen.pop(machine_id, None)
                    self.live_telemetry[machine_id] = MorningLiveBrewTelemetry(
                        stage="done",
                        water_output=round(purge_vol, 1),
                        is_brewing=False,
                        last_updated=time.time(),
                        profile=self._last_brew_profile.get(machine_id, []),
                        stages_seen=stages_seen,
                        source="shadow",
                    )
                    changed = True

                elif (was_poll_brew or was_brewing) and not brew_count_incremented and water_delta == 0:
                    # Physical brew/heating canceled before dispensing
                    if machine_id in self.pre_brew_tank_levels:
                        self.water_tank_levels[machine_id] = self.pre_brew_tank_levels[machine_id]
                    self._active_brew_profile.pop(machine_id, None)
                    self._active_stages_seen.pop(machine_id, None)
                    self.live_telemetry[machine_id] = MorningLiveBrewTelemetry(
                        stage="idle",
                        water_output=0.0,
                        mass_output=0.0,
                        temperature=prev_t.temperature if prev_t else 0,
                        bloom_lapse=0,
                        is_brewing=False,
                        last_updated=time.time(),
                        profile=self._last_brew_profile.get(machine_id, []),
                        stages_seen=[],
                        source="shadow",
                    )
                    changed = True

        self._previous_statuses[machine_id] = curr_status
        self._previous_brew_counts[machine_id] = machine.brew_count
        if machine.total_water_ml > 0:
            self._previous_total_water[machine_id] = machine.total_water_ml

        if changed:
            self.async_update_listeners()

    async def _async_update_data(self) -> dict[str, MorningMachine]:
        """Fetch latest telemetry and status for all user machines."""
        try:
            machines = await self.client.get_machines()

            if self.iot_listener is not None and hasattr(
                self.iot_listener, "async_get_thing_shadow"
            ):
                enriched_machines: list[MorningMachine] = []
                for m in machines:
                    try:
                        shadow_doc = await self.iot_listener.async_get_thing_shadow(m.id)
                        if isinstance(shadow_doc, dict) and shadow_doc:
                            m = m.with_shadow_doc(shadow_doc)
                    except Exception:
                        pass
                    enriched_machines.append(m)
                machines = enriched_machines

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

                prev_status = self._previous_statuses.get(mid)
                curr_status = machine.status.upper()
                live_active = bool(
                    self.live_telemetry.get(mid) and self.live_telemetry[mid].is_brewing
                )
                is_running = live_active or curr_status in ("BREWING", "PURGE")

                # Restore previous value on startup before defaulting to full capacity
                if mid not in self.water_tank_levels:
                    restored = None
                    if hasattr(self, "hass") and self.hass and hasattr(self.hass, "states"):
                        try:
                            from homeassistant.helpers import entity_registry as er

                            ent_reg = er.async_get(self.hass)
                            target_unique_id = f"{mid}_water_level_estimated"
                            target_ent_id = ent_reg.async_get_entity_id(
                                "sensor", DOMAIN, target_unique_id
                            )
                            if target_ent_id and isinstance(target_ent_id, str):
                                state = self.hass.states.get(target_ent_id)
                                if (
                                    state
                                    and isinstance(state.state, str)
                                    and state.state not in ("unknown", "unavailable")
                                ):
                                    restored = float(state.state)
                        except Exception:
                            pass

                        if restored is None and hasattr(self.hass.states, "async_all"):
                            raw_states = self.hass.states.async_all("sensor")
                            if isinstance(raw_states, list):
                                for state in raw_states:
                                    if (
                                        isinstance(state.entity_id, str)
                                        and state.entity_id.endswith("_water_tank_level")
                                        and isinstance(state.state, str)
                                        and state.state not in ("unknown", "unavailable")
                                    ):
                                        try:
                                            restored = float(state.state)
                                            break
                                        except (ValueError, TypeError):
                                            pass

                    if restored is not None:
                        self.water_tank_levels[mid] = max(0.0, min(capacity, restored))
                        self._water_level_seeded[mid] = True
                    else:
                        if curr_level_status == WATER_LEVEL_LOW:
                            self.water_tank_levels[mid] = 0.0
                        else:
                            self.water_tank_levels[mid] = capacity
                    self.pre_brew_tank_levels[mid] = self.water_tank_levels[mid]

                # Physical capacitive sensor states (guarded against pump vibration / liquid slosh)
                if curr_level_status == WATER_LEVEL_LOW and not is_running:
                    # Low water level sensor triggered while idle -> clamp estimation
                    self.water_tank_levels[mid] = 0.0
                    self.pre_brew_tank_levels[mid] = 0.0
                elif (
                    prev_level_status == WATER_LEVEL_LOW
                    and curr_level_status == WATER_LEVEL_NORMAL
                    and not is_running
                ):
                    # Reservoir refilled after being confirmed empty while machine is idle
                    _LOGGER.info("Morning machine %s water tank refilled (LOW -> NORMAL)", mid)
                    self.water_tank_levels[mid] = capacity
                    self.pre_brew_tank_levels[mid] = capacity

                # Polling fallback: detect active heating/brewing start if live stream not connected
                if (
                    curr_status in (STATUS_HEATING, "HEATING", "heating")
                    and prev_status not in (STATUS_HEATING, "HEATING", "heating")
                    and not live_active
                ):
                    prev_t = self.live_telemetry.get(mid)
                    self._active_stages_seen[mid] = ["heating"]
                    self.live_telemetry[mid] = MorningLiveBrewTelemetry(
                        stage="heating",
                        temperature=int(
                            getattr(machine, "temperature", 0)
                            or (prev_t.temperature if prev_t else 0)
                        ),
                        water_output=0.0,
                        mass_output=0.0,
                        is_brewing=True,
                        last_updated=time.time(),
                        stages_seen=["heating"],
                        source="rest",
                    )
                elif (
                    curr_status == "BREWING"
                    and prev_status != "BREWING"
                    and not live_active
                    and not self._active_polling_brew.get(mid, False)
                ):
                    if prev_status not in (STATUS_HEATING, "HEATING", "heating"):
                        self._active_stages_seen[mid] = []
                    stages_seen = self._record_stage(mid, "brewing")
                    self._active_polling_brew[mid] = True
                    assumed = fallback_vol
                    self._unreconciled_brew_volume[mid] = (
                        self._unreconciled_brew_volume.get(mid, 0.0) + assumed
                    )
                    self.water_tank_levels[mid] = max(
                        0.0, self.get_estimated_water_level(mid) - assumed
                    )
                    prev_t = self.live_telemetry.get(mid)
                    self.live_telemetry[mid] = MorningLiveBrewTelemetry(
                        stage="brewing",
                        water_output=assumed,
                        mass_output=prev_t.mass_output if prev_t else 0.0,
                        temperature=prev_t.temperature if prev_t else 0,
                        is_brewing=True,
                        last_updated=time.time(),
                        stages_seen=stages_seen,
                        source="rest",
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
                        prev_t = self.live_telemetry.get(mid)
                        stages_seen = self._record_stage(mid, "done")
                        self._active_stages_seen.pop(mid, None)
                        if not self._last_brew_profile.get(mid):
                            flow_rate = float(machine.pump_flow_rate_p1 or 2.75)
                            temp_val = int(prev_t.temperature if prev_t and prev_t.temperature > 0 else 93)
                            est_dur = round(max(1.0, assumed / flow_rate), 1)
                            self._last_brew_profile[mid] = [
                                {"t": 0.0, "water": 0.0, "mass": 0.0, "temp": temp_val, "flow": 0.0, "stage": "brewing"},
                                {"t": est_dur, "water": round(assumed, 1), "mass": round(assumed, 1), "temp": temp_val, "flow": round(flow_rate, 1), "stage": "done"},
                            ]
                        self.live_telemetry[mid] = MorningLiveBrewTelemetry(
                            stage="done",
                            water_output=assumed,
                            mass_output=prev_t.mass_output if prev_t else 0.0,
                            temperature=prev_t.temperature if prev_t else 0,
                            bloom_lapse=prev_t.bloom_lapse if prev_t else 0,
                            is_brewing=False,
                            last_updated=time.time(),
                            profile=self._last_brew_profile.get(mid, []),
                            stages_seen=stages_seen,
                            source="rest",
                        )
                        self.add_lifetime_water_ml(mid, assumed)

                # Flow meter delta reconciliation (total_water_ml)
                prev_total_water = self._previous_total_water.get(mid)

                if (
                    prev_total_water is not None
                    and prev_total_water > 0
                    and machine.total_water_ml > prev_total_water
                ):
                    water_delta = float(machine.total_water_ml - prev_total_water)
                    self._active_polling_brew.pop(mid, None)
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
                        prev_t = self.live_telemetry.get(mid)
                        flow_rate = float(machine.pump_flow_rate_p1 or 2.75)
                        temp_val = int(prev_t.temperature if prev_t and prev_t.temperature > 0 else 93)
                        est_dur = round(max(1.0, water_delta / flow_rate), 1)
                        self._last_brew_profile[mid] = [
                            {"t": 0.0, "water": 0.0, "mass": 0.0, "temp": temp_val, "flow": 0.0, "stage": "brewing"},
                            {"t": est_dur, "water": round(water_delta, 1), "mass": round(water_delta, 1), "temp": temp_val, "flow": round(flow_rate, 1), "stage": "done"},
                        ]
                        self.live_telemetry[mid] = MorningLiveBrewTelemetry(
                            stage="done",
                            water_output=water_delta,
                            mass_output=prev_t.mass_output if prev_t else 0.0,
                            temperature=prev_t.temperature if prev_t else 0,
                            bloom_lapse=prev_t.bloom_lapse if prev_t else 0,
                            is_brewing=False,
                            last_updated=time.time(),
                            profile=self._last_brew_profile.get(mid, []),
                            stages_seen=list(prev_t.stages_seen) if prev_t and prev_t.stages_seen else ["brewing", "done"],
                            source="rest",
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
                        prev_t = self.live_telemetry.get(mid)
                        self.live_telemetry[mid] = MorningLiveBrewTelemetry(
                            stage="done",
                            water_output=water_delta,
                            mass_output=prev_t.mass_output if prev_t else 0.0,
                            temperature=prev_t.temperature if prev_t else 0,
                            bloom_lapse=prev_t.bloom_lapse if prev_t else 0,
                            is_brewing=False,
                            last_updated=time.time(),
                            profile=self._last_brew_profile.get(mid, []),
                            stages_seen=["purge", "done"],
                            source="rest",
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
                    prev_t = self.live_telemetry.get(mid)
                    self.live_telemetry[mid] = MorningLiveBrewTelemetry(
                        stage="done",
                        water_output=purge_vol,
                        mass_output=prev_t.mass_output if prev_t else 0.0,
                        temperature=prev_t.temperature if prev_t else 0,
                        bloom_lapse=prev_t.bloom_lapse if prev_t else 0,
                        is_brewing=False,
                        last_updated=time.time(),
                        profile=self._last_brew_profile.get(mid, []),
                        stages_seen=["purge", "done"],
                        source="rest",
                    )
                    self.add_lifetime_water_ml(mid, purge_vol)

                if curr_status in (
                    STATUS_IDLE,
                    STATUS_READY,
                    STATUS_ECO,
                    "IDLE",
                    "READY",
                    "ECO",
                    "POWER_OFF",
                ):
                    was_unreconciled_poll_brew = self._active_polling_brew.pop(mid, False)
                    prev_t = self.live_telemetry.get(mid)
                    if was_unreconciled_poll_brew and not brew_count_incremented:
                        # Polling brew ended without brew_count or flow meter increment -> canceled!
                        refund = self._unreconciled_brew_volume.pop(mid, 0.0)
                        if refund > 0:
                            self.water_tank_levels[mid] = min(
                                capacity, self.get_estimated_water_level(mid) + refund
                            )
                        self._active_brew_profile.pop(mid, None)
                        self._active_stages_seen.pop(mid, None)
                        self.live_telemetry[mid] = MorningLiveBrewTelemetry(
                            stage="idle",
                            water_output=0.0,
                            mass_output=0.0,
                            temperature=prev_t.temperature if prev_t else 0,
                            bloom_lapse=0,
                            is_brewing=False,
                            last_updated=time.time(),
                            profile=self._last_brew_profile.get(mid, []),
                            stages_seen=[],
                            source="rest",
                        )
                    elif prev_t and prev_t.is_brewing:
                        final_prof = self._active_brew_profile.pop(
                            mid, self._last_brew_profile.get(mid, [])
                        )
                        if final_prof:
                            self._last_brew_profile[mid] = final_prof
                        stages_seen = self._record_stage(mid, "done")
                        self._active_stages_seen.pop(mid, None)
                        self.live_telemetry[mid] = MorningLiveBrewTelemetry(
                            stage="done",
                            water_output=prev_t.water_output,
                            mass_output=prev_t.mass_output,
                            temperature=prev_t.temperature,
                            bloom_lapse=prev_t.bloom_lapse,
                            is_brewing=False,
                            last_updated=time.time(),
                            profile=self._last_brew_profile.get(mid, []),
                            stages_seen=stages_seen,
                            source=prev_t.source or "rest",
                        )
                elif curr_status != "BREWING":
                    self._active_polling_brew.pop(mid, None)

                if not is_running or mid not in self._previous_water_levels:
                    self._previous_water_levels[mid] = curr_level_status
                self._previous_brew_counts[mid] = machine.brew_count
                self._previous_statuses[mid] = curr_status
                if machine.total_water_ml > 0 or mid not in self._previous_total_water:
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
