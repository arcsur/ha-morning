"""Config flow for Morning Coffee Machine integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .client import MorningAuthError, MorningClient, MorningConnectionError, MorningError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EMAIL,
    CONF_ID_TOKEN,
    CONF_MACHINE_IDS,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN_EXPIRES_AT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .models import MorningMachine

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)


class MorningConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Morning Coffee Machine."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._email: str | None = None
        self._password: str | None = None
        self._auth_session = None
        self._discovered_machines: list[MorningMachine] = []
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step where user provides email and password."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip().lower()
            password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(email)
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            client = MorningClient(session=session)

            try:
                auth_session = await client.authenticate(email, password)
                machines = await client.get_machines()

                if not machines:
                    _LOGGER.warning("No machines found for account: %s", email)
                    errors["base"] = "no_devices"
                else:
                    self._email = email
                    self._password = password
                    self._auth_session = auth_session
                    self._discovered_machines = machines

                    if len(machines) == 1:
                        machine = machines[0]
                        title = machine.name or f"Morning Machine ({machine.id})"
                        return self.async_create_entry(
                            title=title,
                            data={
                                CONF_EMAIL: email,
                                CONF_ACCESS_TOKEN: auth_session.access_token,
                                CONF_ID_TOKEN: auth_session.id_token,
                                CONF_REFRESH_TOKEN: auth_session.refresh_token,
                                CONF_TOKEN_EXPIRES_AT: auth_session.expires_at,
                                CONF_MACHINE_IDS: [machine.id],
                            },
                        )

                    return await self.async_step_select_machine()

            except MorningAuthError:
                _LOGGER.error("Invalid credentials provided for %s", email)
                errors["base"] = "invalid_auth"
            except MorningConnectionError:
                _LOGGER.error("Cannot connect to Morning cloud servers")
                errors["base"] = "cannot_connect"
            except MorningError as err:
                _LOGGER.error("Unexpected error during setup: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_select_machine(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle selecting which machine(s) to add when multiple are found."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_ids = user_input.get(CONF_MACHINE_IDS, [])
            if not selected_ids:
                errors["base"] = "no_machine_selected"
            elif self._email and self._auth_session:
                title = (
                    f"Morning ({len(selected_ids)} machines)"
                    if len(selected_ids) > 1
                    else next(
                        (m.name for m in self._discovered_machines if m.id in selected_ids),
                        f"Morning ({selected_ids[0]})",
                    )
                )
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_EMAIL: self._email,
                        CONF_ACCESS_TOKEN: self._auth_session.access_token,
                        CONF_ID_TOKEN: self._auth_session.id_token,
                        CONF_REFRESH_TOKEN: self._auth_session.refresh_token,
                        CONF_TOKEN_EXPIRES_AT: self._auth_session.expires_at,
                        CONF_MACHINE_IDS: selected_ids,
                    },
                )

        machine_options = {
            m.id: f"{m.name} ({m.model or 'MM-730'} - {m.id})"
            for m in self._discovered_machines
        }

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MACHINE_IDS,
                    default=list(machine_options.keys()),
                ): cv.multi_select(machine_options),
            }
        )

        return self.async_show_form(
            step_id="select_machine",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Handle reauthentication request when credentials or tokens expire."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        self._email = entry_data.get(CONF_EMAIL, "")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Dialog that prompts user to re-enter their password."""
        errors: dict[str, str] = {}

        if user_input is not None and self._email:
            password = user_input[CONF_PASSWORD]
            session = async_get_clientsession(self.hass)
            client = MorningClient(session=session)

            try:
                auth_session = await client.authenticate(self._email, password)
                if self._reauth_entry:
                    self.hass.config_entries.async_update_entry(
                        self._reauth_entry,
                        data={
                            **self._reauth_entry.data,
                            CONF_ACCESS_TOKEN: auth_session.access_token,
                            CONF_ID_TOKEN: auth_session.id_token,
                            CONF_REFRESH_TOKEN: auth_session.refresh_token,
                            CONF_TOKEN_EXPIRES_AT: auth_session.expires_at,
                        },
                    )
                    await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                    return self.async_abort(reason="reauth_successful")

            except MorningAuthError:
                errors["base"] = "invalid_auth"
            except MorningConnectionError:
                errors["base"] = "cannot_connect"
            except MorningError:
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_PASSWORD): cv.string,
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            description_placeholders={"email": self._email or ""},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return MorningOptionsFlowHandler(config_entry)


class MorningOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Morning integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=current_interval,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
