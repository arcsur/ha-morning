"""Data models for the Morning Coffee Machine integration."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field, replace
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


@dataclass
class MorningLiveBrewTelemetry:
    """Represents live telemetry from an active or recent brew."""

    stage: str = "idle"  # idle, heating, blooming, brewing, done, cancel, error
    temperature: int = 0
    water_output: float = 0.0
    mass_output: float = 0.0
    bloom_lapse: int = 0
    is_brewing: bool = False
    last_updated: float = 0.0
    profile: list[dict[str, Any]] = field(default_factory=list)
    stages_seen: list[str] = field(default_factory=list)
    source: str = "none"  # mqtt, shadow, poll, or none


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
    child_lock: bool = False
    total_water_ml: int = 0
    stm32_version: str | None = None
    fault_information: str | None = None
    pump_flow_rate_k1: float | None = None
    pump_flow_rate_p1: float | None = None
    temperature: int | None = None
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

        # Extract nested brew info if present
        brew_data = data.get("brew") if isinstance(data.get("brew"), dict) else {}
        total_water_ml = int(brew_data.get("ml") or data.get("totalWaterMl") or 0)

        # Extract pump flow rates
        pump_rates = data.get("pumpFlowRate") if isinstance(data.get("pumpFlowRate"), dict) else {}
        if not pump_rates and isinstance(data.get("pumpFlowrate"), dict):
            pump_rates = data.get("pumpFlowrate", {})
        k1 = float(pump_rates.get("k1") or pump_rates.get("K1")) if (pump_rates.get("k1") or pump_rates.get("K1")) is not None else None
        p1 = float(pump_rates.get("p1") or pump_rates.get("P1")) if (pump_rates.get("p1") or pump_rates.get("P1")) is not None else None

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
            child_lock=bool(data.get("childLock", False)),
            total_water_ml=total_water_ml,
            stm32_version=data.get("stm32Version"),
            fault_information=data.get("faultInfomation") or data.get("faultInformation"),
            pump_flow_rate_k1=k1,
            pump_flow_rate_p1=p1,
            temperature=(
                int(data.get("temperature") or data.get("currentTemp") or data.get("current_temp") or 0)
                if (data.get("temperature") or data.get("currentTemp") or data.get("current_temp"))
                else None
            ),
            raw_data=data,
        )

    def with_shadow_doc(self, shadow_doc: dict[str, Any]) -> MorningMachine:
        """Return a new MorningMachine enriched with AWS IoT Thing Shadow reported settings."""
        if not isinstance(shadow_doc, dict):
            return self
        state = shadow_doc.get("state", shadow_doc)
        if not isinstance(state, dict):
            return self
        reported = state.get("reported", state)
        if not isinstance(reported, dict):
            return self
        settings = reported.get("settings", reported)
        if not isinstance(settings, dict):
            return self

        brew_data = settings.get("brew") if isinstance(settings.get("brew"), dict) else {}
        shadow_ml = int(brew_data.get("ml") or 0)
        shadow_count = int(brew_data.get("count") or 0)

        pump_rates = settings.get("pumpFlowrate") if isinstance(settings.get("pumpFlowrate"), dict) else {}
        if not pump_rates and isinstance(settings.get("pumpFlowRate"), dict):
            pump_rates = settings.get("pumpFlowRate", {})
        raw_k1 = pump_rates.get("k1") if pump_rates.get("k1") is not None else pump_rates.get("K1")
        raw_p1 = pump_rates.get("p1") if pump_rates.get("p1") is not None else pump_rates.get("P1")
        k1 = float(raw_k1) if raw_k1 is not None else self.pump_flow_rate_k1
        p1 = float(raw_p1) if raw_p1 is not None else self.pump_flow_rate_p1

        status_val = str(settings.get("status") or "").strip()
        water_lvl = str(settings.get("waterLevel") or "").strip()
        stm32_ver = settings.get("stm32Version") or self.stm32_version
        fault_info = (
            settings.get("faultInfomation")
            if "faultInfomation" in settings
            else settings.get("faultInformation", self.fault_information)
        )

        raw_limescale = settings.get("limescale") or settings.get("limeScale")
        limescale_val = int(raw_limescale) if raw_limescale is not None and str(raw_limescale).isdigit() else self.lime_scale

        raw_child_lock = settings.get("childLock")
        if isinstance(raw_child_lock, str):
            child_lock_val = raw_child_lock.strip().upper() in ("ON", "TRUE", "1")
        elif isinstance(raw_child_lock, bool):
            child_lock_val = raw_child_lock
        else:
            child_lock_val = self.child_lock

        return replace(
            self,
            status=status_val if status_val else self.status,
            water_level=water_lvl if water_lvl else self.water_level,
            lime_scale=limescale_val,
            brew_count=max(self.brew_count, shadow_count),
            total_water_ml=max(self.total_water_ml, shadow_ml),
            stm32_version=str(stm32_ver) if stm32_ver else self.stm32_version,
            fault_information=fault_info,
            pump_flow_rate_k1=k1,
            pump_flow_rate_p1=p1,
            child_lock=child_lock_val,
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
