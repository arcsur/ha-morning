"""Asynchronous API client for Morning Coffee Machine cloud services."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    API_USER_AGENT,
    COGNITO_CLIENT_ID,
    COGNITO_CLIENT_SECRET,
    COGNITO_ENDPOINT,
)
from .models import MorningAuthSession, MorningMachine

_LOGGER = logging.getLogger(__name__)


class MorningError(Exception):
    """Base exception for Morning integration errors."""


class MorningAuthError(MorningError):
    """Exception raised when authentication fails."""


class MorningConnectionError(MorningError):
    """Exception raised when connection to the Morning cloud fails."""


class MorningDeviceNotFoundError(MorningError):
    """Exception raised when a requested machine is not found."""


class MorningApiError(MorningError):
    """Exception raised when the Morning API returns an error response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Initialize MorningApiError with message and optional status code."""
        super().__init__(message)
        self.status_code = status_code


class MorningClient:
    """Client for interacting with the Morning cloud backend."""

    def __init__(
        self,
        session: aiohttp.ClientSession | None = None,
        auth_session: MorningAuthSession | None = None,
    ) -> None:
        """Initialize MorningClient."""
        self._session = session
        self._auth_session = auth_session
        self._owns_session = False

    @property
    def auth_session(self) -> MorningAuthSession | None:
        """Return the current authentication session."""
        return self._auth_session

    def _get_secret_hash(self, username: str) -> str:
        """Compute the AWS Cognito SECRET_HASH using HMAC-SHA256."""
        message = (username + COGNITO_CLIENT_ID).encode("utf-8")
        key = COGNITO_CLIENT_SECRET.encode("utf-8")
        digest = hmac.new(key, message, hashlib.sha256).digest()
        return base64.b64encode(digest).decode("utf-8")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return or create an aiohttp ClientSession."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Close the internal session if owned."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    async def authenticate(self, email: str, password: str) -> MorningAuthSession:
        """Authenticate with AWS Cognito using email and password."""
        session = await self._get_session()
        secret_hash = self._get_secret_hash(email)

        payload = {
            "AuthFlow": "USER_PASSWORD_AUTH",
            "ClientId": COGNITO_CLIENT_ID,
            "AuthParameters": {
                "USERNAME": email,
                "PASSWORD": password,
                "SECRET_HASH": secret_hash,
            },
        }

        headers = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            "User-Agent": API_USER_AGENT,
        }

        try:
            async with session.post(
                COGNITO_ENDPOINT, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                body = await response.json(content_type=None)
                if response.status != 200:
                    err_type = body.get("__type", "UnknownError")
                    err_msg = body.get("message", "Authentication failed")
                    _LOGGER.error("Cognito authentication failed: %s (%s)", err_msg, err_type)
                    raise MorningAuthError(f"Cognito auth error: {err_msg} ({err_type})")

                auth_result = body.get("AuthenticationResult")
                if not auth_result or "AccessToken" not in auth_result:
                    raise MorningAuthError("Authentication succeeded but no tokens received")

                auth_session = MorningAuthSession.from_cognito_result(auth_result, email)
                self._auth_session = auth_session
                _LOGGER.debug("Successfully authenticated Morning user: %s", email)
                return auth_session

        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to connect to Cognito authentication service: %s", err)
            raise MorningConnectionError(f"Connection error during auth: {err}") from err

    async def refresh_tokens(self) -> MorningAuthSession:
        """Refresh the access and ID tokens using the refresh token."""
        if not self._auth_session or not self._auth_session.refresh_token:
            raise MorningAuthError("No refresh token available to refresh authentication")

        session = await self._get_session()

        # Build candidate usernames to try for REFRESH_TOKEN_AUTH.
        # AWS Cognito requires USERNAME in AuthParameters when the app client has a secret.
        # Depending on Cognito configuration, it may expect the user's sub UUID or the email alias.
        candidates: list[str] = []
        if self._auth_session.user_id:
            candidates.append(self._auth_session.user_id)
        if self._auth_session.email and self._auth_session.email not in candidates:
            candidates.append(self._auth_session.email)

        if not candidates:
            raise MorningAuthError("No username or email available to refresh authentication")

        headers = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            "User-Agent": API_USER_AGENT,
        }

        last_error_type = ""
        last_error_msg = ""

        for candidate in candidates:
            secret_hash = self._get_secret_hash(candidate)
            payload = {
                "AuthFlow": "REFRESH_TOKEN_AUTH",
                "ClientId": COGNITO_CLIENT_ID,
                "AuthParameters": {
                    "REFRESH_TOKEN": self._auth_session.refresh_token,
                    "SECRET_HASH": secret_hash,
                    "USERNAME": candidate,
                },
            }

            try:
                async with session.post(
                    COGNITO_ENDPOINT,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    body = await response.json(content_type=None)
                    if response.status == 200:
                        auth_result = body.get("AuthenticationResult")
                        if not auth_result or "AccessToken" not in auth_result:
                            raise MorningAuthError("Token refresh succeeded but no tokens returned")

                        new_session = MorningAuthSession.from_cognito_result(
                            auth_result,
                            self._auth_session.email,
                            refresh_token=self._auth_session.refresh_token,
                            user_id=self._auth_session.user_id
                            or (candidate if candidate != self._auth_session.email else None),
                        )
                        self._auth_session = new_session
                        _LOGGER.debug(
                            "Successfully refreshed tokens using username %s for user: %s",
                            candidate,
                            self._auth_session.email,
                        )
                        return new_session

                    last_error_type = body.get("__type", "UnknownError")
                    last_error_msg = body.get("message", "Token refresh failed")
                    _LOGGER.warning(
                        "Cognito token refresh attempt with username '%s' failed: %s (%s)",
                        candidate,
                        last_error_msg,
                        last_error_type,
                    )
            except aiohttp.ClientError as err:
                _LOGGER.error("Connection error during token refresh: %s", err)
                raise MorningConnectionError(f"Connection error during token refresh: {err}") from err

        _LOGGER.error("All token refresh attempts failed: %s (%s)", last_error_msg, last_error_type)
        raise MorningAuthError(f"Token refresh failed: {last_error_msg} ({last_error_type})")

    async def _ensure_valid_token(self) -> str:
        """Ensure token is valid and return ID token for Authorization header."""
        if not self._auth_session:
            raise MorningAuthError("Client is not authenticated")

        if self._auth_session.is_expired:
            _LOGGER.debug("Token expired or nearing expiry; refreshing...")
            await self.refresh_tokens()

        return self._auth_session.id_token

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: Any | None = None,
        retry_on_auth_failure: bool = True,
    ) -> Any:
        """Make an authenticated HTTP request to the Morning API."""
        session = await self._get_session()
        token = await self._ensure_valid_token()

        url = f"{API_BASE_URL}{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": API_USER_AGENT,
            "Accept": "application/json",
        }
        if json_data is not None:
            headers["Content-Type"] = "application/json"

        try:
            async with session.request(
                method,
                url,
                params=params,
                json=json_data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                # Handle unauthorized / token expired
                if response.status in (401, 403) and retry_on_auth_failure:
                    _LOGGER.info("Received HTTP %s, attempting token refresh and retry", response.status)
                    await self.refresh_tokens()
                    return await self._request(
                        method, endpoint, params=params, json_data=json_data, retry_on_auth_failure=False
                    )

                if response.status == 204:
                    return None

                try:
                    data = await response.json(content_type=None)
                except Exception:
                    data = await response.text()

                if response.status >= 400:
                    msg = (
                        data.get("message", f"API error HTTP {response.status}")
                        if isinstance(data, dict)
                        else str(data)
                    )
                    _LOGGER.error("API error for %s %s: status=%s, msg=%s", method, endpoint, response.status, msg)
                    if response.status in (401, 403):
                        raise MorningAuthError(f"Unauthorized: {msg}")
                    if response.status == 404:
                        raise MorningDeviceNotFoundError(f"Resource not found: {msg}")
                    raise MorningApiError(msg, status_code=response.status)

                return data

        except aiohttp.ClientError as err:
            _LOGGER.error("Connection error for %s %s: %s", method, endpoint, err)
            raise MorningConnectionError(f"Connection error to {endpoint}: {err}") from err

    async def get_machines(self) -> list[MorningMachine]:
        """Fetch all coffee machines linked to the user account."""
        data = await self._request("GET", "machine/user")
        if not isinstance(data, list):
            _LOGGER.warning("Unexpected response format for machine/user: %s", data)
            return []

        machines = [MorningMachine.from_dict(item) for item in data if isinstance(item, dict)]
        _LOGGER.debug("Found %d machine(s) linked to account", len(machines))
        return machines

    async def get_machine(self, machine_id: str) -> MorningMachine:
        """Fetch telemetry and details for a specific machine."""
        data = await self._request("GET", f"machine/{machine_id}")
        if not isinstance(data, dict):
            raise MorningDeviceNotFoundError(f"Machine {machine_id} details could not be parsed")
        return MorningMachine.from_dict(data)

    async def set_standby_timeout(self, machine_id: str, timeout_seconds: int) -> bool:
        """Set the machine auto-off standby timeout (in seconds)."""
        _LOGGER.debug("Setting standby timeout for %s to %d seconds", machine_id, timeout_seconds)
        await self._request(
            "PUT",
            f"machine/{machine_id}/energy",
            params={"timeOut": int(timeout_seconds)},
        )
        return True

    async def set_machine_name(self, machine_id: str, name: str) -> bool:
        """Update machine user-friendly name."""
        _LOGGER.debug("Setting name for %s to '%s'", machine_id, name)
        await self._request(
            "PUT",
            f"machine/{machine_id}/name",
            params={"name": str(name)},
        )
        return True

    async def reset_machine(self) -> bool:
        """Send reset command to machine."""
        _LOGGER.info("Sending reset command to machine")
        await self._request("PUT", "machine/reset")
        return True

    async def check_updates(self, machine_type: str = "COFFEE") -> dict[str, Any]:
        """Check for firmware updates for coffee machines."""
        _LOGGER.debug("Checking updates for type=%s", machine_type)
        data = await self._request("GET", "machine/check-updates", params={"type": machine_type})
        return data if isinstance(data, dict) else {}
