"""Unit tests for Morning data models."""

import unittest
from custom_components.morning.models import MorningAuthSession, MorningFirmware, MorningMachine


class TestMorningModels(unittest.TestCase):
    """Test Morning models parsing and methods."""

    def test_firmware_parsing(self):
        """Test MorningFirmware parsing."""
        data = {
            "current": "1.2.0",
            "isLatest": True,
            "latestVersion": "1.2.0",
        }
        fw = MorningFirmware.from_dict(data)
        self.assertIsNotNone(fw)
        self.assertEqual(fw.current, "1.2.0")
        self.assertTrue(fw.is_latest)
        self.assertEqual(fw.latest_version, "1.2.0")

        # None case
        self.assertIsNone(MorningFirmware.from_dict(None))

    def test_machine_parsing(self):
        """Test MorningMachine parsing from JSON dict."""
        data = {
            "id": "M_AC67B25AC974",
            "name": "Kitchen Morning Machine",
            "model": "MM-730",
            "firmwareVersion": "1.2.0",
            "active": True,
            "online": True,
            "type": "COFFEE",
            "subType": "STANDARD",
            "icon": "https://example.com/icon.png",
            "photo": "https://example.com/photo.jpg",
            "recipeSlots": 10,
            "status": "ECO",
            "waterLevel": "NORMAL",
            "limeScale": 142,
            "brewCount": 58,
            "energySaveTimeOut": 1800,
            "mac": "AC:67:B2:5A:C9:74",
            "uuid": "FA2E9CAB-3178-D61A-1D29-A0974B2DEA9A",
            "firmware": {
                "current": "1.2.0",
                "isLatest": True,
            },
        }
        machine = MorningMachine.from_dict(data)
        self.assertEqual(machine.id, "M_AC67B25AC974")
        self.assertEqual(machine.name, "Kitchen Morning Machine")
        self.assertEqual(machine.model, "MM-730")
        self.assertEqual(machine.firmware_version, "1.2.0")
        self.assertTrue(machine.active)
        self.assertTrue(machine.online)
        self.assertEqual(machine.type, "COFFEE")
        self.assertEqual(machine.status, "ECO")
        self.assertEqual(machine.water_level, "NORMAL")
        self.assertEqual(machine.lime_scale, 142)
        self.assertEqual(machine.brew_count, 58)
        self.assertEqual(machine.energy_save_timeout, 1800)
        self.assertEqual(machine.mac, "AC:67:B2:5A:C9:74")
        self.assertEqual(machine.uuid, "FA2E9CAB-3178-D61A-1D29-A0974B2DEA9A")
        self.assertIsNotNone(machine.firmware)
        self.assertEqual(machine.firmware.current, "1.2.0")

    def test_auth_session(self):
        """Test MorningAuthSession creation, serialization, and expiration."""
        result = {
            "AccessToken": "access_token_123",
            "IdToken": "id_token_456",
            "RefreshToken": "refresh_token_789",
            "ExpiresIn": 3600,
        }
        session = MorningAuthSession.from_cognito_result(result, "test@example.com")
        self.assertEqual(session.access_token, "access_token_123")
        self.assertEqual(session.id_token, "id_token_456")
        self.assertEqual(session.refresh_token, "refresh_token_789")
        self.assertEqual(session.email, "test@example.com")
        self.assertFalse(session.is_expired)

        # Test to_dict and from_dict
        d = session.to_dict()
        restored = MorningAuthSession.from_dict(d)
        self.assertEqual(restored.access_token, session.access_token)
        self.assertEqual(restored.id_token, session.id_token)
        self.assertEqual(restored.refresh_token, session.refresh_token)
        self.assertEqual(restored.email, session.email)

        # Test expired session
        expired_session = MorningAuthSession(
            access_token="tok",
            id_token="id",
            refresh_token="ref",
            expires_at=100.0,
            email="test@example.com",
        )
        self.assertTrue(expired_session.is_expired)


if __name__ == "__main__":
    unittest.main()
