"""Unit tests for Morning cloud API client."""

import base64
import hashlib
import hmac
import unittest
from unittest.mock import AsyncMock, MagicMock

from aiohttp import ClientError

from custom_components.morning.client import (
    MorningAuthError,
    MorningClient,
    MorningConnectionError,
)
from custom_components.morning.const import (
    COGNITO_CLIENT_ID,
    COGNITO_CLIENT_SECRET,
    COGNITO_ENDPOINT,
)
from custom_components.morning.models import MorningAuthSession


class TestMorningClient(unittest.IsolatedAsyncioTestCase):
    """Test MorningClient methods and error handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.email = "barista@example.com"
        self.password = "Espresso123!"
        self.session = MagicMock()
        self.session.closed = False
        self.client = MorningClient(session=self.session)

    def test_secret_hash_calculation(self):
        """Verify AWS Cognito SECRET_HASH HMAC-SHA256 calculation."""
        expected_msg = (self.email + COGNITO_CLIENT_ID).encode("utf-8")
        expected_key = COGNITO_CLIENT_SECRET.encode("utf-8")
        expected_hash = base64.b64encode(
            hmac.new(expected_key, expected_msg, hashlib.sha256).digest()
        ).decode("utf-8")

        computed = self.client._get_secret_hash(self.email)
        self.assertEqual(computed, expected_hash)

    async def test_authenticate_success(self):
        """Test successful authentication with AWS Cognito."""
        cognito_response = {
            "AuthenticationResult": {
                "AccessToken": "mock_access_token",
                "IdToken": "mock_id_token",
                "RefreshToken": "mock_refresh_token",
                "ExpiresIn": 3600,
            }
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=cognito_response)

        # Context manager mock for post
        self.session.post.return_value.__aenter__.return_value = mock_resp

        auth_session = await self.client.authenticate(self.email, self.password)

        self.assertEqual(auth_session.access_token, "mock_access_token")
        self.assertEqual(auth_session.id_token, "mock_id_token")
        self.assertEqual(auth_session.refresh_token, "mock_refresh_token")
        self.assertEqual(auth_session.email, self.email)
        self.assertFalse(auth_session.is_expired)

        # Verify call arguments
        self.session.post.assert_called_once()
        call_args, call_kwargs = self.session.post.call_args
        self.assertEqual(call_args[0], COGNITO_ENDPOINT)
        self.assertEqual(call_kwargs["json"]["AuthFlow"], "USER_PASSWORD_AUTH")
        self.assertEqual(call_kwargs["json"]["ClientId"], COGNITO_CLIENT_ID)
        self.assertEqual(
            call_kwargs["json"]["AuthParameters"]["USERNAME"], self.email
        )
        self.assertEqual(
            call_kwargs["json"]["AuthParameters"]["PASSWORD"], self.password
        )

    async def test_authenticate_invalid_credentials(self):
        """Test authentication error handling on invalid credentials."""
        mock_resp = AsyncMock()
        mock_resp.status = 400
        mock_resp.json = AsyncMock(
            return_value={
                "__type": "NotAuthorizedException",
                "message": "Incorrect username or password.",
            }
        )
        self.session.post.return_value.__aenter__.return_value = mock_resp

        with self.assertRaises(MorningAuthError) as ctx:
            await self.client.authenticate(self.email, "WrongPassword")
        self.assertIn("NotAuthorizedException", str(ctx.exception))

    async def test_authenticate_connection_error(self):
        """Test connection failure during authentication."""
        self.session.post.side_effect = ClientError("DNS resolution failed")

        with self.assertRaises(MorningConnectionError):
            await self.client.authenticate(self.email, self.password)

    async def test_refresh_tokens_success_with_user_id(self):
        """Test refreshing tokens with user_id sub claim."""
        user_uuid = "896ae5fc-40b1-707f-5047-bc86f9fc02a8"
        self.client._auth_session = MorningAuthSession(
            access_token="old_access",
            id_token="old_id",
            refresh_token="existing_refresh_token",
            expires_at=0.0,
            email=self.email,
            user_id=user_uuid,
        )

        cognito_response = {
            "AuthenticationResult": {
                "AccessToken": "new_access_token",
                "IdToken": "new_id_token",
                "ExpiresIn": 3600,
            }
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=cognito_response)
        self.session.post.return_value.__aenter__.return_value = mock_resp

        new_session = await self.client.refresh_tokens()
        self.assertEqual(new_session.access_token, "new_access_token")
        self.assertEqual(new_session.id_token, "new_id_token")
        self.assertEqual(new_session.refresh_token, "existing_refresh_token")
        self.assertEqual(new_session.user_id, user_uuid)

        # Verify call payload had USERNAME and SECRET_HASH for user_id
        _, call_kwargs = self.session.post.call_args
        auth_params = call_kwargs["json"]["AuthParameters"]
        self.assertEqual(auth_params["USERNAME"], user_uuid)
        self.assertEqual(auth_params["REFRESH_TOKEN"], "existing_refresh_token")
        self.assertEqual(auth_params["SECRET_HASH"], self.client._get_secret_hash(user_uuid))

    async def test_refresh_tokens_fallback_to_email_on_error(self):
        """Test refreshing tokens falls back to email if user_id attempt fails."""
        user_uuid = "896ae5fc-40b1-707f-5047-bc86f9fc02a8"
        self.client._auth_session = MorningAuthSession(
            access_token="old_access",
            id_token="old_id",
            refresh_token="existing_refresh_token",
            expires_at=0.0,
            email=self.email,
            user_id=user_uuid,
        )

        # First call fails with NotAuthorizedException, second call succeeds
        mock_resp_fail = AsyncMock()
        mock_resp_fail.status = 400
        mock_resp_fail.json = AsyncMock(
            return_value={
                "__type": "NotAuthorizedException",
                "message": "Unable to verify secret hash for client",
            }
        )

        mock_resp_success = AsyncMock()
        mock_resp_success.status = 200
        mock_resp_success.json = AsyncMock(
            return_value={
                "AuthenticationResult": {
                    "AccessToken": "new_access_token",
                    "IdToken": "new_id_token",
                    "ExpiresIn": 3600,
                }
            }
        )

        # Context manager returns fail on first call, success on second
        self.session.post.return_value.__aenter__.side_effect = [
            mock_resp_fail,
            mock_resp_success,
        ]

        new_session = await self.client.refresh_tokens()
        self.assertEqual(new_session.access_token, "new_access_token")
        self.assertEqual(self.session.post.call_count, 2)

        # Second call should have used email
        _, second_call_kwargs = self.session.post.call_args_list[1]
        second_auth_params = second_call_kwargs["json"]["AuthParameters"]
        self.assertEqual(second_auth_params["USERNAME"], self.email)
        self.assertEqual(second_auth_params["SECRET_HASH"], self.client._get_secret_hash(self.email))

    async def test_refresh_tokens_all_candidates_fail(self):
        """Test refreshing tokens raises MorningAuthError when all candidates fail."""
        self.client._auth_session = MorningAuthSession(
            access_token="old_access",
            id_token="old_id",
            refresh_token="existing_refresh_token",
            expires_at=0.0,
            email=self.email,
            user_id="bad_uuid",
        )

        mock_resp_fail = AsyncMock()
        mock_resp_fail.status = 400
        mock_resp_fail.json = AsyncMock(
            return_value={
                "__type": "NotAuthorizedException",
                "message": "Invalid Refresh Token",
            }
        )
        self.session.post.return_value.__aenter__.return_value = mock_resp_fail

        with self.assertRaises(MorningAuthError):
            await self.client.refresh_tokens()

    async def test_get_machines_success(self):
        """Test fetching list of user machines."""
        self.client._auth_session = MorningAuthSession(
            access_token="acc",
            id_token="id",
            refresh_token="ref",
            expires_at=9999999999.0,
            email=self.email,
        )

        mock_machines_payload = [
            {
                "id": "M_AC67B25AC974",
                "name": "Kitchen Machine",
                "model": "MM-730",
                "firmwareVersion": "1.2.0",
                "active": True,
                "online": True,
                "type": "COFFEE",
                "status": "READY",
                "waterLevel": "NORMAL",
                "limeScale": 100,
                "brewCount": 42,
                "energySaveTimeOut": 1800,
                "mac": "AC:67:B2:5A:C9:74",
                "uuid": "FA2E9CAB-3178-D61A-1D29-A0974B2DEA9A",
            }
        ]

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_machines_payload)
        self.session.request.return_value.__aenter__.return_value = mock_resp

        machines = await self.client.get_machines()
        self.assertEqual(len(machines), 1)
        self.assertEqual(machines[0].id, "M_AC67B25AC974")
        self.assertEqual(machines[0].name, "Kitchen Machine")
        self.assertEqual(machines[0].status, "READY")
        self.assertEqual(machines[0].water_level, "NORMAL")
        self.assertEqual(machines[0].brew_count, 42)

    async def test_set_standby_timeout(self):
        """Test updating standby energy timeout."""
        self.client._auth_session = MorningAuthSession(
            access_token="acc",
            id_token="id",
            refresh_token="ref",
            expires_at=9999999999.0,
            email=self.email,
        )

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"status": "OK"})
        self.session.request.return_value.__aenter__.return_value = mock_resp

        success = await self.client.set_standby_timeout("M_AC67B25AC974", 3600)
        self.assertTrue(success)

        call_args, call_kwargs = self.session.request.call_args
        self.assertEqual(call_args[0], "PUT")
        self.assertIn("machine/M_AC67B25AC974/energy", call_args[1])
        self.assertEqual(call_kwargs["params"], {"timeOut": 3600})

    async def test_reset_machine(self):
        """Test sending machine reset command."""
        self.client._auth_session = MorningAuthSession(
            access_token="acc",
            id_token="id",
            refresh_token="ref",
            expires_at=9999999999.0,
            email=self.email,
        )

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"status": "OK"})
        self.session.request.return_value.__aenter__.return_value = mock_resp

        success = await self.client.reset_machine()
        self.assertTrue(success)

        call_args, call_kwargs = self.session.request.call_args
        self.assertEqual(call_args[0], "PUT")
        self.assertIn("machine/reset", call_args[1])


if __name__ == "__main__":
    unittest.main()
