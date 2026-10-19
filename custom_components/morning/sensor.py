"""Sensor platform for Morning Coffee Machine."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
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
        return self.machine.status.lower()

    @property
    def icon(self) -> str:
        """Return dynamic icon depending on machine state."""
        if not self.machine:
            return "mdi:coffee-maker-outline"
        status = self.machine.status.upper()
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
