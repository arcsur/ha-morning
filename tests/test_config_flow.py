"""Unit tests for Morning Config Flow."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.morning.client import MorningAuthError, MorningConnectionError
from custom_components.morning.config_flow import MorningConfigFlow
from custom_components.morning.const import (
    CONF_EMAIL,
    CONF_MACHINE_IDS,
    CONF_PASSWORD,
    CONF_USER_ID,
)
from custom_components.morning.models import MorningAuthSession, MorningMachine


class TestMorningConfigFlow(unittest.IsolatedAsyncioTestCase):
    """Test Morning ConfigFlow steps."""

    def setUp(self):
        """Set up test fixtures."""
        self.flow = MorningConfigFlow()
        self.flow.hass = MagicMock()

    async def test_step_user_show_form(self):
        """Test initial user step shows form when user_input is None."""
        result = await self.flow.async_step_user(user_input=None)
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "user")
        self.assertEqual(result["errors"], {})

    @patch("custom_components.morning.config_flow.MorningClient")
    async def test_step_user_single_machine_success(self, mock_client_cls):
        """Test single machine account connects and creates entry immediately."""
        mock_client = mock_client_cls.return_value
        mock_auth_session = MorningAuthSession(
            access_token="acc",
            id_token="id",
            refresh_token="ref",
            expires_at=9999999999.0,
            email="user@example.com",
            user_id="user_uuid_123",
        )
        mock_client.authenticate = AsyncMock(return_value=mock_auth_session)
        mock_machine = MorningMachine.from_dict(
            {"id": "M_1234", "name": "Kitchen Morning"}
        )
        mock_client.get_machines = AsyncMock(return_value=[mock_machine])

        user_input = {
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "Password123!",
        }

        result = await self.flow.async_step_user(user_input=user_input)
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "Kitchen Morning")
        self.assertEqual(result["data"][CONF_EMAIL], "user@example.com")
        self.assertEqual(result["data"][CONF_USER_ID], "user_uuid_123")
        self.assertEqual(result["data"][CONF_MACHINE_IDS], ["M_1234"])

    @patch("custom_components.morning.config_flow.MorningClient")
    async def test_step_user_invalid_auth(self, mock_client_cls):
        """Test invalid credentials shows error."""
        mock_client = mock_client_cls.return_value
        mock_client.authenticate = AsyncMock(
            side_effect=MorningAuthError("Incorrect password")
        )

        user_input = {
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "WrongPassword",
        }

        result = await self.flow.async_step_user(user_input=user_input)
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"base": "invalid_auth"})

    @patch("custom_components.morning.config_flow.MorningClient")
    async def test_step_user_cannot_connect(self, mock_client_cls):
        """Test connection failure shows cannot_connect error."""
        mock_client = mock_client_cls.return_value
        mock_client.authenticate = AsyncMock(
            side_effect=MorningConnectionError("Network down")
        )

        user_input = {
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "Password123!",
        }

        result = await self.flow.async_step_user(user_input=user_input)
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"base": "cannot_connect"})

    @patch("custom_components.morning.config_flow.MorningClient")
    async def test_step_user_no_devices(self, mock_client_cls):
        """Test account with no machines shows no_devices error."""
        mock_client = mock_client_cls.return_value
        mock_auth_session = MorningAuthSession(
            access_token="acc",
            id_token="id",
            refresh_token="ref",
            expires_at=9999999999.0,
            email="user@example.com",
        )
        mock_client.authenticate = AsyncMock(return_value=mock_auth_session)
        mock_client.get_machines = AsyncMock(return_value=[])

        user_input = {
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "Password123!",
        }

        result = await self.flow.async_step_user(user_input=user_input)
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"base": "no_devices"})


if __name__ == "__main__":
    unittest.main()
