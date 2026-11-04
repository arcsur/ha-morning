"""Sensor platform for Morning Coffee Machine."""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfMass,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_MACHINE_IDS,
    DOMAIN,
    STATUS_BREWING,
    STATUS_ECO,
    STATUS_FAULT,
    STATUS_IDLE,
    STATUS_MAINTAIN,
    STATUS_MAINTENANCE,
    STATUS_POWER_OFF,
    STATUS_READY,
    STATUS_SCALE,
    STATUS_WATER,
)
from .coordinator import MorningDataUpdateCoordinator
from .entity import MorningEntity

STATUS_ICON_MAP = {
    STATUS_BREWING: "mdi:coffee-maker",
    STATUS_ECO: "mdi:leaf",
    STATUS_IDLE: "mdi:check-circle-outline",
    STATUS_READY: "mdi:check-circle-outline",
    STATUS_WATER: "mdi:water-alert",
    STATUS_MAINTENANCE: "mdi:wrench-outline",
    STATUS_MAINTAIN: "mdi:wrench-outline",
    STATUS_SCALE: "mdi:water-boiler-alert",
    STATUS_FAULT: "mdi:alert-circle",
    STATUS_POWER_OFF: "mdi:power",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Morning sensor entities based on config entry."""
    coordinator: MorningDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    machine_ids: list[str] = entry.data.get(CONF_MACHINE_IDS, [])

    entities: list[SensorEntity] = []
    for mid in machine_ids:
        entities.extend(
            [
                MorningStatusSensor(coordinator, mid),
                MorningBrewCountSensor(coordinator, mid),
                MorningLimescaleSensor(coordinator, mid),
                MorningStandbyTimeoutSensor(coordinator, mid),
                MorningFirmwareSensor(coordinator, mid),
                MorningEstimatedWaterLevelSensor(coordinator, mid),
                MorningWaterTankPercentageSensor(coordinator, mid),
                MorningBrewWaterDispensedSensor(coordinator, mid),
                MorningBrewMassDispensedSensor(coordinator, mid),
                MorningBrewTemperatureSensor(coordinator, mid),
                MorningBrewStageSensor(coordinator, mid),
                MorningBrewBloomSensor(coordinator, mid),
                MorningLifetimeWaterSensor(coordinator, mid),
                MorningSlaveFirmwareSensor(coordinator, mid),
                MorningFaultCodeSensor(coordinator, mid),
            ]
        )

    async_add_entities(entities)


class MorningStatusSensor(MorningEntity, SensorEntity):
    """Sensor tracking the operational status of the Morning Machine."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the status sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = SensorEntityDescription(
            key="status",
            translation_key="status",
            name="Status",
            has_entity_name=True,
        )
        self._attr_unique_id = f"{machine_id}_status"

    @property
    def native_value(self) -> str | None:
        """Return the current machine status."""
        if not self.machine:
            return None
        telem = getattr(self.coordinator, "live_telemetry", {}).get(self._machine_id)
        raw_status = self.machine.status.lower()
        if telem:
            is_fresh = telem.last_updated > 0 and (time.time() - telem.last_updated) < 60.0
            if telem.is_brewing and is_fresh:
                if telem.stage == "heating":
                    return "heating"
                if telem.stage == "purge":
                    return "purge"
                return "brewing"
            if not telem.is_brewing and raw_status in ("brewing", "heating", "purge"):
                return "done" if telem.stage == "done" else "idle"
        return raw_status

    @property
    def icon(self) -> str:
        """Return dynamic icon depending on machine state."""
        if not self.machine:
            return "mdi:coffee-maker-outline"
        status = (self.native_value or self.machine.status or "").upper()
        if status == "DONE":
            return "mdi:check-circle-outline"
        return STATUS_ICON_MAP.get(status, "mdi:coffee-maker-outline")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional machine telemetry attributes."""
        if not self.machine:
            return {}
        return {
            "raw_status": self.machine.status,
            "type": self.machine.type,
            "sub_type": self.machine.sub_type,
            "online": self.machine.online,
            "active": self.machine.active,
            "recipe_slots": self.machine.recipe_slots,
            "child_lock": self.machine.child_lock,
            "total_water_ml": max(
                self.coordinator.get_lifetime_water_ml(self._machine_id),
                self.machine.total_water_ml,
            ),
            "stm32_version": self.machine.stm32_version,
            "fault_information": self.machine.fault_information,
            "pump_flow_rate_k1": self.machine.pump_flow_rate_k1,
            "pump_flow_rate_p1": self.machine.pump_flow_rate_p1,
        }


class MorningBrewCountSensor(MorningEntity, SensorEntity):
    """Sensor tracking the total brew count of the Morning Machine."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the brew count sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = SensorEntityDescription(
            key="brew_count",
            name="Total Brews",
            has_entity_name=True,
            icon="mdi:coffee",
            state_class=SensorStateClass.TOTAL_INCREASING,
        )
        self._attr_unique_id = f"{machine_id}_brew_count"

    @property
    def native_value(self) -> int | None:
        """Return the total brew cycles count."""
        return self.machine.brew_count if self.machine else None


