"""Unit tests for AWS IoT MQTT WebSocket client and telemetry parser."""

import struct
import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock

from custom_components.morning.iot import (
    MorningIotListener,
    decode_brew_progress_payload,
    decode_mqtt_publish,
    decode_mqtt_publish_packet,
    encode_mqtt_connect,
    encode_mqtt_puback,
    encode_mqtt_publish,
    encode_mqtt_subscribe,
    sign_iot_websocket_url,
    sign_sigv4_headers,
)
from custom_components.morning.models import MorningMachine, MorningRecipe


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
        sig_idx = url.index("X-Amz-Signature=")
        token_idx = url.index("X-Amz-Security-Token=")
        self.assertGreater(token_idx, sig_idx)

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

        # Test QoS 1 PUBLISH packet (0x32) with 2-byte Packet Identifier (0x002A = 42)
        packet_id = 42
        qos1_body = struct.pack("!H", len(topic_bytes)) + topic_bytes + struct.pack("!H", packet_id) + payload
        qos1_data = bytes([0x32, len(qos1_body)]) + qos1_body
        dec_q1 = decode_mqtt_publish_packet(qos1_data)
        self.assertIsNotNone(dec_q1)
        q1_topic, q1_payload, q1_pid = dec_q1
        self.assertEqual(q1_topic, topic)
        self.assertEqual(q1_payload, payload)
        self.assertEqual(q1_pid, 42)

        # decode_mqtt_publish also strips QoS 1 packet identifier cleanly
        dec_q1_compat = decode_mqtt_publish(qos1_data)
        self.assertEqual(dec_q1_compat, (topic, payload))

        # Test PUBACK encoding
        puback = encode_mqtt_puback(42)
        self.assertEqual(puback, bytes([0x40, 0x02, 0x00, 42]))

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
        # Total water = bypass (55.4) + mass (54.1) = 109.5 ml
        self.assertAlmostEqual(telem.water_output, 109.5, places=1)
        self.assertEqual(telem.mass_output, 54.1)
        self.assertEqual(telem.temperature, 94)
        self.assertEqual(telem.bloom_lapse, 12)

        # Espresso test: waterOutput is 0.0, massOutput is 36.5
        espresso_packet = {
            "name": "BrewCoffee.Response",
            "data": {
                "progress": {
                    "status": "BREWING",
                    "waterOutput": 0.0,
                    "massOutput": 36.5,
                    "temperature": 92,
                    "bloomLapse": 0,
                }
            },
        }
        esp_telem = decode_brew_progress_payload(espresso_packet)
        self.assertIsNotNone(esp_telem)
        self.assertEqual(esp_telem.water_output, 36.5)
        self.assertEqual(esp_telem.mass_output, 36.5)

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
        self.assertAlmostEqual(done_telem.water_output, 297.8, places=1)

        # Shadow ready packet
        ready_packet = {
            "state": {
                "reported": {
                    "status": "ready"
                }
            }
        }
        ready_telem = decode_brew_progress_payload(ready_packet)
        self.assertIsNotNone(ready_telem)
        self.assertFalse(ready_telem.is_brewing)
        self.assertEqual(ready_telem.stage, "ready")

        # Top-level idle packet
        idle_packet = {"status": "IDLE"}
        idle_telem = decode_brew_progress_payload(idle_packet)
        self.assertIsNotNone(idle_telem)
        self.assertFalse(idle_telem.is_brewing)
        self.assertEqual(idle_telem.stage, "idle")

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

        # Match by AWS shadow topic
        topic_shadow = "$aws/things/M_123/shadow/update/accepted"
        mid_shadow = listener._resolve_machine_id(topic_shadow)
        self.assertEqual(mid_shadow, "M_123")

        # Match by payload machineId on mobile app random UUID response topic
        mobile_topic = "PROD/user/phone_identity_999/random_uuid_abc/response"
        mid_mobile = listener._resolve_machine_id(
            mobile_topic,
            payload_dict={"machineId": "M_123", "name": "BrewCoffee.Response"},
            own_identity_id="ha_identity_111",
        )
        self.assertEqual(mid_mobile, "M_123")

        # Reject foreign machine on wildcard topic
        mid_foreign = listener._resolve_machine_id(
            mobile_topic,
            payload_dict={"machineId": "M_FOREIGN_999", "name": "BrewCoffee.Response"},
            own_identity_id="ha_identity_111",
        )
        self.assertIsNone(mid_foreign)

    def test_decode_purge_payload(self):
        """Test decoding purge status messages from various MQTT payload formats."""
        # Format 1: data.status
        p1 = {"data": {"status": "PURGE"}}
        t1 = decode_brew_progress_payload(p1)
        self.assertIsNotNone(t1)
        self.assertEqual(t1.stage, "purge")
        self.assertTrue(t1.is_brewing)

        # Format 2: shadow reported state
        p2 = {"state": {"reported": {"settings": {"status": "PURGE"}}}}
        t2 = decode_brew_progress_payload(p2)
        self.assertIsNotNone(t2)
        self.assertEqual(t2.stage, "purge")
        self.assertTrue(t2.is_brewing)

        # Format 3: top-level status
        p3 = {"status": "PURGE"}
        t3 = decode_brew_progress_payload(p3)
        self.assertIsNotNone(t3)
        self.assertEqual(t3.stage, "purge")
        self.assertTrue(t3.is_brewing)

    def test_decode_heating_payload(self):
        """Test decoding heating stage messages across payload formats."""
        # Format 1: data.status
        p1 = {"data": {"status": "HEATING", "temperature": 93}}
        t1 = decode_brew_progress_payload(p1)
        self.assertIsNotNone(t1)
        self.assertEqual(t1.stage, "heating")
        self.assertTrue(t1.is_brewing)
        self.assertEqual(t1.temperature, 93)

        # Format 2: shadow reported state
        p2 = {"state": {"reported": {"settings": {"status": "heating", "temperature": 91}}}}
        t2 = decode_brew_progress_payload(p2)
        self.assertIsNotNone(t2)
        self.assertEqual(t2.stage, "heating")
        self.assertTrue(t2.is_brewing)
        self.assertEqual(t2.temperature, 91)

        # Format 3: top-level status
        p3 = {"status": "HEATING", "temperature": 88}
        t3 = decode_brew_progress_payload(p3)
        self.assertIsNotNone(t3)
        self.assertEqual(t3.stage, "heating")
        self.assertTrue(t3.is_brewing)
        self.assertEqual(t3.temperature, 88)

    def test_decode_direct_telemetry_payload(self):
        """Test decoding telemetry when data contains progress directly without nested progress dict."""
        p = {
            "name": "BrewCoffee.Progress",
            "data": {
                "status": "BREWING",
                "waterOutput": 40.0,
                "massOutput": 35.0,
                "temperature": 92,
                "bloomLapse": 5,
            },
        }
        t = decode_brew_progress_payload(p)
        self.assertIsNotNone(t)
        self.assertEqual(t.stage, "brewing")
        self.assertTrue(t.is_brewing)
        self.assertAlmostEqual(t.water_output, 75.0)
        self.assertEqual(t.mass_output, 35.0)
        self.assertEqual(t.temperature, 92)

    def test_decode_blooming_and_cancel_payloads(self):
        """Test decoding active blooming and cancel messages."""
        bloom_p = {
            "data": {
                "progress": {
                    "status": "BREWING",
                    "waterOutput": 0.0,
                    "massOutput": 2.0,
                    "temperature": 93,
                    "bloomLapse": 4,
                }
            }
        }
        tb = decode_brew_progress_payload(bloom_p)
        self.assertIsNotNone(tb)
        self.assertEqual(tb.stage, "blooming")
        self.assertTrue(tb.is_brewing)

        for cancel_p in (
            {"data": {"progress": {"status": "cancel", "waterOutput": 0.0, "massOutput": 0.0}}},
            {"data": {"status": "CANCEL"}},
            {"state": {"reported": {"settings": {"status": "cancelled"}}}},
            {"status": "abort"},
        ):
            tc = decode_brew_progress_payload(cancel_p)
            self.assertIsNotNone(tc)
            self.assertEqual(tc.stage, "cancel")
            self.assertFalse(tc.is_brewing)

    def test_encode_mqtt_publish(self):
        """Test encoding MQTT PUBLISH packets with QoS 0 and QoS 1."""
        topic = "PROD/user/id123/uuid456/command"
        payload = b'{"action":"BREW","apiVersion":2}'

        # QoS 1 with packet_id
        pkt_q1 = encode_mqtt_publish(topic, payload, packet_id=105, qos=1)
        self.assertEqual(pkt_q1[0], 0x32)
        decoded_q1 = decode_mqtt_publish_packet(pkt_q1)
        self.assertIsNotNone(decoded_q1)
        self.assertEqual(decoded_q1[0], topic)
        self.assertEqual(decoded_q1[1], payload)
        self.assertEqual(decoded_q1[2], 105)

        # QoS 0
        pkt_q0 = encode_mqtt_publish(topic, payload, qos=0)
        self.assertEqual(pkt_q0[0], 0x30)
        decoded_q0 = decode_mqtt_publish_packet(pkt_q0)
        self.assertIsNotNone(decoded_q0)
        self.assertEqual(decoded_q0[0], topic)
        self.assertEqual(decoded_q0[1], payload)
        self.assertIsNone(decoded_q0[2])

    async def test_async_brew_and_cancel_commands(self):
        """Test async_brew_coffee and async_cancel_brew payload generation and publishing."""
        from unittest.mock import AsyncMock

        coordinator = MagicMock()
        client = MagicMock()
        client.auth_session = MagicMock()
        client.auth_session.user_id = "user_sub_uuid"
        session = MagicMock()

        listener = MorningIotListener(coordinator=coordinator, client=client, session=session)
        listener._identity_id = "ap-southeast-1:test-identity"
        listener.async_publish_command = AsyncMock()

        recipe = MorningRecipe(
            name="Morning Espresso",
            temperature=94,
            mass_output=40,
            water_output=0,
            bloom_duration=10,
            stages=[
                {"id": 0, "output": 0, "pressure": 3},
                {"id": 1, "output": 5, "pressure": 7},
                {"id": 2, "output": 35, "pressure": 5},
            ],
        )

        await listener.async_brew_coffee("M_TEST_1", recipe)
        listener.async_publish_command.assert_called_once()
        cmd_payload = listener.async_publish_command.call_args[0][0]
        self.assertEqual(cmd_payload["action"], "BREW")
        self.assertEqual(cmd_payload["apiVersion"], 2)
        self.assertEqual(cmd_payload["machineId"], "M_TEST_1")
        self.assertEqual(cmd_payload["userId"], "ap-southeast-1:test-identity")
        self.assertEqual(cmd_payload["appUserId"], "user_sub_uuid")
        self.assertEqual(cmd_payload["data"]["type"], "COFFEE_RECIPE")
        self.assertEqual(cmd_payload["data"]["recipe"]["name"], "Morning Espresso")
        self.assertEqual(cmd_payload["data"]["recipe"]["temperature"], 94)
        self.assertEqual(cmd_payload["data"]["recipe"]["massOutput"], 40)
        coordinator.handle_live_brew_update.assert_called_once()
        telem = coordinator.handle_live_brew_update.call_args[0][1]
        self.assertEqual(telem.stage, "heating")
        self.assertTrue(telem.is_brewing)

        # Cancel brew
        await listener.async_cancel_brew("M_TEST_1")
        self.assertEqual(listener.async_publish_command.call_count, 2)
        cancel_cmd = listener.async_publish_command.call_args[0][0]
        self.assertEqual(cancel_cmd["action"], "CANCEL")
        self.assertEqual(cancel_cmd["machineId"], "M_TEST_1")
        self.assertIsNone(cancel_cmd["data"])
        cancel_telem = coordinator.handle_live_brew_update.call_args[0][1]
        self.assertEqual(cancel_telem.stage, "cancel")
        self.assertFalse(cancel_telem.is_brewing)


if __name__ == "__main__":
    unittest.main()
