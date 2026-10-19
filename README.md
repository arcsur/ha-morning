# Morning Coffee Machine Integration for Home Assistant

[![Hassfest](https://github.com/arcsur/ha-morning/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/arcsur/ha-morning/actions/workflows/hassfest.yaml)
[![HACS](https://github.com/arcsur/ha-morning/actions/workflows/hacs.yaml/badge.svg)](https://github.com/arcsur/ha-morning/actions/workflows/hacs.yaml)
[![Tests](https://github.com/arcsur/ha-morning/actions/workflows/tests.yaml/badge.svg)](https://github.com/arcsur/ha-morning/actions/workflows/tests.yaml)
[![HACS Default](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

A modern Home Assistant integration for **[The Morning Machine](https://drinkmorning.com)** (model MM-730).

Integrate your Morning coffee machine with Home Assistant using your official Drink Morning mobile account credentials. The integration automatically discovers your machines, synchronizes machine state, monitors water level and limescale accumulation, and lets you adjust standby sleep settings and trigger maintenance actions.

---

## Features

- **Seamless Cloud Discovery**: Log in with your Morning mobile app email and password. All paired machines are automatically discovered—no need to configure local IPs, Bluetooth pairing, or MAC addresses.
- **Real-Time Telemetry & Status**:
  - Operational state (`Ready`, `Eco Mode`, `Brewing`, `Water Refill Needed`, `Maintenance`, `Hardware Fault`, etc.)
  - Total brew cycles count (`state_class: total_increasing`)
  - Limescale accumulation / descaling urgency meter
  - Current firmware version and update availability
- **Binary Sensors**:
  - **Water Tank Low**: Problem sensor indicating when the reservoir requires refilling.
  - **Cloud Connection**: Connectivity sensor tracking whether the machine is online.
  - **Brewing**: Running indicator indicating active coffee brewing.
- **Control & Configuration**:
  - **Standby Timeout Setting**: Adjust the machine's auto-sleep timeout directly from Home Assistant (from 5 minutes up to 2 hours).
  - **Reset Machine**: Button entity to send a soft restart command to the machine.
  - **Check Updates**: Button entity to check for OTA firmware updates.
- **Custom Services**:
  - `morning.set_standby_timeout`: Programmatically adjust auto-sleep durations in automations.
  - `morning.reset_machine`: Trigger machine reboot.
  - `morning.check_updates`: Query cloud backend for latest firmware.
- **Built for Modern Home Assistant Standards**:
  - Config Flow with single and multi-machine support.
  - Reauthentication flow if account passwords change.
  - Fully typed `DataUpdateCoordinator` with automated token refresh.
  - Configurable polling interval via Options Flow (10s – 300s).

---

## How It Works

```
┌─────────────────────────┐          ┌──────────────────────────────────┐          ┌───────────────────────┐
│     Home Assistant      │  HTTPS   │  Morning Cloud Backend (Akronym) │   MQTT   │    Morning Machine    │
│  (DataUpdateCoordinator)├─────────►│  • AWS Cognito User Pool         ├─────────►│  (In Your Kitchen)    │
│                         │          │  • REST API (api.akronym.link)   │          │                       │
└─────────────────────────┘          └──────────────────────────────────┘          └───────────────────────┘
```

1. **Authentication**: Home Assistant authenticates against Akronym's AWS Cognito User Pool (`ap-southeast-1_35sNfBuQq`) using HMAC-SHA256 authenticated secret hashes.
2. **Machine Enumeration**: Home Assistant queries `GET /v2/machine/user` using the Bearer token to retrieve registered machines, hardware IDs (`M_<MAC>`), and custom names.
3. **State Polling**: The `DataUpdateCoordinator` periodically polls the machine telemetry and automatically refreshes tokens in the background before they expire.

---

## Installation

### Method 1: HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance.
2. In Home Assistant, navigate to **HACS** > **Integrations**.
3. Click the three dots in the top right corner and choose **Custom repositories**.
4. Enter the repository URL:
   ```
   https://github.com/arcsur/ha-morning
   ```
5. Select **Integration** as the Category and click **Add**.
6. Find **Morning Coffee Machine** in the integration list and click **Download**.
7. Restart Home Assistant.

### Method 2: Manual Installation

1. Download the latest release from the [Releases](https://github.com/arcsur/ha-morning/releases) page.
2. Copy the `custom_components/morning/` folder into your Home Assistant `<config_dir>/custom_components/` directory:
   ```
   <config_dir>/
   └── custom_components/
       └── morning/
           ├── __init__.py
           ├── manifest.json
           ├── config_flow.py
           ├── ...
   ```
3. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, go to **Settings** > **Devices & Services**.
2. Click **Add Integration** and search for **Morning Coffee Machine**.
3. Enter your **Morning Account Email** and **Password** (the same credentials you use in the Drink Morning mobile app).
4. Home Assistant will discover your coffee machine. If you have multiple machines, you will be prompted to select which ones to add.
5. Click **Submit**. Your Morning machine is now ready!

### Options

To change the polling frequency:
1. Go to **Settings** > **Devices & Services** > **Morning Coffee Machine**.
2. Click **Configure**.
3. Adjust the **Polling interval** (default: 30 seconds).

---

## Entities Provided

| Entity Type | Name | Object ID | Description |
| :--- | :--- | :--- | :--- |
| **Sensor** | Status | `sensor.<machine>_status` | Current machine status (`Ready`, `Eco`, `Brewing`, `Water`, etc.) |
| **Sensor** | Total Brews | `sensor.<machine>_brew_count` | Lifetime coffee brew count |
| **Sensor** | Limescale Counter | `sensor.<machine>_limescale` | Descaling urgency meter |
| **Sensor** | Standby Timeout | `sensor.<machine>_standby_timeout` | Configured auto-off duration in seconds |
| **Sensor** | Firmware | `sensor.<machine>_firmware` | Currently installed firmware version |
| **Binary Sensor** | Water Tank Low | `binary_sensor.<machine>_water_low` | On when the water tank level is LOW |
| **Binary Sensor** | Cloud Connection | `binary_sensor.<machine>_connectivity` | On when the machine is online |
| **Binary Sensor** | Brewing | `binary_sensor.<machine>_brewing` | On when actively brewing |
| **Number** | Standby Timeout Setting | `number.<machine>_standby_timeout_setting` | Slider/box to set standby timeout (300–7200s) |
| **Button** | Reset Machine | `button.<machine>_reset` | Sends soft restart command |
| **Button** | Check Firmware Updates | `button.<machine>_check_updates` | Queries cloud for new firmware updates |

---

## Example Automations

### 1. Alert when Water Tank is Low

```yaml
alias: "Morning Machine: Water Tank Low Notification"
description: "Send push notification when coffee machine water tank is empty"
trigger:
  - platform: state
    entity_id: binary_sensor.morning_machine_water_low
    to: "on"
action:
  - service: notify.notify
    data:
      title: "☕ Morning Coffee Machine"
      message: "The water tank is low. Please refill the reservoir before brewing."
```

### 2. Notify when Coffee Brewing is Finished

```yaml
alias: "Morning Machine: Coffee Brew Finished"
description: "Notify household when coffee extraction completes"
trigger:
  - platform: state
    entity_id: binary_sensor.morning_machine_brewing
    from: "on"
    to: "off"
condition:
  - condition: state
    entity_id: sensor.morning_machine_status
    state: "ready"
action:
  - service: notify.notify
    data:
      title: "☕ Coffee is Ready!"
      message: "Your Morning coffee machine has finished brewing."
```

### 3. Automatically Extend Standby Timeout During Breakfast

```yaml
alias: "Morning Machine: Morning Standby Boost"
description: "Keep machine awake longer during breakfast hours"
trigger:
  - platform: time
    at: "07:00:00"
action:
  - service: number.set_value
    target:
      entity_id: number.morning_machine_standby_timeout_setting
    data:
      value: 3600  # 1 hour
```

---

## Troubleshooting

- **"Invalid authentication"**: Ensure you are using the email and password for your Morning mobile application account.
- **"No devices found"**: You must first pair your Morning Machine to your home Wi-Fi network and account using the official Drink Morning mobile application (iOS / Android). Once linked in the app, Home Assistant will immediately find it.
- **Reauthentication**: If your account password changes, Home Assistant will mark the integration as requiring reauthentication and prompt you for your updated password without losing entity histories or automations.

---

## Contributing & License

Contributions, bug reports, and pull requests are welcome!

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for details.