class MorningLimescaleSensor(MorningEntity, SensorEntity):
    """Sensor tracking the limescale / descaling urgency meter."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the limescale sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = SensorEntityDescription(
            key="limescale",
            name="Limescale Counter",
            has_entity_name=True,
            icon="mdi:water-boiler-alert",
            state_class=SensorStateClass.TOTAL_INCREASING,
        )
        self._attr_unique_id = f"{machine_id}_limescale"

    @property
    def native_value(self) -> int | None:
        """Return the current limescale counter value."""
        return self.machine.lime_scale if self.machine else None


class MorningStandbyTimeoutSensor(MorningEntity, SensorEntity):
    """Sensor displaying the configured standby timeout in seconds."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the standby timeout sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = SensorEntityDescription(
            key="standby_timeout",
            name="Standby Timeout",
            has_entity_name=True,
            icon="mdi:timer-sand",
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
        )
        self._attr_unique_id = f"{machine_id}_standby_timeout"

    @property
    def native_value(self) -> int | None:
        """Return the auto-sleep timeout in seconds."""
        return self.machine.energy_save_timeout if self.machine else None


class MorningFirmwareSensor(MorningEntity, SensorEntity):
    """Sensor displaying firmware version and update availability."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the firmware sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = SensorEntityDescription(
            key="firmware",
            name="Firmware",
            has_entity_name=True,
            icon="mdi:cellphone-arrow-down",
        )
        self._attr_unique_id = f"{machine_id}_firmware"

    @property
    def native_value(self) -> str | None:
        """Return the running firmware version."""
        return self.machine.firmware_version if self.machine else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return firmware details."""
        if not self.machine or not self.machine.firmware:
            return {}
        return {
            "is_latest": self.machine.firmware.is_latest,
            "latest_version": self.machine.firmware.latest_version,
        }


class MorningEstimatedWaterLevelSensor(MorningEntity, RestoreSensor):
    """Sensor tracking the estimated water level in the machine tank."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the estimated water level sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = SensorEntityDescription(
            key="water_level_estimated",
            name="Water Tank Level",
            has_entity_name=True,
            icon="mdi:water",
            device_class=SensorDeviceClass.VOLUME_STORAGE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        )
        self._attr_unique_id = f"{machine_id}_water_level_estimated"

    async def async_added_to_hass(self) -> None:
        """Restore state on startup if not already seeded."""
        await super().async_added_to_hass()
        if not self.coordinator._water_level_seeded.get(self._machine_id, False):
            restored_val = None
            last_sensor_data = await self.async_get_last_sensor_data()
            if last_sensor_data and last_sensor_data.native_value is not None:
                try:
                    restored_val = float(last_sensor_data.native_value)
                except (ValueError, TypeError):
                    pass
            if restored_val is None:
                last_state = await self.async_get_last_state()
                if last_state and last_state.state not in ("unknown", "unavailable"):
                    try:
                        restored_val = float(last_state.state)
                    except (ValueError, TypeError):
                        pass
            if restored_val is not None:
                self.coordinator.set_estimated_water_level(self._machine_id, restored_val)

    @property
    def native_value(self) -> float | None:
        """Return the estimated water level in ml."""
        return round(self.coordinator.get_estimated_water_level(self._machine_id), 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return reservoir attributes."""
        capacity = self.coordinator.get_tank_capacity(self._machine_id)
        current = self.coordinator.get_estimated_water_level(self._machine_id)
        pct = round((current / capacity) * 100.0, 1) if capacity > 0 else 0.0
        return {
            "capacity_ml": capacity,
            "percentage": pct,
            "water_level_sensor": self.machine.water_level if self.machine else None,
        }


