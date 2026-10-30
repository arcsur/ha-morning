"""Unit tests for AWS IoT MQTT WebSocket client and telemetry parser."""

import struct
import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock

from custom_components.morning.iot import (
    MorningIotListener,
    decode_brew_progress_payload,
    decode_mqtt_publish,
    encode_mqtt_connect,
    encode_mqtt_subscribe,
    sign_iot_websocket_url,
    sign_sigv4_headers,
)
from custom_components.morning.models import MorningMachine


class TestMorningIot(unittest.IsolatedAsyncioTestCase):
    """Test AWS IoT signing, MQTT encoding/decoding, and telemetry parsing."""

    def setUp(self):
        """Set up test fixtures."""
        self.credentials = {
            "AccessKeyId": "ASIAEXAMPLEKEYID",
            "SecretKey": "EXAMPLESECRETKEYEXAMPLESECRETKEY",
            "SessionToken": "EXAMPLESECURITYTOKEN",
        }
        self.timestamp = datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC)

    def test_sign_iot_websocket_url(self):
        """Test SigV4 presigned URL generation."""
        url = sign_iot_websocket_url(
            endpoint="example.iot.ap-southeast-1.amazonaws.com",
            region="ap-southeast-1",
            credentials=self.credentials,
            timestamp=self.timestamp,
        )
        self.assertTrue(url.startswith("wss://example.iot.ap-southeast-1.amazonaws.com/mqtt?"))
        self.assertIn("X-Amz-Algorithm=AWS4-HMAC-SHA256", url)
        self.assertIn("X-Amz-Credential=ASIAEXAMPLEKEYID", url)
        self.assertIn("X-Amz-Date=20261030T120000Z", url)
        self.assertIn("X-Amz-Signature=", url)
        self.assertIn("X-Amz-Security-Token=EXAMPLESECURITYTOKEN", url)

    def test_sign_sigv4_headers(self):
        """Test SigV4 headers generation for REST endpoints."""
        headers = sign_sigv4_headers(
            method="PUT",
            host="example.iot.ap-southeast-1.amazonaws.com",
            path="/principal-policies/PRODUserIotPolicy",
            region="ap-southeast-1",
            service="iot",
            credentials=self.credentials,
            timestamp=self.timestamp,
        )
        self.assertIn("authorization", headers)
        self.assertTrue(headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=ASIAEXAMPLEKEYID/"))
        self.assertEqual(headers["x-amz-date"], "20261030T120000Z")
        self.assertEqual(headers["x-amz-security-token"], "EXAMPLESECURITYTOKEN")

    def test_encode_mqtt_packets(self):
        """Test minimal MQTT CONNECT and SUBSCRIBE packet encoding."""
        conn_pkt = encode_mqtt_connect("test_client_id", keepalive=60)
        self.assertEqual(conn_pkt[0], 0x10)  # CONNECT packet type
        self.assertIn(b"MQTT", conn_pkt)
        self.assertIn(b"test_client_id", conn_pkt)

        sub_pkt = encode_mqtt_subscribe("PROD/user/123/+/response", packet_id=2)
        self.assertEqual(sub_pkt[0], 0x82)  # SUBSCRIBE packet type
        self.assertIn(b"PROD/user/123/+/response", sub_pkt)

    def test_decode_mqtt_publish(self):
        """Test decoding an MQTT PUBLISH packet."""
        topic = "PROD/user/id123/uuid456/response"
        payload = b'{"data": {"progress": {"waterOutput": 42.5}}}'

        topic_bytes = topic.encode("utf-8")
        packet_body = struct.pack("!H", len(topic_bytes)) + topic_bytes + payload
        data = bytes([0x30, len(packet_body)]) + packet_body

        decoded = decode_mqtt_publish(data)
        self.assertIsNotNone(decoded)
        dec_topic, dec_payload = decoded
        self.assertEqual(dec_topic, topic)
        self.assertEqual(dec_payload, payload)

    def test_decode_brew_progress_payload(self):
        """Test parsing live brew telemetry dictionary."""
        # Active brewing packet
        active_packet = {
            "name": "BrewCoffee.Response",
            "data": {
                "progress": {
                    "status": "BREWING",
                    "waterOutput": 55.4,
                    "massOutput": 54.1,
                    "temperature": 94,
                    "bloomLapse": 12,
                }
            },
        }
        telem = decode_brew_progress_payload(active_packet)
        self.assertIsNotNone(telem)
        self.assertTrue(telem.is_brewing)
        self.assertEqual(telem.stage, "brewing")
        self.assertEqual(telem.water_output, 55.4)
        self.assertEqual(telem.mass_output, 54.1)
        self.assertEqual(telem.temperature, 94)
        self.assertEqual(telem.bloom_lapse, 12)

        # Done brewing packet
        done_packet = {
            "name": "BrewCoffee.Response",
            "data": {
                "progress": {
                    "status": "DONE",
                    "waterOutput": 150.0,
                    "massOutput": 147.8,
                    "temperature": 91,
                    "bloomLapse": 15,
                }
            },
        }
        done_telem = decode_brew_progress_payload(done_packet)
        self.assertIsNotNone(done_telem)
        self.assertFalse(done_telem.is_brewing)
        self.assertEqual(done_telem.stage, "done")
        self.assertEqual(done_telem.water_output, 150.0)

    def test_resolve_machine_id(self):
        """Test resolving machine ID by UUID or fallback."""
        coordinator = MagicMock()
        machine = MorningMachine.from_dict({"id": "M_123", "uuid": "FDEE0D2A-1E2E-248F-50B1-D063963E3A18"})
        coordinator.data = {"M_123": machine}

        listener = MorningIotListener(coordinator=coordinator, client=MagicMock(), session=MagicMock())

        # Match by UUID in topic
        topic = "PROD/user/identity1/FDEE0D2A-1E2E-248F-50B1-D063963E3A18/response"
        mid = listener._resolve_machine_id(topic)
        self.assertEqual(mid, "M_123")

        # Match by direct machine ID in topic
        topic_id = "PROD/user/identity1/M_123/response"
        mid_id = listener._resolve_machine_id(topic_id)
        self.assertEqual(mid_id, "M_123")


if __name__ == "__main__":
    unittest.main()
