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
CONF_TANK_CAPACITY: Final = "tank_capacity"
CONF_FALLBACK_BREW_VOLUME: Final = "fallback_brew_volume"
CONF_PURGE_VOLUME: Final = "purge_volume"
CONF_ENABLE_IOT_STREAM: Final = "enable_iot_stream"

# Default intervals & capacities
DEFAULT_SCAN_INTERVAL: Final = 30  # seconds
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 300
DEFAULT_TANK_CAPACITY: Final = 850  # ml
DEFAULT_FALLBACK_BREW_VOLUME: Final = 50  # ml
DEFAULT_PURGE_VOLUME: Final = 30  # ml

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
COGNITO_IDENTITY_POOL_ID: Final = "ap-southeast-1:f5305f0e-09c7-4f5d-b390-153d2c998a5f"

# AWS IoT Core endpoints & policies
AWS_IOT_ENDPOINT: Final = "a8lnp0dy0uxch-ats.iot.ap-southeast-1.amazonaws.com"
AWS_IOT_REGION: Final = "ap-southeast-1"
AWS_IOT_POLICY_NAME: Final = "PRODUserIotPolicy"

# Akronym / Morning Cloud REST API
API_BASE_URL: Final = "https://api.akronym.link/v2/"
API_USER_AGENT: Final = "Morning-HomeAssistant/1.0.0"

# Service Names & Attributes
SERVICE_SET_STANDBY_TIMEOUT: Final = "set_standby_timeout"
SERVICE_RESET_MACHINE: Final = "reset_machine"
SERVICE_CHECK_UPDATES: Final = "check_updates"
SERVICE_REFILL_WATER: Final = "refill_water"
SERVICE_RECORD_PURGE: Final = "record_purge"
SERVICE_BREW_RECIPE: Final = "brew_recipe"
SERVICE_CANCEL_BREW: Final = "cancel_brew"
SERVICE_SEARCH_RECIPES: Final = "search_recipes"
SERVICE_SAVE_PROFILE: Final = "save_profile"
SERVICE_TOGGLE_FAVORITE: Final = "toggle_favorite"
ATTR_AMOUNT_ML: Final = "amount_ml"

# Machine Statuses
STATUS_ECO: Final = "ECO"
STATUS_IDLE: Final = "IDLE"
STATUS_READY: Final = "READY"
STATUS_HEATING: Final = "HEATING"
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
