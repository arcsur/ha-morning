"""Unit tests for Morning integration setup and teardown."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.morning import (
    async_reload_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.morning.const import (
    CONF_ACCESS_TOKEN,
    CONF_EMAIL,
    CONF_ID_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRES_AT,
    DOMAIN,
)


class TestMorningInit(unittest.IsolatedAsyncioTestCase):
    """Test setup and unload of Morning integration."""

    def setUp(self):
        """Set up test fixtures."""
        self.hass = MagicMock()
        self.hass.data = {}
        self.hass.async_add_executor_job = AsyncMock(side_effect=lambda func, *args: func(*args))
        self.hass.config_entries = MagicMock()
        self.hass.config_entries.async_forward_entry_setups = AsyncMock()
        self.hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        self.hass.config_entries.async_reload = AsyncMock()

        self.entry = MagicMock()
        self.entry.entry_id = "test_entry_id"
        self.entry.options = {}
        self.entry.data = {
            CONF_EMAIL: "user@example.com",
            CONF_ACCESS_TOKEN: "acc",
            CONF_ID_TOKEN: "id",
            CONF_REFRESH_TOKEN: "ref",
            CONF_TOKEN_EXPIRES_AT: 9999999999.0,
        }

    @patch("custom_components.morning.MorningDataUpdateCoordinator.async_config_entry_first_refresh", new_callable=AsyncMock)
    @patch("custom_components.morning.MorningIotListener.start")
    @patch("custom_components.morning.async_setup_services", new_callable=AsyncMock)
    async def test_setup_and_unload_entry(self, mock_setup_services, mock_iot_start, mock_refresh):
        """Test full setup and unload cycle."""
        # 1. Setup entry
        res = await async_setup_entry(self.hass, self.entry)
        self.assertTrue(res)
        self.assertIn(DOMAIN, self.hass.data)
        self.assertIn(self.entry.entry_id, self.hass.data[DOMAIN])
        mock_refresh.assert_called_once()
        mock_iot_start.assert_called_once()
        mock_setup_services.assert_called_once()

        # 2. Unload entry
        with patch.object(self.hass.data[DOMAIN][self.entry.entry_id]["iot_listener"], "stop", new_callable=AsyncMock) as mock_iot_stop:
            unload_ok = await async_unload_entry(self.hass, self.entry)
            self.assertTrue(unload_ok)
            mock_iot_stop.assert_called_once()
            self.assertNotIn(self.entry.entry_id, self.hass.data[DOMAIN])

    async def test_async_setup(self):
        """Test component level async_setup."""
        with patch("custom_components.morning._async_register_frontend", new_callable=AsyncMock) as mock_reg:
            res = await async_setup(self.hass, {})
            self.assertTrue(res)
            mock_reg.assert_called_once_with(self.hass)

    async def test_reload_entry(self):
        """Test reload entry callback."""
        await async_reload_entry(self.hass, self.entry)
        self.hass.config_entries.async_reload.assert_called_once_with(self.entry.entry_id)

    async def test_register_frontend(self):
        """Test custom card static path and extra js url registration."""
        from custom_components.morning import _async_register_frontend

        self.hass.http = MagicMock()
        self.hass.http.async_register_static_paths = AsyncMock()
        self.hass.data = {}

        with patch("homeassistant.components.frontend.add_extra_js_url") as mock_add_js:
            await _async_register_frontend(self.hass)
            self.assertTrue(self.hass.data.get("morning_frontend_registered"))
            self.hass.http.async_register_static_paths.assert_called_once()
            mock_add_js.assert_called_once_with(self.hass, "/morning-card/morning-coffee-card.js?v=1.4.2")

            # Second call should be a no-op due to idempotency guard
            await _async_register_frontend(self.hass)
            self.assertEqual(self.hass.http.async_register_static_paths.call_count, 1)


if __name__ == "__main__":
    unittest.main()
