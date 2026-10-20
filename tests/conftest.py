"""Pytest configuration and Home Assistant test stubs."""

import sys
from typing import Any, TypeVar
from unittest.mock import MagicMock

_T = TypeVar("_T")
_CoordinatorT = TypeVar("_CoordinatorT")

# Stub homeassistant modules if not installed in current environment
if "homeassistant" not in sys.modules:
    try:
        import homeassistant  # noqa: F401
    except ImportError:
        class UpdateFailed(Exception):
            """Stub UpdateFailed exception."""

        class ConfigEntryAuthFailed(Exception):
            """Stub ConfigEntryAuthFailed exception."""

        class MockDataUpdateCoordinator[T]:
            """Stub DataUpdateCoordinator."""

            def __init__(self, hass, logger, *, name=None, update_interval=None, **kwargs):
                self.hass = hass
                self.logger = logger
                self.name = name
                self.update_interval = update_interval
                self.data = {}
                self.last_update_success = True

            async def _async_update_data(self):
                raise NotImplementedError

            async def async_request_refresh(self):
                self.data = await self._async_update_data()

        class MockCoordinatorEntity[CoordinatorT]:
            """Stub CoordinatorEntity."""

            _attr_has_entity_name = True

            def __init__(self, coordinator: CoordinatorT):
                self.coordinator = coordinator

        class MockConfigFlow:
            """Stub ConfigFlow."""

            def __init_subclass__(cls, **kwargs):
                super().__init_subclass__()

            def __init__(self):
                self.hass = None
                self.context = {}
                self.unique_id = None

            async def async_set_unique_id(self, unique_id: str, *, raise_on_progress: bool = True):
                self.unique_id = unique_id

            def _abort_if_unique_id_configured(self):
                pass

            def async_create_entry(self, *, title: str, data: dict[str, Any], options: dict[str, Any] | None = None):
                return {
                    "type": "create_entry",
                    "title": title,
                    "data": data,
                    "options": options or {},
                }

            def async_show_form(self, *, step_id: str, data_schema=None, errors=None, description_placeholders=None):
                return {
                    "type": "form",
                    "step_id": step_id,
                    "data_schema": data_schema,
                    "errors": errors or {},
                    "description_placeholders": description_placeholders,
                }

            def async_abort(self, *, reason: str, description_placeholders=None):
                return {
                    "type": "abort",
                    "reason": reason,
                    "description_placeholders": description_placeholders,
                }

        class MockOptionsFlow:
            """Stub OptionsFlow."""

            def __init__(self):
                self.hass = None

            def async_create_entry(self, *, title: str, data: dict[str, Any]):
                return {"type": "create_entry", "title": title, "data": data}

            def async_show_form(self, *, step_id: str, data_schema=None, errors=None):
                return {"type": "form", "step_id": step_id, "data_schema": data_schema, "errors": errors or {}}

        ha_mock = MagicMock()
        ha_mock.const.Platform = MagicMock()
        ha_mock.const.Platform.SENSOR = "sensor"
        ha_mock.const.Platform.BINARY_SENSOR = "binary_sensor"
        ha_mock.const.Platform.NUMBER = "number"
        ha_mock.const.Platform.BUTTON = "button"
        ha_mock.const.UnitOfTime.SECONDS = "s"

        sys.modules["homeassistant"] = ha_mock
        sys.modules["homeassistant.const"] = ha_mock.const
        sys.modules["homeassistant.core"] = ha_mock.core
        sys.modules["homeassistant.core"].callback = lambda f: f
        sys.modules["homeassistant.config_entries"] = ha_mock.config_entries
        sys.modules["homeassistant.config_entries"].ConfigFlow = MockConfigFlow
        sys.modules["homeassistant.config_entries"].OptionsFlow = MockOptionsFlow
        sys.modules["homeassistant.exceptions"] = ha_mock.exceptions
        sys.modules["homeassistant.exceptions"].ConfigEntryAuthFailed = ConfigEntryAuthFailed
        sys.modules["homeassistant.data_entry_flow"] = ha_mock.data_entry_flow
        sys.modules["homeassistant.helpers"] = ha_mock.helpers
        sys.modules["homeassistant.helpers.aiohttp_client"] = ha_mock.helpers.aiohttp_client
        sys.modules["homeassistant.helpers.config_validation"] = ha_mock.helpers.config_validation
        sys.modules["homeassistant.helpers.config_validation"].string = str
        sys.modules["homeassistant.helpers.config_validation"].multi_select = lambda opts: lambda val: val
        sys.modules["homeassistant.helpers.device_registry"] = ha_mock.helpers.device_registry
        sys.modules["homeassistant.helpers.entity_platform"] = ha_mock.helpers.entity_platform
        sys.modules["homeassistant.helpers.update_coordinator"] = ha_mock.helpers.update_coordinator
        sys.modules["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = MockDataUpdateCoordinator
        sys.modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = MockCoordinatorEntity
        sys.modules["homeassistant.helpers.update_coordinator"].UpdateFailed = UpdateFailed
        sys.modules["homeassistant.components"] = ha_mock.components
        sys.modules["homeassistant.components.sensor"] = ha_mock.components.sensor
        sys.modules["homeassistant.components.binary_sensor"] = ha_mock.components.binary_sensor
        sys.modules["homeassistant.components.number"] = ha_mock.components.number
        sys.modules["homeassistant.components.button"] = ha_mock.components.button