class MorningWaterTankPercentageSensor(MorningEntity, RestoreSensor):
    """Sensor tracking water level as a percentage of tank capacity."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the water percentage sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = SensorEntityDescription(
            key="water_tank_percentage",
            name="Water Tank Percentage",
            has_entity_name=True,
            icon="mdi:water-percent",
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
        )
        self._attr_unique_id = f"{machine_id}_water_tank_percentage"

    async def async_added_to_hass(self) -> None:
        """Restore state on startup if not already seeded."""
        await super().async_added_to_hass()
        if not self.coordinator._water_level_seeded.get(self._machine_id, False):
            restored_pct = None
            last_sensor_data = await self.async_get_last_sensor_data()
            if last_sensor_data and last_sensor_data.native_value is not None:
                try:
                    restored_pct = float(last_sensor_data.native_value)
                except (ValueError, TypeError):
                    pass
            if restored_pct is None:
                last_state = await self.async_get_last_state()
                if last_state and last_state.state not in ("unknown", "unavailable"):
                    try:
                        restored_pct = float(last_state.state)
                    except (ValueError, TypeError):
                        pass
            if restored_pct is not None:
                capacity = float(self.coordinator.get_tank_capacity(self._machine_id))
                if capacity > 0:
                    restored_ml = round((restored_pct / 100.0) * capacity, 1)
                    self.coordinator.set_estimated_water_level(self._machine_id, restored_ml)

    @property
    def native_value(self) -> float | None:
        """Return current percentage level."""
        capacity = self.coordinator.get_tank_capacity(self._machine_id)
        if capacity <= 0:
            return 0.0
        current = self.coordinator.get_estimated_water_level(self._machine_id)
        return round((current / capacity) * 100.0, 1)


class MorningBrewWaterDispensedSensor(MorningEntity, RestoreSensor):
    """Sensor tracking water dispensed during brewing (live updates, sticky post-brew)."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the brew water dispensed sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = SensorEntityDescription(
            key="brew_water_dispensed",
            name="Brew Water Dispensed",
            has_entity_name=True,
            icon="mdi:water-pump",
            native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        )
        self._attr_unique_id = f"{machine_id}_brew_water_dispensed"
        self._restored_val: float | None = None

    async def async_added_to_hass(self) -> None:
        """Restore previous brew reading."""
        await super().async_added_to_hass()
        last_data = await self.async_get_last_sensor_data()
        if last_data and last_data.native_value is not None:
            try:
                self._restored_val = float(last_data.native_value)
            except (ValueError, TypeError):
                pass
        if self._restored_val is None:
            last_state = await self.async_get_last_state()
            if last_state and last_state.state not in ("unknown", "unavailable"):
                try:
                    self._restored_val = float(last_state.state)
                except (ValueError, TypeError):
                    pass

    @property
    def native_value(self) -> float | None:
        """Return live water output if brewing or last brew final output."""
        telem = getattr(self.coordinator, "live_telemetry", {}).get(self._machine_id)
        if telem is not None:
            return round(telem.water_output, 1)
        return self._restored_val

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extraction profile and stage tracking attributes."""
        attrs: dict[str, Any] = {}
        profile = self.coordinator.get_brew_profile(self._machine_id)
        if profile:
            attrs["extraction_profile"] = profile
        telem = getattr(self.coordinator, "live_telemetry", {}).get(self._machine_id)
        if telem:
            if telem.stages_seen:
                attrs["stages_seen"] = list(telem.stages_seen)
            if telem.source and telem.source != "none":
                attrs["telemetry_source"] = telem.source
        iot = getattr(self.coordinator, "iot_listener", None)
        if iot is not None and hasattr(iot, "is_connected"):
            attrs["iot_connected"] = bool(iot.is_connected)
        return attrs


class MorningBrewMassDispensedSensor(MorningEntity, RestoreSensor):
    """Sensor tracking mass dispensed during brewing (live updates, sticky post-brew)."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the brew mass dispensed sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = SensorEntityDescription(
            key="brew_mass_dispensed",
            name="Brew Mass Dispensed",
            has_entity_name=True,
            icon="mdi:scale",
            device_class=SensorDeviceClass.WEIGHT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
        )
        self._attr_unique_id = f"{machine_id}_brew_mass_dispensed"
        self._restored_val: float | None = None

    async def async_added_to_hass(self) -> None:
        """Restore previous brew reading."""
        await super().async_added_to_hass()
        last_data = await self.async_get_last_sensor_data()
        if last_data and last_data.native_value is not None:
            try:
                self._restored_val = float(last_data.native_value)
            except (ValueError, TypeError):
                pass
        if self._restored_val is None:
            last_state = await self.async_get_last_state()
            if last_state and last_state.state not in ("unknown", "unavailable"):
                try:
                    self._restored_val = float(last_state.state)
                except (ValueError, TypeError):
                    pass

    @property
    def native_value(self) -> float | None:
        """Return live mass output if brewing or last brew final output."""
        telem = getattr(self.coordinator, "live_telemetry", {}).get(self._machine_id)
        if telem is not None:
            return round(telem.mass_output, 1)
        return self._restored_val


