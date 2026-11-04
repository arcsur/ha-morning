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
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import aiohttp

from .const import (
    AWS_IOT_ENDPOINT,
    AWS_IOT_POLICY_NAME,
    AWS_IOT_REGION,
    COGNITO_IDENTITY_POOL_ID,
    COGNITO_REGION,
    COGNITO_USER_POOL_ID,
)
from .models import MorningLiveBrewTelemetry

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


def encode_mqtt_subscribe(topic: str, packet_id: int = 1) -> bytes:
    """Construct minimal MQTT 3.1.1 SUBSCRIBE packet."""
    topic_bytes = topic.encode("utf-8")
    payload = struct.pack("!H", len(topic_bytes)) + topic_bytes + bytes([0])
    var_header = struct.pack("!H", packet_id)
    rem_len = encode_mqtt_varlen(len(var_header) + len(payload))
    return bytes([0x82]) + rem_len + var_header + payload


def decode_mqtt_publish(data: bytes) -> tuple[str, bytes] | None:
    """Decode an incoming MQTT PUBLISH packet, returning (topic, payload)."""
    if len(data) < 4:
        return None
    pkt_type = data[0] >> 4
    if pkt_type != 3:  # 3 = PUBLISH
        return None

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
    payload = data[pos:]
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
        is_brewing = stage_str not in ("done", "cancel", "cancelled", "error", "water_low", "idle")

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
        )

    if isinstance(data, dict):
        status_val = str(data.get("status") or "").lower()
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
            temp_val = int(
                data.get("temperature")
                or data.get("current_temp")
                or data.get("current_temperature")
                or 0
            )
            return MorningLiveBrewTelemetry(
                stage="heating",
                temperature=temp_val,
                water_output=0.0,
                mass_output=0.0,
                bloom_lapse=0,
                is_brewing=True,
                last_updated=time.time(),
            )

    # Check for shadow reported status
    state = payload_dict.get("state")
    if isinstance(state, dict):
        reported = state.get("reported")
        if isinstance(reported, dict):
            settings = reported.get("settings", reported)
            status_val = str(settings.get("status") or "").lower()
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
                temp_val = int(
                    settings.get("temperature")
                    or settings.get("current_temp")
                    or settings.get("current_temperature")
                    or reported.get("temperature")
                    or 0
                )
                return MorningLiveBrewTelemetry(
                    stage="heating",
                    temperature=temp_val,
                    water_output=0.0,
                    mass_output=0.0,
                    bloom_lapse=0,
                    is_brewing=True,
                    last_updated=time.time(),
                )
            if status_val in ("ready", "idle", "eco"):
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

    # Check top-level status
    status_val = str(payload_dict.get("status") or "").lower()
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
        temp_val = int(payload_dict.get("temperature") or 0)
        return MorningLiveBrewTelemetry(
            stage="heating",
            temperature=temp_val,
            water_output=0.0,
            mass_output=0.0,
            bloom_lapse=0,
            is_brewing=True,
            last_updated=time.time(),
        )
    if status_val in ("ready", "idle", "eco"):
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


class MorningIotListener:
    """Manages AWS IoT WebSocket connection and live telemetry dispatching."""

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
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Start listener background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="morning_iot_stream")
        _LOGGER.debug("Started Morning IoT telemetry background listener")

    async def stop(self) -> None:
        """Stop listener background task."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        _LOGGER.debug("Stopped Morning IoT telemetry background listener")

    def _resolve_machine_id(self, topic: str) -> str | None:
        """Resolve machine ID from topic string (e.g. PROD/user/{id}/{uuid}/response or $aws/things/{id}/...)."""
        parts = topic.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "$aws" and parts[1] == "things":
            candidate_uuid = parts[2]
        else:
            candidate_uuid = parts[3] if len(parts) >= 4 else None

        if self.coordinator.data:
            if candidate_uuid:
                cand_lower = candidate_uuid.lower()
                for mid, machine in self.coordinator.data.items():
                    if machine.uuid.lower() == cand_lower or machine.id.lower() == cand_lower:
                        return mid
            return next(iter(self.coordinator.data.keys()))
        return None

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
                return identity_id, credentials

        except Exception as err:
            _LOGGER.warning("Failed retrieving AWS Cognito credentials for IoT: %s", err)
            return None

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
                async with self.session.ws_connect(
                    ws_url,
                    protocols=["mqtt"],
                    timeout=aiohttp.ClientWSTimeout(ws_close=10),
                    autoping=True,
                ) as ws:
                    backoff = 5  # Reset backoff on successful connect
                    _LOGGER.info("Connected to Morning AWS IoT live telemetry stream")

                    # Send MQTT CONNECT
                    cid = f"ha_morning_{identity_id.split(':')[-1][:8]}"
                    _LOGGER.debug("Sending MQTT CONNECT packet with cid=%s", cid)
                    await ws.send_bytes(encode_mqtt_connect(cid))

                    # Await CONNACK
                    connack_msg = await ws.receive()
                    if connack_msg.type != aiohttp.WSMsgType.BINARY:
                        _LOGGER.warning(
                            "MQTT CONNECT failed; unexpected message type: %s (code=%s, extra=%s)",
                            connack_msg.type,
                            ws.close_code,
                            connack_msg.extra,
                        )
                        break

                    connack_data = connack_msg.data
                    if len(connack_data) < 4 or connack_data[0] != 0x20:
                        _LOGGER.warning("MQTT invalid CONNACK packet: %s", list(connack_data))
                        break

                    connack_rc = connack_data[3]
                    if connack_rc != 0:
                        _LOGGER.warning("MQTT broker rejected connection: return_code=%d", connack_rc)
                        break

                    _LOGGER.info("MQTT session accepted by broker (CONNACK return_code=0)")

                    # Subscribe to topics
                    sub_topics = [
                        f"PROD/user/{identity_id}/+/response",
                        f"PROD/user/{identity_id}/+/status",
                    ]
                    for pid, top in enumerate(sub_topics, start=1):
                        _LOGGER.debug("Subscribing to MQTT topic: %s", top)
                        await ws.send_bytes(encode_mqtt_subscribe(top, packet_id=pid))

                    last_ping = time.time()
                    while self._running and not ws.closed:
                        try:
                            msg = await asyncio.wait_for(ws.receive(), timeout=15)
                        except TimeoutError:
                            if time.time() - last_ping >= 30:
                                await ws.send_bytes(b"\xc0\x00")  # PINGREQ
                                last_ping = time.time()
                            continue

                        if msg.type == aiohttp.WSMsgType.BINARY:
                            parsed = decode_mqtt_publish(msg.data)
                            if parsed:
                                topic, payload_bytes = parsed
                                try:
                                    payload_dict = json.loads(payload_bytes.decode("utf-8"))
                                    telem = decode_brew_progress_payload(payload_dict)
                                    if telem:
                                        target_mid = self._resolve_machine_id(topic)
                                        if target_mid:
                                            self.coordinator.handle_live_brew_update(
                                                target_mid, telem
                                            )
                                except Exception as err:
                                    _LOGGER.debug("Error parsing IoT brew telemetry: %s", err)

                        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                            _LOGGER.warning(
                                "Morning IoT WebSocket closed by server: code=%s, extra=%s",
                                ws.close_code,
                                msg.extra,
                            )
                            break

                # Sleep before reconnecting if WebSocket closed
                if self._running:
                    await asyncio.sleep(backoff)
                    backoff = min(60, backoff * 2)

            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.warning("Morning IoT live stream error: %s (retrying in %ds)", err, backoff)
                await asyncio.sleep(backoff)
                backoff = min(60, backoff * 2)
