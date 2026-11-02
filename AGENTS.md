# Project Instructions

- When modifying or re-deploying the integration (`morning`) or its Lovelace card, restart Home Assistant via `ha_restart` so updated Python modules and frontend assets reload into memory.

## Architecture & Domain Invariants

### 1. Water Tracking & Purge Handling
- **Purge vs. Brew Hardware Realities**:
  - The machine treats Purge as a cleaning cycle: it does **not** emit `BrewCoffee.Progress` live stream packets and intentionally does **not** increment `brewCount`.
  - Never tie water level decrement solely to `brewCount`.
- **3-Layer Water Tracking**:
  1. *Layer 1 (Status Edge)*: Decrement configured `purge_volume` (default 30 mL) upon transition from `PURGE` to `READY`/`IDLE`/`ECO`.
  2. *Layer 2 (Flow Meter Delta)*: Monitor cumulative `total_water_ml` from machine shadow; any unassociated positive delta ($\Delta_{\text{water}} > 0$) without an active brew must be decremented from the tank level.
  3. *Layer 3 (Manual Action)*: Expose `morning.record_purge` service and dashboard quick-action button.
- **Reservoir Level Estimation**:
  - Capacitive sensor `water_low` (`on` $\rightarrow$ `off`) auto-resets estimated tank volume to configured `tank_capacity` (default 850 mL).
  - Capacitive sensor `water_low` (`on`) clamps estimated level to 0 mL.
  - Always use `RestoreSensor` to persist water levels across Home Assistant restarts.

### 2. Live-to-Sticky Telemetry State Machine
- **Extraction Lifecycle**:
  - When status is `HEATING` or `BREWING`, stream live flow meter, scale mass, temperature, and bloom timer telemetry. Decrement water tank level live from pre-brew snapshot.
  - When status transitions to `DONE` or `CANCEL`, lock telemetry into persistent "sticky" values.
  - **Terminal Packet Guard**: Terminal completion packets often report `0` or null; always preserve the peak/last non-zero values from `prev_telem`.
  - **Sticky Metric Persistence**: Do not reset or zero out sticky telemetry when the machine transitions to `IDLE`, `READY`, or `ECO`. Values remain frozen on display until a new brew cycle begins.

### 3. Lovelace Card Guidelines
1. **Clickability & Hover UX**:
   - Do **not** use HTML `title` tooltips on interactive statistics, telemetry metrics, or progress bars.
   - Clickability must be indicated exclusively by changing the mouse cursor: enforce `cursor: pointer !important;` on the clickable element and all descendant nodes (`[data-entity-id], [data-entity-id] *`).

2. **State & Startup Defensive Coding**:
   - Never assume `hass.states` or entity `.attributes` are populated during card or editor initialization.
   - Always guard access with optional chaining (e.g., `this._hass?.states?.[entityId]?.attributes?.friendly_name || entityId`) to prevent Lovelace "Configuration error" crashes during early HA startup.
   - In `_resolveEntities()`: strictly guard `if (!this._hass?.states || !this._config?.entity) return;`. Never execute `Object.keys(states)` or string operations on uninitialized properties.
   - In `_getState(key)`: verify `this._hass?.states?.[this._resolvedEntities?.[key]] || null`.
   - In `_updateContent()`: guard with `if (!this._hass?.states)` and render a loading state rather than attempting entity queries.
   - For state attributes containing arrays or objects (such as `extraction_profile`): always validate with `Array.isArray(attr)` before invoking `.slice()`, `.map()`, or `.filter()`.

3. **Shadow DOM Event Dispatching**:
   - When firing Home Assistant native events (such as `hass-more-info` or `hass-action`) from within shadow DOM components, always instantiate `CustomEvent` (not generic `Event` with expando properties) with `{ bubbles: true, cancelable: true, composed: true, detail: { entityId } }` so the payload crosses shadow root boundaries intact.

4. **Frontend Asset Versioning & Cache Busting**:
   - When releasing updates to frontend cards, bump `CARD_VERSION` in the script, ensure `add_extra_js_url` in `__init__.py` serves `?v={version}`, and update the dashboard resource URL with the new version parameter.

5. **Component Lifecycle & Hot-Patching**:
   - Keep the card as a zero-build vanilla ES module in `custom_components/morning/frontend/morning-coffee-card.js`.
   - Use prototype hot-patching (`registerOrHotPatch`) so script re-fetches upgrade active card instances without requiring full window reloads.
   - Auto-resolve sibling entities from the status sensor entity ID (`sensor.<slug>_status`) by device name pattern matching.

### 4. Integration Release & Deployment Protocol
- When modifying integration backend code or the Lovelace card:
  1. Bump version synchronously in `manifest.json`, `pyproject.toml`, and `morning-coffee-card.js`.
  2. Update frontend asset version assertion in `tests/test_init.py` and verify `pytest` and `ruff` pass.
  3. Commit and tag release (`git tag vX.Y.Z && git push origin main --tags`).
  4. Refresh HACS repository info (`ha_manage_hacs(action="update_information", repository_id="1425736971")`).
  5. Download updated version in HACS (`ha_manage_hacs(action="download", repository_id="1425736971", version="vX.Y.Z")`).
  6. Update dashboard resource URL (`ha_config_set_dashboard_resource(..., url="/morning-card/morning-coffee-card.js?v=X.Y.Z")`).
  7. Restart Home Assistant (`ha_restart`) to ensure updated backend code and static card assets load cleanly into memory.
