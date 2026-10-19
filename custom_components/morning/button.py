"""Button platform for Morning Coffee Machine."""

from __future__ import annotations

import logging

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
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
    """Set up Morning button entities based on config entry."""
    coordinator: MorningDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    machine_ids: list[str] = entry.data.get(CONF_MACHINE_IDS, [])

    entities: list[ButtonEntity] = []
    for mid in machine_ids:
        entities.extend(
            [
                MorningResetButton(coordinator, mid),
                MorningCheckUpdatesButton(coordinator, mid),
            ]
        )

    async_add_entities(entities)


class MorningResetButton(MorningEntity, ButtonEntity):
    """Button to trigger a reset on the Morning machine."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the reset button."""
        super().__init__(coordinator, machine_id)
        self.entity_description = ButtonEntityDescription(
            key="reset",
            name="Reset Machine",
            has_entity_name=True,
            icon="mdi:restart",
            device_class=ButtonDeviceClass.RESTART,
        )
        self._attr_unique_id = f"{machine_id}_reset"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Sending reset command for Morning machine %s", self._machine_id)
        await self.coordinator.client.reset_machine()
        await self.coordinator.async_request_refresh()


class MorningCheckUpdatesButton(MorningEntity, ButtonEntity):
    """Button to check for firmware updates."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the check updates button."""
        super().__init__(coordinator, machine_id)
        self.entity_description = ButtonEntityDescription(
            key="check_updates",
            name="Check Firmware Updates",
            has_entity_name=True,
            icon="mdi:update",
            device_class=ButtonDeviceClass.UPDATE,
        )
        self._attr_unique_id = f"{machine_id}_check_updates"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Checking firmware updates for Morning machine %s", self._machine_id)
        machine = self.machine
        machine_type = machine.type if machine else "COFFEE"
        await self.coordinator.client.check_updates(machine_type=machine_type)
        await self.coordinator.async_request_refresh()
