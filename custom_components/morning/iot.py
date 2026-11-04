"""AWS IoT MQTT WebSocket client for live Morning Coffee Machine telemetry."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import struct
import time
import urllib.parse
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import aiohttp

from .client import MorningConnectionError
from .const import (
    AWS_IOT_ENDPOINT,
    AWS_IOT_POLICY_NAME,
    AWS_IOT_REGION,
    COGNITO_IDENTITY_POOL_ID,
    COGNITO_REGION,
    COGNITO_USER_POOL_ID,
)
from .models import MorningLiveBrewTelemetry, MorningRecipe

if TYPE_CHECKING:
    from .client import MorningClient
    from .coordinator import MorningDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _sign(key: bytes, msg: str) -> bytes:
    """HMAC-SHA256 helper."""
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(key: str, date_stamp: str, region_name: str, service_name: str) -> bytes:
    """Derive AWS SigV4 signing key."""
    k_date = _sign(("AWS4" + key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region_name)
    k_service = _sign(k_region, service_name)
    return _sign(k_service, "aws4_request")


def sign_iot_websocket_url(
    endpoint: str,
    region: str,
    credentials: dict[str, str],
    expires: int = 300,
    timestamp: datetime | None = None,
) -> str:
    """Generate a presigned AWS IoT MQTT WebSocket URL using AWS SigV4."""
    now = timestamp or datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    access_key = credentials["AccessKeyId"]
    secret_key = credentials["SecretKey"]
    session_token = credentials.get("SessionToken", "")

    service = "iotdevicegateway"
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"

    query_params = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{access_key}/{credential_scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires),
        "X-Amz-SignedHeaders": "host",
    }

    canonical_querystring = urllib.parse.urlencode(sorted(query_params.items()))
    canonical_headers = f"host:{endpoint}\n"
    payload_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    canonical_request = (
        f"GET\n/mqtt\n{canonical_querystring}\n{canonical_headers}\nhost\n{payload_hash}"
    )

    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    signing_key = _get_signature_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    url = f"wss://{endpoint}/mqtt?{canonical_querystring}&X-Amz-Signature={signature}"
    if session_token:
        url += f"&X-Amz-Security-Token={urllib.parse.quote(session_token)}"
    return url


def sign_sigv4_headers(
    method: str,
    host: str,
    path: str,
    region: str,
    service: str,
    credentials: dict[str, str],
    payload: bytes = b"",
    extra_headers: dict[str, str] | None = None,
    timestamp: datetime | None = None,
) -> dict[str, str]:
    """Generate signed HTTP headers for AWS REST requests (e.g. AttachPrincipalPolicy)."""
    now = timestamp or datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    access_key = credentials["AccessKeyId"]
    secret_key = credentials["SecretKey"]
    session_token = credentials.get("SessionToken", "")

    headers_to_sign = {
        "host": host,
        "x-amz-date": amz_date,
    }
    if session_token:
        headers_to_sign["x-amz-security-token"] = session_token
    if extra_headers:
        for k, v in extra_headers.items():
            headers_to_sign[k.lower()] = v

    sorted_header_keys = sorted(headers_to_sign.keys())
    canonical_headers = "".join(f"{k}:{headers_to_sign[k]}\n" for k in sorted_header_keys)
    signed_headers = ";".join(sorted_header_keys)

    payload_hash = hashlib.sha256(payload).hexdigest()
    canonical_request = f"{method.upper()}\n{path}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    signing_key = _get_signature_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    out = dict(headers_to_sign)
    out["authorization"] = authorization
    return out


def encode_mqtt_varlen(length: int) -> bytes:
    """Encode MQTT variable length integer."""
    encoded = bytearray()
    while True:
        digit = length % 128
        length //= 128
        if length > 0:
            digit |= 0x80
        encoded.append(digit)
        if length == 0:
            break
    return bytes(encoded)


def encode_mqtt_connect(client_id: str, keepalive: int = 60) -> bytes:
    """Construct minimal MQTT 3.1.1 CONNECT packet."""
    protocol_name = b"MQTT"
    var_header = (
        struct.pack("!H", len(protocol_name))
        + protocol_name
        + bytes([4, 0x02])
        + struct.pack("!H", keepalive)
    )
    cid_bytes = client_id.encode("utf-8")
    payload = struct.pack("!H", len(cid_bytes)) + cid_bytes
    rem_len = encode_mqtt_varlen(len(var_header) + len(payload))
    return bytes([0x10]) + rem_len + var_header + payload


def encode_mqtt_subscribe(topic: str, packet_id: int = 1, qos: int = 1) -> bytes:
    """Construct minimal MQTT 3.1.1 SUBSCRIBE packet."""
    topic_bytes = topic.encode("utf-8")
    payload = struct.pack("!H", len(topic_bytes)) + topic_bytes + bytes([qos & 0x03])
    var_header = struct.pack("!H", packet_id)
    rem_len = encode_mqtt_varlen(len(var_header) + len(payload))
    return bytes([0x82]) + rem_len + var_header + payload


def encode_mqtt_puback(packet_id: int) -> bytes:
    """Construct MQTT 3.1.1 PUBACK packet for QoS 1 messages."""
    return bytes([0x40, 0x02]) + struct.pack("!H", packet_id)


def encode_mqtt_publish(topic: str, payload: bytes, packet_id: int = 1, qos: int = 1) -> bytes:
    """Construct MQTT 3.1.1 PUBLISH packet."""
    topic_bytes = topic.encode("utf-8")
    var_header = struct.pack("!H", len(topic_bytes)) + topic_bytes
    if qos > 0:
        var_header += struct.pack("!H", packet_id)
    first_byte = 0x30 | ((qos & 0x03) << 1)
    rem_len = encode_mqtt_varlen(len(var_header) + len(payload))
    return bytes([first_byte]) + rem_len + var_header + payload


def decode_mqtt_publish_packet(data: bytes) -> tuple[str, bytes, int | None] | None:
    """Decode an incoming MQTT PUBLISH packet, returning (topic, payload, packet_id)."""
    if len(data) < 4:
        return None
    pkt_type = data[0] >> 4
    if pkt_type != 3:  # 3 = PUBLISH
        return None
    qos = (data[0] >> 1) & 0x03

    # Parse remaining length
    pos = 1
    multiplier = 1
    rem_len = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        rem_len += (b & 127) * multiplier
        multiplier *= 128
        if (b & 128) == 0:
            break

    if pos + 2 > len(data):
        return None

    topic_len = struct.unpack("!H", data[pos : pos + 2])[0]
    pos += 2
    if pos + topic_len > len(data):
        return None

    topic = data[pos : pos + topic_len].decode("utf-8", errors="ignore")
    pos += topic_len

    packet_id: int | None = None
    if qos > 0:
        if pos + 2 > len(data):
            return None
        packet_id = struct.unpack("!H", data[pos : pos + 2])[0]
        pos += 2

    payload = data[pos:]
    return topic, payload, packet_id


def decode_mqtt_publish(data: bytes) -> tuple[str, bytes] | None:
    """Decode an incoming MQTT PUBLISH packet, returning (topic, payload)."""
    res = decode_mqtt_publish_packet(data)
    if res is None:
        return None
    topic, payload, _ = res
    return topic, payload


def decode_brew_progress_payload(payload_dict: dict[str, Any]) -> MorningLiveBrewTelemetry | None:
    """Extract MorningLiveBrewTelemetry from an incoming MQTT JSON message."""
    data = payload_dict.get("data")
    prog = None
    if isinstance(data, dict):
        if isinstance(data.get("progress"), dict):
            prog = data["progress"]
        elif any(
            k in data
            for k in (
                "waterOutput",
                "water_output",
                "massOutput",
                "mass_output",
                "bloomLapse",
                "temperature",
            )
        ):
            prog = data
    elif any(
        k in payload_dict
        for k in ("waterOutput", "water_output", "massOutput", "mass_output", "bloomLapse")
    ):
        prog = payload_dict

    if isinstance(prog, dict):
        raw_water = float(prog.get("waterOutput") or prog.get("water_output") or 0.0)
        raw_mass = float(prog.get("massOutput") or prog.get("mass_output") or 0.0)
        temperature = int(prog.get("temperature") or 0)
        stage_str = str(prog.get("status") or "brewing").lower()
        bloom_lapse = int(prog.get("bloomLapse") or 0)
        if stage_str in ("cancel", "cancelled", "canceled", "abort", "aborted"):
            stage_str = "cancel"
        elif stage_str in ("bloom", "blooming", "prewet") or (
            stage_str == "brewing" and bloom_lapse > 0 and raw_water == 0.0
        ):
            stage_str = "blooming"
        is_brewing = stage_str not in ("done", "cancel", "error", "water_low", "idle", "ready", "eco")

        # Morning Machine: waterOutput is bypass water, massOutput is extracted espresso.
        # Total water drawn from the reservoir is bypass water + extraction mass.
        water_dispensed = (raw_water + raw_mass) if (raw_water > 0 or raw_mass > 0) else 0.0

        return MorningLiveBrewTelemetry(
            stage=stage_str,
            temperature=temperature,
            water_output=water_dispensed,
            mass_output=raw_mass,
            bloom_lapse=bloom_lapse,
            is_brewing=is_brewing,
            last_updated=time.time(),
            source="mqtt",
        )

    def _status_to_telemetry(status_val: str, temp_val: int = 0) -> MorningLiveBrewTelemetry | None:
        if status_val == "purge":
            return MorningLiveBrewTelemetry(
                stage="purge",
                temperature=0,
                water_output=0.0,
                mass_output=0.0,
                bloom_lapse=0,
                is_brewing=True,
                last_updated=time.time(),
            )
        if status_val in ("heating", "preheating", "warming"):
            return MorningLiveBrewTelemetry(
                stage="heating",
                temperature=temp_val,
                water_output=0.0,
                mass_output=0.0,
                bloom_lapse=0,
                is_brewing=True,
                last_updated=time.time(),
            )
        if status_val in ("cancel", "cancelled", "canceled", "abort", "aborted"):
            return MorningLiveBrewTelemetry(
                stage="cancel",
                temperature=0,
                water_output=0.0,
                mass_output=0.0,
                bloom_lapse=0,
                is_brewing=False,
                last_updated=time.time(),
            )
        if status_val in ("done", "ready", "idle", "eco"):
            return MorningLiveBrewTelemetry(
                stage=status_val,
                temperature=0,
                water_output=0.0,
                mass_output=0.0,
                bloom_lapse=0,
                is_brewing=False,
                last_updated=time.time(),
            )
        return None

    if isinstance(data, dict):
        status_val = str(data.get("status") or "").lower()
        temp_val = int(
            data.get("temperature")
            or data.get("current_temp")
            or data.get("current_temperature")
            or 0
        )
        matched = _status_to_telemetry(status_val, temp_val)
        if matched is not None:
            return matched

    # Check for shadow reported status
    state = payload_dict.get("state")
    if isinstance(state, dict):
        reported = state.get("reported")
        if isinstance(reported, dict):
            settings = reported.get("settings", reported)
            status_val = str(settings.get("status") or "").lower()
            temp_val = int(
                settings.get("temperature")
                or settings.get("current_temp")
                or settings.get("current_temperature")
                or reported.get("temperature")
                or 0
            )
            return _status_to_telemetry(status_val, temp_val)

    # Check top-level status
    status_val = str(payload_dict.get("status") or "").lower()
    temp_val = int(payload_dict.get("temperature") or 0)
    matched = _status_to_telemetry(status_val, temp_val)
    if matched is not None:
        return matched

    return None


class MorningIotListener:
    """Manages AWS IoT WebSocket connection, Thing Shadow sync, and live telemetry dispatching."""

    def __init__(
        self,
        coordinator: MorningDataUpdateCoordinator,
        client: MorningClient,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the listener."""
        self.coordinator = coordinator
        self.client = client
        self.session = session
        self._running = False
        self.is_connected = False
        self._task: asyncio.Task | None = None
        self._shadow_task: asyncio.Task | None = None
        self._shadow_session: aiohttp.ClientSession | None = None
        self._identity_id: str | None = None
        self._credentials: dict[str, str] | None = None
        self._creds_obtained_at: float = 0.0
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ws_lock = asyncio.Lock()
        self._app_id = str(uuid.uuid4())
        self._packet_id_counter = 1

    def _evict_iot_pool(self) -> None:
        """Close pooled keep-alive REST sockets to AWS_IOT_ENDPOINT before WebSocket upgrade."""
        connector = getattr(self.session, "connector", None)
        conns = getattr(connector, "_conns", None)
        if isinstance(conns, dict):
            for key in list(conns.keys()):
                if getattr(key, "host", None) == AWS_IOT_ENDPOINT:
                    for handler, _ in conns.pop(key, []):
                        try:
                            handler.close()
                        except Exception:
                            pass

    def start(self) -> None:
        """Start listener background tasks."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="morning_iot_stream")
        self._shadow_task = asyncio.create_task(
            self._run_shadow_loop(), name="morning_iot_shadow_sync"
        )
        _LOGGER.debug("Started Morning IoT telemetry and shadow background listeners")

    async def stop(self) -> None:
        """Stop listener background tasks."""
        self._running = False
        self.is_connected = False
        self._ws = None
        for task in (self._task, self._shadow_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._task = None
        self._shadow_task = None
        if self._shadow_session is not None and not self._shadow_session.closed:
            await self._shadow_session.close()
        self._shadow_session = None
        _LOGGER.debug("Stopped Morning IoT telemetry background listener")

    def _resolve_machine_id(
        self,
        topic: str,
        payload_dict: dict[str, Any] | None = None,
        own_identity_id: str | None = None,
    ) -> str | None:
        """Resolve machine ID from payload or topic string, filtering out foreign machines."""
        if not self.coordinator or not self.coordinator.data:
            return None

        if isinstance(payload_dict, dict):
            payload_mid = payload_dict.get("machineId") or payload_dict.get("id")
            if not payload_mid and isinstance(payload_dict.get("data"), dict):
                payload_mid = payload_dict["data"].get("machineId")
            if not payload_mid and isinstance(payload_dict.get("state"), dict):
                reported = payload_dict["state"].get("reported", {})
                if isinstance(reported, dict):
                    settings = reported.get("settings", reported)
                    if isinstance(settings, dict):
                        payload_mid = settings.get("id")
            if payload_mid:
                pmid_lower = str(payload_mid).lower()
                for mid, machine in self.coordinator.data.items():
                    if machine.id.lower() == pmid_lower or machine.uuid.lower() == pmid_lower:
                        return mid
                # Payload explicitly targeted a machine not owned by this coordinator
                return None

        parts = topic.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "$aws" and parts[1] == "things":
            candidate_uuid = parts[2]
        else:
            candidate_uuid = parts[3] if len(parts) >= 4 else None

        if candidate_uuid:
            cand_lower = candidate_uuid.lower()
            for mid, machine in self.coordinator.data.items():
                if machine.uuid.lower() == cand_lower or machine.id.lower() == cand_lower:
                    return mid

        # Only fallback to first machine if topic belongs to our own identity_id
        if own_identity_id is not None and len(parts) >= 3 and parts[0] == "PROD" and parts[1] == "user":
            if parts[2] != own_identity_id:
                return None

        return next(iter(self.coordinator.data.keys()))

    async def _get_credentials_and_identity(self) -> tuple[str, dict[str, str]] | None:
        """Fetch AWS Cognito Identity ID and temporary credentials."""
        auth_session = self.client.auth_session
        if not auth_session:
            return None

        id_token = await self.client._ensure_valid_token()
        cognito_idp_provider = (
            f"cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
        )

        identity_endpoint = f"https://cognito-identity.{COGNITO_REGION}.amazonaws.com/"
        headers = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityService.GetId",
        }
        body_get_id = {
            "IdentityPoolId": COGNITO_IDENTITY_POOL_ID,
            "Logins": {cognito_idp_provider: id_token},
        }

        try:
            async with self.session.post(
                identity_endpoint, json=body_get_id, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("Cognito GetId returned HTTP %s", resp.status)
                    return None
                data = await resp.json(content_type=None)
                identity_id = data.get("IdentityId")

            if not identity_id:
                return None

            # GetCredentialsForIdentity
            headers["X-Amz-Target"] = "AWSCognitoIdentityService.GetCredentialsForIdentity"
            body_creds = {
                "IdentityId": identity_id,
                "Logins": {cognito_idp_provider: id_token},
            }
            async with self.session.post(
                identity_endpoint, json=body_creds, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("Cognito GetCredentials returned HTTP %s", resp.status)
                    return None
                creds_data = await resp.json(content_type=None)
                credentials = creds_data.get("Credentials")
                if not credentials:
                    return None

                # Attach IoT Policy
                await self._attach_policy(identity_id, credentials)
                self._identity_id = identity_id
                self._credentials = credentials
                self._creds_obtained_at = time.time()
                return identity_id, credentials

        except Exception as err:
            _LOGGER.warning("Failed retrieving AWS Cognito credentials for IoT: %s", err)
            return None

    async def async_get_thing_shadow(self, machine_id: str) -> dict[str, Any] | None:
        """Fetch the live AWS IoT Thing Shadow document for a machine."""
        if not self._credentials or (time.time() - self._creds_obtained_at) > 2400:
            res = await self._get_credentials_and_identity()
            if not res:
                return None

        creds = self._credentials
        if not creds:
            return None

        path = f"/things/{machine_id}/shadow"
        url = f"https://{AWS_IOT_ENDPOINT}{path}"
        headers = sign_sigv4_headers(
            method="GET",
            host=AWS_IOT_ENDPOINT,
            path=path,
            region=AWS_IOT_REGION,
            service="iotdata",
            credentials=creds,
        )
        try:
            shadow_sess = self.session
            if isinstance(self.session, aiohttp.ClientSession):
                if self._shadow_session is None or self._shadow_session.closed:
                    self._shadow_session = aiohttp.ClientSession()
                shadow_sess = self._shadow_session
            async with shadow_sess.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                if resp.status in (401, 403):
                    self._credentials = None
                _LOGGER.debug("GetThingShadow(%s) returned HTTP %s", machine_id, resp.status)
        except Exception as err:
            _LOGGER.debug("GetThingShadow(%s) error: %s", machine_id, err)
        return None

    async def _run_shadow_loop(self) -> None:
        """Poll AWS IoT Thing Shadow at 1s (active brew) / 3s (idle) cadence."""
        while self._running:
            try:
                if self.coordinator and self.coordinator.data:
                    for mid in list(self.coordinator.data.keys()):
                        shadow_doc = await self.async_get_thing_shadow(mid)
                        if shadow_doc and self.coordinator:
                            self.coordinator.handle_shadow_update(mid, shadow_doc)

                is_active = False
                if self.coordinator and self.coordinator.data:
                    for mid, machine in self.coordinator.data.items():
                        st = str(machine.status or "").lower()
                        telem = self.coordinator.live_telemetry.get(mid)
                        if st in ("heating", "brewing", "purge") or (telem and telem.is_brewing):
                            is_active = True
                            break

                await asyncio.sleep(1.0 if is_active else 3.0)
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.debug("Shadow poll loop error: %s", err)
                await asyncio.sleep(3.0)

    async def _attach_policy(self, identity_id: str, credentials: dict[str, str]) -> None:
        """Attach AWS IoT user policy to identity principal."""
        iot_host = f"iot.{AWS_IOT_REGION}.amazonaws.com"
        path = f"/principal-policies/{AWS_IOT_POLICY_NAME}"
        url = f"https://{iot_host}{path}"
        headers = sign_sigv4_headers(
            method="PUT",
            host=iot_host,
            path=path,
            region=AWS_IOT_REGION,
            service="iot",
            credentials=credentials,
            extra_headers={"x-amzn-iot-principal": identity_id},
        )
        try:
            async with self.session.put(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                _LOGGER.debug("AttachPrincipalPolicy result: HTTP %s", resp.status)
        except Exception as err:
            _LOGGER.warning("AttachPrincipalPolicy error: %s", err)

    async def _run_loop(self) -> None:
        """Main connection and packet dispatching loop with backoff."""
        backoff = 5
        while self._running:
            try:
                res = await self._get_credentials_and_identity()
                if not res:
                    await asyncio.sleep(backoff)
                    backoff = min(60, backoff * 2)
                    continue

                identity_id, credentials = res
                ws_url = sign_iot_websocket_url(
                    endpoint=AWS_IOT_ENDPOINT,
                    region=AWS_IOT_REGION,
                    credentials=credentials,
                )

                _LOGGER.debug("Connecting to AWS IoT WebSocket endpoint...")
                self._evict_iot_pool()
                async with self.session.ws_connect(
                    ws_url,
                    protocols=["mqtt"],
                    timeout=aiohttp.ClientWSTimeout(ws_close=10),
                    autoping=True,
                ) as ws:
                    backoff = 5  # Reset backoff on successful connect
                    _LOGGER.info("Connected to Morning AWS IoT live telemetry stream")

                    # Send MQTT CONNECT with unique client_id to avoid collision on reconnect
                    cid = f"ha_morning_{identity_id.split(':')[-1][:8]}_{int(time.time() * 1000) % 100000}"
                    _LOGGER.debug("Sending MQTT CONNECT packet with cid=%s", cid)
                    await ws.send_bytes(encode_mqtt_connect(cid))

                    # Await CONNACK
                    connack_msg = await ws.receive()
                    if connack_msg.type != aiohttp.WSMsgType.BINARY:
                        raise RuntimeError(
                            f"MQTT CONNECT failed; unexpected message type: {connack_msg.type} (code={ws.close_code}, extra={connack_msg.extra})"
                        )

                    connack_data = connack_msg.data
                    if len(connack_data) < 4 or connack_data[0] != 0x20:
                        raise RuntimeError(f"MQTT invalid CONNACK packet: {list(connack_data)}")

                    connack_rc = connack_data[3]
                    if connack_rc != 0:
                        raise RuntimeError(f"MQTT broker rejected connection: return_code={connack_rc}")

                    self.is_connected = True
                    self._ws = ws
                    if self.coordinator and hasattr(self.coordinator, "async_update_listeners"):
                        self.coordinator.async_update_listeners()
                    _LOGGER.info("MQTT session accepted by broker (CONNACK return_code=0)")

                    # Subscribe to topics with QoS 1
                    sub_topics = [
                        "PROD/user/+/+/response",
                        "PROD/user/+/+/status",
                    ]
                    for pid, top in enumerate(sub_topics, start=1):
                        _LOGGER.debug("Subscribing to MQTT topic: %s", top)
                        await ws.send_bytes(encode_mqtt_subscribe(top, packet_id=pid, qos=1))

                    last_ping = time.time()
                    while self._running and not ws.closed:
                        if time.time() - last_ping >= 25:
                            await ws.send_bytes(b"\xc0\x00")  # PINGREQ
                            last_ping = time.time()

                        try:
                            msg = await asyncio.wait_for(ws.receive(), timeout=15)
                        except TimeoutError:
                            if time.time() - last_ping >= 25:
                                await ws.send_bytes(b"\xc0\x00")  # PINGREQ
                                last_ping = time.time()
                            continue

                        if msg.type == aiohttp.WSMsgType.BINARY:
                            pkt_type = msg.data[0] >> 4 if msg.data else 0
                            if pkt_type == 9:  # SUBACK
                                _LOGGER.debug("MQTT SUBACK received: %s", list(msg.data))
                                continue

                            parsed = decode_mqtt_publish_packet(msg.data)
                            if parsed:
                                topic, payload_bytes, pkt_id = parsed
                                if pkt_id is not None:
                                    await ws.send_bytes(encode_mqtt_puback(pkt_id))
                                try:
                                    payload_dict = json.loads(payload_bytes.decode("utf-8"))
                                    target_mid = self._resolve_machine_id(
                                        topic, payload_dict, identity_id
                                    )
                                    if target_mid:
                                        telem = decode_brew_progress_payload(payload_dict)
                                        if telem:
                                            _LOGGER.info(
                                                "IoT MQTT telemetry for %s: stage=%s water=%.1f mass=%.1f temp=%d bloom=%d",
                                                target_mid,
                                                telem.stage,
                                                telem.water_output,
                                                telem.mass_output,
                                                telem.temperature,
                                                telem.bloom_lapse,
                                            )
                                            self.coordinator.handle_live_brew_update(
                                                target_mid, telem
                                            )
                                except Exception as err:
                                    _LOGGER.warning("Error parsing IoT brew telemetry on %s: %s", topic, err)

                        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                            self.is_connected = False
                            _LOGGER.warning(
                                "Morning IoT WebSocket closed by server: code=%s, extra=%s",
                                ws.close_code,
                                msg.extra,
                            )
                            break

                    self.is_connected = False
                    self._ws = None

                # Sleep before reconnecting if WebSocket closed
                if self._running:
                    await asyncio.sleep(backoff)
                    backoff = min(60, backoff * 2)

            except asyncio.CancelledError:
                self.is_connected = False
                self._ws = None
                break
            except Exception as err:
                self.is_connected = False
                self._ws = None
                _LOGGER.warning("Morning IoT live stream error: %s (retrying in %ds)", err, backoff)
                await asyncio.sleep(backoff)
                backoff = min(60, backoff * 2)

    async def async_publish_command(self, payload_dict: dict[str, Any]) -> None:
        """Publish a command to the Morning IoT command topic."""
        if not self._identity_id:
            res = await self._get_credentials_and_identity()
            if not res:
                raise MorningConnectionError("Unable to acquire Cognito credentials for IoT command")

        # Wait up to 3 seconds if listener is currently reconnecting
        for _ in range(30):
            if self._ws is not None and not self._ws.closed and self.is_connected:
                break
            await asyncio.sleep(0.1)

        async with self._ws_lock:
            if self._ws is None or self._ws.closed:
                raise MorningConnectionError("Morning IoT live MQTT connection is not active")

            topic = f"PROD/user/{self._identity_id}/{self._app_id}/command"
            payload_bytes = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
            self._packet_id_counter = (self._packet_id_counter % 65535) + 1
            pkt = encode_mqtt_publish(topic, payload_bytes, packet_id=self._packet_id_counter, qos=1)
            _LOGGER.debug(
                "Publishing IoT command to %s (len=%d): %s",
                topic,
                len(payload_bytes),
                payload_dict,
            )
            await self._ws.send_bytes(pkt)

    async def async_brew_coffee(self, machine_id: str, recipe: MorningRecipe) -> None:
        """Initiate coffee extraction on the machine via AWS IoT MQTT."""
        if not self._identity_id:
            res = await self._get_credentials_and_identity()
            if not res:
                raise MorningConnectionError("Unable to acquire Cognito credentials for IoT brew")

        app_user_id = (
            self.client.auth_session.user_id
            if self.client and self.client.auth_session and self.client.auth_session.user_id
            else self._identity_id
        )
        payload = {
            "action": "BREW",
            "apiVersion": 2,
            "userId": self._identity_id,
            "appUserId": app_user_id,
            "machineId": machine_id,
            "appId": self._app_id,
            "data": recipe.to_iot_request_data(),
        }
        _LOGGER.info(
            "Sending BREW command to machine %s: %s (%d°C, %dg)",
            machine_id,
            recipe.name,
            recipe.temperature,
            recipe.mass_output,
        )
        await self.async_publish_command(payload)

        # Optimistically mark machine as heating so UI and coordinator respond immediately
        if self.coordinator:
            self.coordinator.handle_live_brew_update(
                machine_id,
                MorningLiveBrewTelemetry(
                    stage="heating",
                    temperature=0,
                    water_output=0.0,
                    mass_output=0.0,
                    bloom_lapse=0,
                    is_brewing=True,
                    last_updated=time.time(),
                    source="command",
                ),
            )

    async def async_cancel_brew(self, machine_id: str) -> None:
        """Cancel an ongoing coffee extraction on the machine via AWS IoT MQTT."""
        if not self._identity_id:
            res = await self._get_credentials_and_identity()
            if not res:
                raise MorningConnectionError("Unable to acquire Cognito credentials for IoT cancel")

        app_user_id = (
            self.client.auth_session.user_id
            if self.client and self.client.auth_session and self.client.auth_session.user_id
            else self._identity_id
        )
        payload = {
            "action": "CANCEL",
            "apiVersion": 2,
            "userId": self._identity_id,
            "appUserId": app_user_id,
            "machineId": machine_id,
            "appId": self._app_id,
            "data": None,
        }
        _LOGGER.info("Sending CANCEL command to machine %s", machine_id)
        await self.async_publish_command(payload)

        # Optimistically mark brew as cancelled
        if self.coordinator:
            self.coordinator.handle_live_brew_update(
                machine_id,
                MorningLiveBrewTelemetry(
                    stage="cancel",
                    temperature=0,
                    water_output=0.0,
                    mass_output=0.0,
                    bloom_lapse=0,
                    is_brewing=False,
                    last_updated=time.time(),
                    source="command",
                ),
            )

