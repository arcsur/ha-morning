"""Base entity definition for Morning Coffee Machine."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MorningDataUpdateCoordinator
from .models import MorningMachine


class MorningEntity(CoordinatorEntity[MorningDataUpdateCoordinator]):
    """Defines a base entity for Morning Coffee Machines."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        machine_id: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._machine_id = machine_id

    @property
    def machine(self) -> MorningMachine | None:
        """Return the current machine data from the coordinator."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._machine_id)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.machine is not None
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this Morning machine."""
        machine = self.machine
        name = (machine.name if machine else None) or f"Morning Machine ({self._machine_id})"
        model = (machine.model if machine else None) or "Morning Machine (MM-730)"
        sw_version = machine.firmware_version if machine else None

        connections: set[tuple[str, str]] = set()
        if machine and machine.mac:
            connections.add((CONNECTION_NETWORK_MAC, machine.mac))

        return DeviceInfo(
            identifiers={(DOMAIN, self._machine_id)},
            name=name,
            manufacturer="Morning",
            model=model,
            sw_version=sw_version,
            connections=connections,
            configuration_url="https://drinkmorning.com",
        )
