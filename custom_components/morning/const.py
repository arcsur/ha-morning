"""Constants for the Morning Coffee Machine integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "morning"

# Configuration keys
CONF_EMAIL: Final = "email"
CONF_PASSWORD: Final = "password"
CONF_ACCESS_TOKEN: Final = "access_token"
CONF_ID_TOKEN: Final = "id_token"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_TOKEN_EXPIRES_AT: Final = "token_expires_at"
CONF_USER_ID: Final = "user_id"
CONF_MACHINE_ID: Final = "machine_id"
CONF_MACHINE_IDS: Final = "machine_ids"
CONF_SCAN_INTERVAL: Final = "scan_interval"

# Default intervals
DEFAULT_SCAN_INTERVAL: Final = 30  # seconds
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 300

# Supported Platforms
PLATFORMS: Final[list[Platform]] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.BUTTON,
]

# AWS Cognito Identity Provider endpoints & credentials
COGNITO_REGION: Final = "ap-southeast-1"
COGNITO_USER_POOL_ID: Final = "ap-southeast-1_35sNfBuQq"
COGNITO_CLIENT_ID: Final = "2cdkqojjd6hfcq6i75tqcfrij7"
COGNITO_CLIENT_SECRET: Final = "kaear8a337jnbnfm285jn0esik1agt2fr9hvq9kenk9n5proaot"
COGNITO_ENDPOINT: Final = "https://cognito-idp.ap-southeast-1.amazonaws.com/"

# Akronym / Morning Cloud REST API
API_BASE_URL: Final = "https://api.akronym.link/v2/"
API_USER_AGENT: Final = "Morning-HomeAssistant/1.0.0"

# Service Names
SERVICE_SET_STANDBY_TIMEOUT: Final = "set_standby_timeout"
SERVICE_RESET_MACHINE: Final = "reset_machine"
SERVICE_CHECK_UPDATES: Final = "check_updates"

# Machine Statuses
STATUS_ECO: Final = "ECO"
STATUS_IDLE: Final = "IDLE"
STATUS_READY: Final = "READY"
STATUS_BREWING: Final = "BREWING"
STATUS_WATER: Final = "WATER"
STATUS_MAINTENANCE: Final = "MAINTENANCE"
STATUS_MAINTAIN: Final = "MAINTAIN"
STATUS_POWER_OFF: Final = "POWER_OFF"
STATUS_FAULT: Final = "FAULT"
STATUS_OTA: Final = "OTA"
STATUS_SCALE: Final = "SCALE"
STATUS_SETTING: Final = "SETTING"
STATUS_QUERYING: Final = "QUERYING"
STATUS_PURGE: Final = "PURGE"
STATUS_WIFI_SETUP: Final = "WIFI_SETUP"
STATUS_SCALE_RATE: Final = "SCALE_RATE"
STATUS_FACTORY_RESETTING: Final = "FACTORY_RESETTING"

# Water Levels
WATER_LEVEL_NORMAL: Final = "NORMAL"
WATER_LEVEL_LOW: Final = "LOW"
WATER_LEVEL_NOT_AVAILABLE: Final = "NOT_AVAILABLE"
