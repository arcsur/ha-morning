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
  - **Cancel Reset & Water Refund**:
    - On `CANCEL` (via live IoT or when a REST-polled `BREWING` transitions to `IDLE`/`READY`/`ECO` with `brew_count_incremented == False` and `water_delta == 0`), immediately reset `brew_stage` to `"idle"` (`is_brewing = False`) and refund any unconsumed polling fallback water volume.
  - **Dual-Cadence Synchronization (1 Hz IoT vs. 30s REST Poll)**:
    - `MorningStatusSensor`, `MorningBrewingBinarySensor`, and `MorningCoffeeCard` must treat fresh `live_telemetry` stages (`"heating"`, `"blooming"`, `"brewing"`, `"purge"`, `"done"`, `"cancel"`, `"idle"`) as authoritative over a lagged 30s REST poll (`machine.status`).
  - **Token Persistence Without Self-Reload**:
    - Guard `async_reload_entry` in `__init__.py` by comparing `dict(entry.options)` against stored options so persisting refreshed Cognito tokens via `hass.config_entries.async_update_entry(..., data=new_data)` never unloads/reloads the integration or kills `MorningIotListener`.
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
   - In `registerOrHotPatch(tagName, cls)`: copy both prototype properties (`cls.prototype`) and static constructor properties/methods (`cls`, e.g. `getConfigElement`, `getStubConfig`) onto existing constructors.
   - Dispatch `window.dispatchEvent(new CustomEvent("ll-custom-elements-loaded"))` and `window.dispatchEvent(new CustomEvent("ll-rebuild"))` upon custom element registration so Lovelace immediately rebuilds any placeholder error cards (`Custom element doesn't exist: ...`) rendered during early boot before the script finished evaluating.
   - Auto-resolve sibling entities from the status sensor entity ID (`sensor.<slug>_status`) by device name pattern matching.

6. **Static Resource Registration & Boot Invariants**:
   - Always keep `"dependencies": ["http", "frontend"]` in `manifest.json` so Home Assistant initializes `hass.http` and `frontend` before calling `async_setup` or `async_setup_entry`.
   - Always register static HTTP paths (`hass.http.async_register_static_paths`) and inject extra JS in component-level `async_setup(hass, config)` as well as at the very top of `async_setup_entry(hass, entry)` before any coordinator network calls (`async_config_entry_first_refresh`). Lovelace queries dashboard resources concurrently during early Home Assistant boot; registering static paths after network calls produces early 404s that poison browser ES module resolution.
   - Mirror `morning-coffee-card.js` into `<config_dir>/www/morning-card/morning-coffee-card.js` inside `_async_register_frontend` so Home Assistant's core `/local/` static handler serves `/local/morning-card/morning-coffee-card.js` before custom integrations finish booting.
   - Never set `hass.data["morning_frontend_registered"] = True` unless `hass.http` is present and static path registration actually succeeded (`static_registered = True`).
   - Avoid blocking file I/O inside the asyncio event loop: wrap file reads (such as `manifest.json`) in `await hass.async_add_executor_job(...)`.

### 4. Testing & Development Workflow (Inner Loop)
- **Frontend Card Automated Tests**:
  - Run `npm test` (via Vitest + JSDOM) to verify entity resolution, stage progressions, sticky telemetry, and SVG extraction curves.
  - Tests run in < 1 second against shared fixtures in `tests/fixtures/`.
  - Always test **desynchronized/lagged sensor states** (e.g., `brew_stage: "cancel"` or `"idle"` while `status: "brewing"` lags from the 30s REST poll, and `brew_stage: "heating"` / `"blooming"` while `status: "eco"`).
- **Backend Tests**:
  - Run `.venv/bin/pytest` and `.venv/bin/ruff check`.
- **Fast Visual Dev Harness**:
  - Run `npm run harness` (or `python3 -m http.server 8080`) and open `http://localhost:8080/dev/harness/index.html` in browser.
  - Test UI changes live with instant reload on file save (Cmd+R), scenario presets (`Heating`, `Blooming`, `Brewing`, `Cancel`, `Done`, `Purge`, `Water Low`, `Boot Race`), metric sliders, and real-time brew playback.
  - **Do NOT bump versions, tag git, or invoke HACS during inner-loop development.**

### 5. Integration Release & Deployment Protocol (Outer Loop)
- When modifications are fully verified in tests and the dev harness:
  1. Bump version synchronously in `manifest.json`, `pyproject.toml`, `package.json`, and `morning-coffee-card.js`.
  2. Update frontend asset version assertion in `tests/test_init.py` and verify `npm test`, `pytest`, and `ruff` pass.
  3. Commit and tag release (`git tag vX.Y.Z && git push origin main --tags`).
  4. Refresh HACS repository info (`ha_manage_hacs(action="update_information", repository_id="1425736971")`).
  5. Download updated version in HACS (`ha_manage_hacs(action="download", repository_id="1425736971", version="vX.Y.Z")`).
  6. Restart Home Assistant (`ha_restart`) and **wait** (using `schedule` timer + `ha_get_integration(query="morning")`) until Home Assistant is back online and the integration state is `"loaded"`.
  7. Only **after** the integration is `"loaded"`, update the dashboard resource URL (`ha_config_set_dashboard_resource(..., url="/local/morning-card/morning-coffee-card.js?v=X.Y.Z")`) and verify `ha_get_logs(source="error_log")` has zero startup/frontend errors so open browser tabs never fetch during a restart-window 404.

