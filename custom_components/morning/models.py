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


@dataclass
class MorningRecipe:
    """Represents a brew recipe / profile for the Morning machine."""

    id: int = 0
    name: str = "Morning from Home Assistant"
    roaster_name: str = ""
    owner_type: str = "USER_RECIPE"
    type: str = "COFFEE_RECIPE"
    temperature: int = 94
    mass_output: int = 40
    water_output: int = 0
    bloom_duration: int | None = None
    stages: list[dict[str, int]] = field(
        default_factory=lambda: [
            {"id": 0, "output": 0, "pressure": 3},
            {"id": 1, "output": 5, "pressure": 7},
            {"id": 2, "output": 35, "pressure": 5},
        ]
    )
    is_favorite: bool = False
    source: str = "user"  # machine, favorite, recent, user, roaster, local

    @property
    def bloom_enabled(self) -> bool:
        """Return True if recipe has a positive bloom duration."""
        return self.bloom_duration is not None and self.bloom_duration > 0

    @property
    def bypass_enabled(self) -> bool:
        """Return True if recipe has bypass water output."""
        return self.water_output > 0

    def to_iot_recipe_dict(self) -> dict[str, Any]:
        """Convert to the exact recipe object expected by Morning IoT MQTT."""
        return {
            "id": self.id,
            "type": self.type,
            "ownerType": self.owner_type,
            "name": self.name,
            "isFavorite": self.is_favorite,
            "isModifiable": False,
            "isNew": False,
            "syncedToMachine": None,
            "temperature": self.temperature,
            "massOutput": self.mass_output,
            "waterOutput": self.water_output,
            "bloomDuration": self.bloom_duration,
            "pressureProfile": {
                "id": 0,
                "name": "Custom",
                "active": True,
                "stageDtos": [
                    {
                        "id": s.get("id", i),
                        "output": int(s.get("output", 0)),
                        "pressure": int(s.get("pressure", 7)),
                    }
                    for i, s in enumerate(self.stages)
                ],
            },
            "capsule": None,
            "roaster": None,
            "user": None,
            "productStore": None,
        }

    def to_iot_request_data(self) -> dict[str, Any]:
        """Convert to data envelope for BrewCoffee.Request."""
        return {
            "type": self.type,
            "ownerType": self.owner_type,
            "recipe": self.to_iot_recipe_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert recipe to dictionary for HA sensor state attributes & storage."""
        return {
            "id": self.id,
            "name": self.name,
            "roaster_name": self.roaster_name,
            "owner_type": self.owner_type,
            "type": self.type,
            "temperature": self.temperature,
            "mass_output": self.mass_output,
            "water_output": self.water_output,
            "bloom_duration": self.bloom_duration,
            "bloom_enabled": self.bloom_enabled,
            "bypass_enabled": self.bypass_enabled,
            "stages": [
                {
                    "id": s.get("id", i),
                    "output": int(s.get("output", 0)),
                    "pressure": int(s.get("pressure", 7)),
                }
                for i, s in enumerate(self.stages)
            ],
            "is_favorite": self.is_favorite,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MorningRecipe:
        """Restore recipe from dictionary."""
        stages_data = data.get("stages") or []
        stages = [
            {
                "id": s.get("id", i),
                "output": int(s.get("output", 0)),
                "pressure": int(s.get("pressure", 7)),
            }
            for i, s in enumerate(stages_data)
        ]
        if not stages:
            mass = int(data.get("mass_output") or 40)
            stages = [
                {"id": 0, "output": 0, "pressure": 3},
                {"id": 1, "output": min(5, max(2, mass - 5)), "pressure": 7},
                {"id": 2, "output": max(5, mass - 5), "pressure": 5},
            ]

        return cls(
            id=int(data.get("id", 0)),
            name=str(data.get("name") or "Morning Recipe"),
            roaster_name=str(data.get("roaster_name") or ""),
            owner_type=str(data.get("owner_type") or "USER_RECIPE"),
            type=str(data.get("type") or "COFFEE_RECIPE"),
            temperature=int(data.get("temperature") or 94),
            mass_output=int(data.get("mass_output") or 40),
            water_output=int(data.get("water_output") or 0),
            bloom_duration=int(data["bloom_duration"]) if data.get("bloom_duration") is not None else None,
            stages=stages,
            is_favorite=bool(data.get("is_favorite", False)),
            source=str(data.get("source") or "local"),
        )

    @classmethod
    def from_api_json(cls, raw: dict[str, Any], source: str = "user") -> MorningRecipe:
        """Parse recipe from Morning Cloud REST API response."""
        data = raw.get("recipe") if isinstance(raw.get("recipe"), dict) else raw

        roaster_info = data.get("roaster")
        roaster_name = ""
        if isinstance(roaster_info, dict):
            roaster_name = str(roaster_info.get("name") or "")
        elif isinstance(roaster_info, str):
            roaster_name = roaster_info
        elif "roaster_name" in data:
            roaster_name = str(data["roaster_name"])

        mass_output = int(data.get("massOutput") or data.get("mass_output") or 40)
        water_output = int(data.get("waterOutput") or data.get("water_output") or 0)
        temperature = int(data.get("temperature") or data.get("temp") or 94)

        bloom_val = data.get("bloomDuration") if "bloomDuration" in data else data.get("bloom_duration")
        bloom_duration = int(bloom_val) if bloom_val is not None else None

        stages: list[dict[str, int]] = []
        profile = data.get("pressureProfile") or data.get("pressure_profile")
        if isinstance(profile, dict) and "stageDtos" in profile and isinstance(profile["stageDtos"], list):
            for i, st in enumerate(profile["stageDtos"]):
                if isinstance(st, dict):
                    stages.append({
                        "id": int(st.get("id", i)),
                        "output": int(st.get("output", 0)),
                        "pressure": int(st.get("pressure", 7)),
                    })
        elif "stages" in data and isinstance(data["stages"], list):
            for i, st in enumerate(data["stages"]):
                if isinstance(st, dict):
                    stages.append({
                        "id": int(st.get("id", i)),
                        "output": int(st.get("output", 0)),
                        "pressure": int(st.get("pressure", 7)),
                    })

        if not stages:
            stages = [
                {"id": 0, "output": 0, "pressure": 3},
                {"id": 1, "output": min(5, max(2, mass_output - 5)), "pressure": 7},
                {"id": 2, "output": max(5, mass_output - 5), "pressure": 5},
            ]

        return cls(
            id=int(data.get("id", 0)),
            name=str(data.get("name") or "Morning Recipe"),
            roaster_name=roaster_name,
            owner_type=str(data.get("ownerType") or data.get("owner_type") or "USER_RECIPE"),
            type=str(data.get("type") or "COFFEE_RECIPE"),
            temperature=temperature,
            mass_output=mass_output,
            water_output=water_output,
            bloom_duration=bloom_duration,
            stages=stages,
            is_favorite=bool(data.get("isFavorite") or data.get("is_favorite") or False),
            source=source,
        )

