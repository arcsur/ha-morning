"""Binary sensor platform for Morning Coffee Machine."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_MACHINE_IDS,
    DOMAIN,
    STATUS_BREWING,
    WATER_LEVEL_LOW,
)
from .coordinator import MorningDataUpdateCoordinator
from .entity import MorningEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Morning binary sensor entities based on config entry."""
    coordinator: MorningDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    machine_ids: list[str] = entry.data.get(CONF_MACHINE_IDS, [])

    entities: list[BinarySensorEntity] = []
    for mid in machine_ids:
        entities.extend(
            [
                MorningWaterLowBinarySensor(coordinator, mid),
                MorningConnectivityBinarySensor(coordinator, mid),
                MorningBrewingBinarySensor(coordinator, mid),
            ]
        )

    async_add_entities(entities)


class MorningWaterLowBinarySensor(MorningEntity, BinarySensorEntity):
    """Binary sensor indicating whether the water reservoir is low."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the water low binary sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = BinarySensorEntityDescription(
            key="water_low",
            name="Water Tank Low",
            has_entity_name=True,
            device_class=BinarySensorDeviceClass.PROBLEM,
        )
        self._attr_unique_id = f"{machine_id}_water_low"

    @property
    def is_on(self) -> bool | None:
        """Return True if water level is LOW (indicating a problem)."""
        if not self.machine:
            return None
        return self.machine.water_level.upper() == WATER_LEVEL_LOW

    @property
    def icon(self) -> str:
        """Return dynamic icon based on water level state."""
        return "mdi:water-alert" if self.is_on else "mdi:water-check"


class MorningConnectivityBinarySensor(MorningEntity, BinarySensorEntity):
    """Binary sensor indicating cloud/network connectivity of the machine."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the connectivity binary sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = BinarySensorEntityDescription(
            key="connectivity",
            name="Cloud Connection",
            has_entity_name=True,
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
        )
        self._attr_unique_id = f"{machine_id}_connectivity"

    @property
    def is_on(self) -> bool | None:
        """Return True if machine is connected to cloud."""
        return self.machine.online if self.machine else None


class MorningBrewingBinarySensor(MorningEntity, BinarySensorEntity):
    """Binary sensor indicating if the machine is actively brewing."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the brewing binary sensor."""
        super().__init__(coordinator, machine_id)
        self.entity_description = BinarySensorEntityDescription(
            key="brewing",
            name="Brewing",
            has_entity_name=True,
            device_class=BinarySensorDeviceClass.RUNNING,
        )
        self._attr_unique_id = f"{machine_id}_brewing"

    @property
    def is_on(self) -> bool | None:
        """Return True if machine is currently brewing."""
        if not self.machine:
            return None
        return self.machine.status.upper() == STATUS_BREWING

    @property
    def icon(self) -> str:
        """Return coffee cup icon."""
        return "mdi:coffee-maker" if self.is_on else "mdi:coffee-maker-outline"
