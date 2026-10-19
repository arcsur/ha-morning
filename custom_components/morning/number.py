"""Number platform for Morning Coffee Machine."""

from __future__ import annotations

import logging

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MACHINE_IDS, DOMAIN
from .coordinator import MorningDataUpdateCoordinator
from .entity import MorningEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Morning number entities based on config entry."""
    coordinator: MorningDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    machine_ids: list[str] = entry.data.get(CONF_MACHINE_IDS, [])

    entities: list[NumberEntity] = []
    for mid in machine_ids:
        entities.append(MorningStandbyTimeoutNumber(coordinator, mid))

    async_add_entities(entities)


class MorningStandbyTimeoutNumber(MorningEntity, NumberEntity):
    """Number entity allowing adjustment of the machine's standby energy saving timeout."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the standby timeout number entity."""
        super().__init__(coordinator, machine_id)
        self.entity_description = NumberEntityDescription(
            key="standby_timeout_setting",
            name="Standby Timeout Setting",
            has_entity_name=True,
            icon="mdi:timer-cog-outline",
            device_class=NumberDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            native_min_value=300,   # 5 minutes
            native_max_value=7200,  # 2 hours
            native_step=60,         # 1 minute steps
            mode=NumberMode.BOX,
        )
        self._attr_unique_id = f"{machine_id}_standby_timeout_setting"

    @property
    def native_value(self) -> float | None:
        """Return the current standby timeout value."""
        if not self.machine:
            return None
        return float(self.machine.energy_save_timeout)

    async def async_set_native_value(self, value: float) -> None:
        """Update the standby timeout setting on the cloud and machine."""
        timeout_int = int(value)
        _LOGGER.info(
            "Changing standby timeout for machine %s to %d seconds",
            self._machine_id,
            timeout_int,
        )
        await self.coordinator.client.set_standby_timeout(self._machine_id, timeout_int)
        await self.coordinator.async_request_refresh()