class MorningBrewTemperatureSensor(MorningEntity, RestoreSensor):
    """Sensor tracking temperature during brew."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the brew temperature sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = SensorEntityDescription(
            key="brew_temperature",
            name="Brew Temperature",
            has_entity_name=True,
            icon="mdi:thermometer",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        )
        self._attr_unique_id = f"{machine_id}_brew_temperature"
        self._restored_val: int | None = None

    async def async_added_to_hass(self) -> None:
        """Restore previous brew reading."""
        await super().async_added_to_hass()
        last_data = await self.async_get_last_sensor_data()
        if last_data and last_data.native_value is not None:
            try:
                self._restored_val = int(last_data.native_value)
            except (ValueError, TypeError):
                pass
        if self._restored_val is None:
            last_state = await self.async_get_last_state()
            if last_state and last_state.state not in ("unknown", "unavailable"):
                try:
                    self._restored_val = int(float(last_state.state))
                except (ValueError, TypeError):
                    pass

    @property
    def native_value(self) -> int | None:
        """Return brew temperature."""
        telem = getattr(self.coordinator, "live_telemetry", {}).get(self._machine_id)
        if telem and telem.temperature > 0:
            return telem.temperature
        return self._restored_val


class MorningBrewStageSensor(MorningEntity, RestoreSensor):
    """Sensor tracking the active or last brew stage."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the brew stage sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = SensorEntityDescription(
            key="brew_stage",
            name="Brew Stage",
            has_entity_name=True,
            icon="mdi:progress-clock",
        )
        self._attr_unique_id = f"{machine_id}_brew_stage"

    async def async_added_to_hass(self) -> None:
        """Restore previous brew state and extraction profile."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.attributes:
            prof = last_state.attributes.get("extraction_profile")
            if prof and isinstance(prof, list):
                self.coordinator.set_restored_brew_profile(self._machine_id, prof)

    @property
    def native_value(self) -> str | None:
        """Return current or sticky brew stage."""
        telem = getattr(self.coordinator, "live_telemetry", {}).get(self._machine_id)
        if telem:
            return telem.stage.lower()
        return "idle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extraction profile and stage tracking attributes."""
        attrs: dict[str, Any] = {}
        profile = self.coordinator.get_brew_profile(self._machine_id)
        if profile:
            attrs["extraction_profile"] = profile
        telem = getattr(self.coordinator, "live_telemetry", {}).get(self._machine_id)
        if telem:
            if telem.stages_seen:
                attrs["stages_seen"] = list(telem.stages_seen)
            if telem.source and telem.source != "none":
                attrs["telemetry_source"] = telem.source
        iot = getattr(self.coordinator, "iot_listener", None)
        if iot is not None and hasattr(iot, "is_connected"):
            attrs["iot_connected"] = bool(iot.is_connected)
        return attrs


