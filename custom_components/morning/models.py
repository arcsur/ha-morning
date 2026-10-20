"""Data models for the Morning Coffee Machine integration."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from typing import Any


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """Extract and decode the payload from a JWT without external libraries."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload_b64 = parts[1]
        padding = "=" * ((4 - len(payload_b64) % 4) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64 + padding).decode("utf-8"))
    except Exception:
        return {}


@dataclass(frozen=True)
class MorningFirmware:
    """Represents firmware information for a machine."""

    current: str
    is_latest: bool = True
    latest_version: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MorningFirmware | None:
        """Create MorningFirmware from dictionary."""
        if not data:
            return None
        return cls(
            current=str(data.get("current", "unknown")),
            is_latest=bool(data.get("isLatest", True)),
            latest_version=data.get("latestVersion"),
        )


@dataclass(frozen=True)
class MorningMachine:
    """Represents a Morning Coffee Machine."""

    id: str
    name: str
    model: str
    firmware_version: str
    active: bool
    online: bool
    type: str
    sub_type: str
    recipe_slots: int
    status: str
    water_level: str
    lime_scale: int
    brew_count: int
    energy_save_timeout: int
    mac: str
    uuid: str
    icon: str | None = None
    photo: str | None = None
    firmware: MorningFirmware | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MorningMachine:
        """Create MorningMachine instance from API response dict."""
        firmware_dict = data.get("firmware")
        firmware = (
            MorningFirmware.from_dict(firmware_dict)
            if isinstance(firmware_dict, dict)
            else None
        )

        firmware_ver = (
            data.get("firmwareVersion")
            or (firmware.current if firmware else None)
            or "Unknown"
        )

        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name") or f"Morning Machine {data.get('id', '')}"),
            model=str(data.get("model", "Morning Machine")),
            firmware_version=firmware_ver,
            active=bool(data.get("active", True)),
            online=bool(data.get("online", False)),
            type=str(data.get("type", "COFFEE")),
            sub_type=str(data.get("subType", "STANDARD")),
            recipe_slots=int(data.get("recipeSlots", 10)),
            status=str(data.get("status", "UNKNOWN")),
            water_level=str(data.get("waterLevel", "UNKNOWN")),
            lime_scale=int(data.get("limeScale") or data.get("waterLimeScale") or 0),
            brew_count=int(data.get("brewCount", 0)),
            energy_save_timeout=int(data.get("energySaveTimeOut", 1800)),
            mac=str(data.get("mac", "")),
            uuid=str(data.get("uuid", "")),
            icon=data.get("icon"),
            photo=data.get("photo"),
            firmware=firmware,
            raw_data=data,
        )


@dataclass
class MorningAuthSession:
    """Represents an active AWS Cognito authentication session."""

    access_token: str
    id_token: str
    refresh_token: str
    expires_at: float
    email: str
    user_id: str | None = None

    def __post_init__(self) -> None:
        """Derive user_id from token claims if not explicitly provided."""
        if not self.user_id:
            payload = decode_jwt_payload(self.id_token) or decode_jwt_payload(self.access_token)
            self.user_id = payload.get("sub") or payload.get("cognito:username")

    @property
    def is_expired(self) -> bool:
        """Return True if the tokens have expired (with a 5-minute safety buffer)."""
        return time.time() >= (self.expires_at - 300)

    @classmethod
    def from_cognito_result(
        cls,
        result: dict[str, Any],
        email: str,
        refresh_token: str | None = None,
        user_id: str | None = None,
    ) -> MorningAuthSession:
        """Create auth session from Cognito InitiateAuth AuthenticationResult."""
        access_token = result["AccessToken"]
        id_token = result.get("IdToken", "")
        ref_tok = result.get("RefreshToken") or refresh_token or ""
        expires_in = int(result.get("ExpiresIn", 3600))
        expires_at = time.time() + expires_in

        return cls(
            access_token=access_token,
            id_token=id_token,
            refresh_token=ref_tok,
            expires_at=expires_at,
            email=email,
            user_id=user_id,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert session to dictionary for storage."""
        return {
            "access_token": self.access_token,
            "id_token": self.id_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "email": self.email,
            "user_id": self.user_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MorningAuthSession:
        """Restore session from dictionary."""
        return cls(
            access_token=data["access_token"],
            id_token=data["id_token"],
            refresh_token=data.get("refresh_token", ""),
            expires_at=float(data.get("expires_at", 0)),
            email=data.get("email", ""),
            user_id=data.get("user_id"),
        )