class MorningBrewBloomSensor(MorningEntity, SensorEntity):
    """Sensor tracking brew bloom lapse duration in seconds."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the brew bloom sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = SensorEntityDescription(
            key="brew_bloom_duration",
            name="Brew Bloom Duration",
            has_entity_name=True,
            icon="mdi:timer-outline",
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
        )
        self._attr_unique_id = f"{machine_id}_brew_bloom_duration"

    @property
    def native_value(self) -> int | None:
        """Return bloom duration in seconds."""
        telem = getattr(self.coordinator, "live_telemetry", {}).get(self._machine_id)
        if telem:
            return telem.bloom_lapse
        return 0


class MorningLifetimeWaterSensor(MorningEntity, RestoreSensor):
    """Sensor tracking cumulative lifetime water consumed by machine."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize lifetime water sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = SensorEntityDescription(
            key="lifetime_water_used",
            name="Lifetime Water Used",
            has_entity_name=True,
            icon="mdi:water-sync",
            device_class=SensorDeviceClass.VOLUME,
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfVolume.LITERS,
        )
        self._attr_unique_id = f"{machine_id}_lifetime_water_used"

    async def async_added_to_hass(self) -> None:
        """Restore previous cumulative water consumption on startup."""
        await super().async_added_to_hass()
        if self._machine_id not in self.coordinator.lifetime_water_levels:
            last_sensor_data = await self.async_get_last_sensor_data()
            if last_sensor_data and last_sensor_data.native_value is not None:
                try:
                    restored_liters = float(last_sensor_data.native_value)
                    self.coordinator.set_lifetime_water_ml(
                        self._machine_id, restored_liters * 1000.0
                    )
                except (ValueError, TypeError):
                    pass

    @property
    def native_value(self) -> float | None:
        """Return cumulative liters pumped."""
        ml = self.coordinator.get_lifetime_water_ml(self._machine_id)
        if self.machine and self.machine.total_water_ml > ml:
            ml = float(self.machine.total_water_ml)
        return round(ml / 1000.0, 2)


class MorningSlaveFirmwareSensor(MorningEntity, SensorEntity):
    """Sensor reporting STM32 / slave motor controller firmware version."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize slave firmware sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = SensorEntityDescription(
            key="slave_firmware",
            name="Motor Controller Firmware",
            has_entity_name=True,
            icon="mdi:chip",
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        self._attr_unique_id = f"{machine_id}_slave_firmware"

    @property
    def native_value(self) -> str | None:
        """Return slave firmware version string."""
        return self.machine.stm32_version if self.machine else None


class MorningFaultCodeSensor(MorningEntity, SensorEntity):
    """Sensor reporting machine error or fault code."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize fault code sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = SensorEntityDescription(
            key="fault_code",
            name="Fault Code",
            has_entity_name=True,
            icon="mdi:alert-circle-outline",
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        self._attr_unique_id = f"{machine_id}_fault_code"

    @property
    def native_value(self) -> str | None:
        """Return machine fault details or 'None'."""
        if not self.machine:
            return None
        return self.machine.fault_information or "None"
