/**
 * Morning Coffee Machine Lovelace Card
 * Custom card displaying machine diagnostics, water level, and live brewing telemetry.
 */

const CARD_VERSION = "1.6.0";

const STAGE_ORDER = ["heating", "blooming", "brewing", "done"];

const STATUS_COLORS = {
  ready: "#2ecc71",
  idle: "#2ecc71",
  eco: "#00b894",
  brewing: "#e67e22",
  heating: "#f39c12",
  water: "#e74c3c",
  maintenance: "#e67e22",
  fault: "#c0392b",
  power_off: "#7f8c8d",
  done: "#2ecc71",
  purge: "#e67e22",
};

const AVAILABLE_STATUS_ITEMS = [
  { id: "total_brews", label: "Total Brews" },
  { id: "limescale", label: "Limescale Counter" },
  { id: "child_lock", label: "Child Lock" },
  { id: "standby", label: "Standby Timeout" },
  { id: "firmware", label: "Firmware Version" },
  { id: "slave_firmware", label: "Motor Controller Firmware" },
  { id: "lifetime_water", label: "Lifetime Water" },
  { id: "fault_code", label: "Fault Code" },
];

const DEFAULT_STATUS_ITEMS = ["total_brews", "limescale", "child_lock"];

class MorningCoffeeCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._resolvedEntities = {};
    this._brewDrawerOpen = false;
    this._activeBrewTab = "saved";
    this._savedSubTab = "favorites";
    this._activePresetKey = "custom";
    this._draftCurve = {
      id: 0,
      name: "Custom Profile",
      temperature: 94,
      mass_output: 40,
      water_output: 0,
      bloom_enabled: false,
      bloom_duration: 10,
      bypass_enabled: false,
      stages: [
        { id: 0, output: 0, pressure: 3 },
        { id: 1, output: 5, pressure: 7 },
        { id: 2, output: 35, pressure: 5 },
      ],
      is_favorite: false,
    };
    this._isDraggingHandle = false;
    this._activeHandleIndex = -1;
    this._searchQuery = "";
    this._searchResults = [];
    this._isSearching = false;
    this._confirmBrewProfile = null;
    this._brewSectionDirty = true;
    this._lastBrewingState = false;
    this._savedDrawerScroll = 0;
    this._savedProfileScroll = 0;
    this._setupClickListener();
  }

  static getStubConfig(hass, entities) {
    const entityList = Array.isArray(entities)
      ? entities
      : (hass && hass.states ? Object.keys(hass.states) : []);
    const statusEntity = entityList.find(
      (e) => e.startsWith("sensor.") && (e.endsWith("_status") || e.includes("morning"))
    );
    return {
      type: "custom:morning-coffee-card",
      entity: statusEntity || "sensor.dagusmorning_status",
      show_header: true,
      show_brew_section: true,
      show_brew_controls: true,
      show_extraction_curve: true,
      show_water_gauge: true,
      show_diagnostics: true,
      status_items: [...DEFAULT_STATUS_ITEMS],
    };
  }

  static getConfigElement() {
    return document.createElement("morning-coffee-card-editor");
  }

  setConfig(config) {
    if (!config) {
      throw new Error("Invalid configuration");
    }
    this._config = {
      name: null,
      show_header: true,
      show_brew_section: true,
      show_brew_controls: true,
      show_extraction_curve: true,
      show_water_gauge: true,
      show_diagnostics: true,
      status_items: [...DEFAULT_STATUS_ITEMS],
      ...config,
    };
    this._resolvedEntities = {};
    this._render();
  }

  get hass() {
    return this._hass;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;

    if (this._config.entity && this._hass && this._hass.states) {
      const needsResolve =
        Object.keys(this._resolvedEntities).length === 0 ||
        this._resolvedEntities.status !== this._config.entity ||
        !this._resolvedEntities.total_brews ||
        !this._resolvedEntities.water_level ||
        !this._resolvedEntities.lifetime_water ||
        !this._resolvedEntities.brew_water ||
        !this._resolvedEntities.brew_mass ||
        !this._resolvedEntities.brew_temp ||
        !this._resolvedEntities.brew_stage;
      if (needsResolve) {
        this._resolveEntities();
      }
    }

    this._updateContent();
  }

  _setupClickListener() {
    if (this._hasClickListener) return;
    this._hasClickListener = true;
    this.shadowRoot.addEventListener("click", (e) => {
      const path = e.composedPath ? e.composedPath() : [e.target];
      for (const el of path) {
        if (!el || !el.getAttribute) continue;

        if (el.id === "purge-action") {
          e.stopPropagation();
          this._handlePurge();
          return;
        }

        if (el.id === "refill-action") {
          e.stopPropagation();
          this._handleRefill();
          return;
        }

        if (el.id === "btn-cancel-brew") {
          e.stopPropagation();
          this._executeCancelBrew();
          return;
        }

        if (el.id === "btn-toggle-drawer") {
          e.stopPropagation();
          this._brewDrawerOpen = !this._brewDrawerOpen;
          this._brewSectionDirty = true;
          this._updateContent();
          return;
        }

        if (el.id === "btn-confirm-brew-now") {
          e.stopPropagation();
          if (this._confirmBrewProfile) {
            this._executeBrew(this._confirmBrewProfile);
            this._confirmBrewProfile = null;
            this._brewSectionDirty = true;
            this._updateContent();
          }
          return;
        }

        if (el.id === "btn-confirm-load-studio") {
          e.stopPropagation();
          if (this._confirmBrewProfile) {
            this._loadProfileIntoStudio(this._confirmBrewProfile);
            this._brewSectionDirty = true;
          }
          return;
        }

        if (el.id === "btn-confirm-dismiss") {
          e.stopPropagation();
          this._confirmBrewProfile = null;
          this._brewSectionDirty = true;
          this._updateContent();
          return;
        }

        if (el.id === "btn-submit-search") {
          e.stopPropagation();
          this._brewSectionDirty = true;
          this._performSearch(this._searchQuery);
          return;
        }

        if (el.id === "btn-studio-save") {
          e.stopPropagation();
          this._saveCustomProfile(this._draftCurve);
          return;
        }

        if (el.id === "btn-studio-brew") {
          e.stopPropagation();
          this._executeBrew(this._draftCurve);
          return;
        }

        const tab = el.getAttribute("data-tab");
        if (tab) {
          e.stopPropagation();
          this._activeBrewTab = tab;
          this._brewSectionDirty = true;
          this._updateContent();
          return;
        }

        const subtab = el.getAttribute("data-subtab");
        if (subtab) {
          e.stopPropagation();
          this._savedSubTab = subtab;
          this._brewSectionDirty = true;
          this._updateContent();
          return;
        }

        const preset = el.getAttribute("data-preset");
        if (preset) {
          e.stopPropagation();
          this._applyPreset(preset);
          this._brewSectionDirty = true;
          return;
        }

        const param = el.getAttribute("data-param");
        const step = el.getAttribute("data-step");
        if (param && step) {
          e.stopPropagation();
          this._handleParamStep(param, parseFloat(step));
          this._brewSectionDirty = true;
          return;
        }

        const toggle = el.getAttribute("data-toggle");
        if (toggle) {
          e.stopPropagation();
          this._handleToggle(toggle);
          this._brewSectionDirty = true;
          return;
        }

        const chipIndex = el.getAttribute("data-quick-chip-index");
        if (chipIndex !== null) {
          e.stopPropagation();
          this._handleQuickChipClick(parseInt(chipIndex, 10));
          this._brewSectionDirty = true;
          return;
        }

        const action = el.getAttribute("data-action");
        if (action) {
          e.stopPropagation();
          const profileJson = el.getAttribute("data-profile");
          let profile = null;
          if (profileJson) {
            try {
              profile = JSON.parse(decodeURIComponent(profileJson));
            } catch (_) {}
          }
          this._brewSectionDirty = true;
          if (action === "brew-profile" && profile) {
            this._executeBrew(profile);
          } else if (action === "load-studio" && profile) {
            this._loadProfileIntoStudio(profile);
          } else if (action === "toggle-fav" && profile) {
            this._toggleFavoriteProfile(profile);
          }
          return;
        }

        const entityId = el.getAttribute("data-entity-id");
        if (entityId) {
          e.stopPropagation();
          this._openMoreInfo(entityId, el);
          return;
        }
      }
    });

    this.shadowRoot.addEventListener("input", (e) => {
      const slider = e.target.closest(".studio-range-slider");
      if (slider) {
        const param = slider.getAttribute("data-slider");
        this._handleSliderChange(param, slider.value);
      }
    });
  }

  _resolveEntities() {
    if (!this._hass || !this._hass.states || !this._config || !this._config.entity) return;
    const states = this._hass.states;
    const mainEntity = this._config.entity;
    const explicit = this._config.entities || {};

    let slug = (mainEntity || "").replace(/^sensor\./, "").replace(/_status$/, "");

    const findEntity = (typeKey, pattern, preferredDomain = null) => {
      if (explicit[typeKey] && states[explicit[typeKey]]) {
        return explicit[typeKey];
      }
      if (!states) return null;
      const candidates = Object.keys(states).filter((id) => {
        const idLower = id.toLowerCase();
        return (
          idLower.includes(pattern.toLowerCase()) &&
          (idLower.includes(slug.toLowerCase()) || idLower.includes("morning"))
        );
      });
      if (candidates.length === 0) return null;
      if (preferredDomain) {
        const pref = candidates.find((id) => id.startsWith(`${preferredDomain}.`));
        if (pref) return pref;
      }
      return candidates[0];
    };

    this._resolvedEntities = {
      status: mainEntity,
      water_level: findEntity("water_level", "water_tank_level", "sensor"),
      water_pct: findEntity("water_pct", "water_tank_percentage", "sensor"),
      brew_water: findEntity("brew_water", "brew_water_dispensed", "sensor"),
      brew_mass: findEntity("brew_mass", "brew_mass_dispensed", "sensor"),
      brew_temp: findEntity("brew_temp", "brew_temperature", "sensor"),
      brew_stage: findEntity("brew_stage", "brew_stage", "sensor"),
      brew_bloom: findEntity("brew_bloom", "brew_bloom_duration", "sensor"),
      total_brews: findEntity("total_brews", "total_brews", "sensor") || findEntity("total_brews", "brew_count", "sensor"),
      limescale: findEntity("limescale", "limescale", "sensor"),
      standby: findEntity("standby", "standby_timeout", "sensor"),
      child_lock: findEntity("child_lock", "child_lock", "binary_sensor"),
      firmware: findEntity("firmware", "firmware", "sensor"),
      slave_firmware: findEntity("slave_firmware", "motor_controller_firmware", "sensor") || findEntity("slave_firmware", "slave_firmware", "sensor"),
      lifetime_water: findEntity("lifetime_water", "lifetime_water_used", "sensor"),
      fault_code: findEntity("fault_code", "fault_code", "sensor"),
      connectivity: findEntity("connectivity", "cloud_connection", "binary_sensor") || findEntity("connectivity", "connectivity"),
      refill_button: findEntity("refill_button", "refill_water_tank", "button"),
    };
  }

  _getState(key) {
    if (!this._hass || !this._hass.states || !this._resolvedEntities || !this._resolvedEntities[key]) return null;
    return this._hass.states[this._resolvedEntities[key]] || null;
  }

  _getValue(key, fallback = null) {
    const s = this._getState(key);
    return s && s.state !== "unavailable" && s.state !== "unknown" ? s.state : fallback;
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
        ha-card {
          padding: 18px;
          background: var(--ha-card-background, var(--card-background-color, #1a1a1a));
          border-radius: var(--ha-card-border-radius, 16px);
          box-shadow: var(--ha-card-box-shadow, 0 4px 20px rgba(0,0,0,0.15));
          color: var(--primary-text-color, #ffffff);
          font-family: var(--paper-font-body1_-_font-family, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif);
          position: relative;
          overflow: hidden;
        }
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 16px;
        }
        .brand {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .brand-icon {
          width: 36px;
          height: 36px;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.08);
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .brand-icon ha-icon {
          --mdc-icon-size: 22px;
          color: var(--primary-color, #e67e22);
        }
        .title-block .name {
          font-size: 1.15rem;
          font-weight: 600;
          line-height: 1.2;
        }
        .title-block .sub {
          font-size: 0.75rem;
          color: var(--secondary-text-color, #888);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .header-badges {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .badge {
          font-size: 0.72rem;
          font-weight: 700;
          text-transform: uppercase;
          padding: 4px 10px;
          border-radius: 20px;
          letter-spacing: 0.5px;
          display: inline-flex;
          align-items: center;
          gap: 4px;
        }
        .badge.online {
          background: rgba(46, 204, 113, 0.15);
          color: #2ecc71;
        }
        .badge.offline {
          background: rgba(231, 76, 60, 0.15);
          color: #e74c3c;
        }
        .badge.status {
          border: 1px solid rgba(255, 255, 255, 0.12);
        }

        /* Extraction / Brewing Hero Display */
        .brew-hero {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 12px;
          padding: 16px;
          margin-bottom: 16px;
          transition: all 0.3s ease;
        }
        .brew-hero.brewing {
          background: linear-gradient(135deg, rgba(230, 126, 34, 0.08), rgba(243, 156, 18, 0.04));
          border-color: rgba(230, 126, 34, 0.3);
          box-shadow: 0 0 25px rgba(230, 126, 34, 0.15);
        }
        .brew-hero.done {
          background: linear-gradient(135deg, rgba(46, 204, 113, 0.08), rgba(39, 174, 96, 0.04));
          border-color: rgba(46, 204, 113, 0.25);
        }

        /* Stepper */
        .stepper {
          display: flex;
          align-items: center;
          justify-content: space-between;
          position: relative;
          margin-bottom: 16px;
        }
        .stepper-line {
          position: absolute;
          top: 14px;
          left: 16px;
          right: 16px;
          height: 2px;
          background: rgba(255, 255, 255, 0.1);
          z-index: 1;
        }
        .step {
          position: relative;
          z-index: 2;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 6px;
        }
        .step-circle {
          width: 28px;
          height: 28px;
          border-radius: 50%;
          background: var(--card-background-color, #222);
          border: 2px solid rgba(255, 255, 255, 0.2);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 0.7rem;
          color: #888;
          transition: all 0.3s;
        }
        .step.active .step-circle {
          border-color: var(--primary-color, #e67e22);
          background: var(--primary-color, #e67e22);
          color: #fff;
          box-shadow: 0 0 10px var(--primary-color, #e67e22);
        }
        .step.passed .step-circle {
          border-color: #2ecc71;
          background: #2ecc71;
          color: #fff;
        }
        .step.skipped .step-circle {
          border-style: dashed;
          border-color: rgba(255, 255, 255, 0.25);
          background: transparent;
          color: var(--secondary-text-color, #777);
        }
        .step.skipped .step-label {
          opacity: 0.55;
        }
        .step-label {
          font-size: 0.7rem;
          text-transform: uppercase;
          color: var(--secondary-text-color, #888);
          font-weight: 500;
        }
        .step.active .step-label {
          color: var(--primary-color, #e67e22);
          font-weight: 700;
        }

        /* Telemetry Grid */
        .telemetry-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
        }
        .metric-card {
          background: rgba(0, 0, 0, 0.2);
          border-radius: 10px;
          padding: 12px;
          display: flex;
          flex-direction: column;
        }
        .metric-header {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.72rem;
          color: var(--secondary-text-color, #888);
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-bottom: 4px;
        }
        .metric-header ha-icon {
          --mdc-icon-size: 14px;
        }
        .metric-value {
          font-size: 1.55rem;
          font-weight: 700;
          font-variant-numeric: tabular-nums;
          line-height: 1.1;
        }
        .metric-unit {
          font-size: 0.85rem;
          font-weight: 400;
          color: var(--secondary-text-color, #aaa);
          margin-left: 2px;
        }

        /* Extraction Curve Profile */
        .extraction-container {
          background: rgba(0, 0, 0, 0.28);
          border: 1px solid rgba(255, 255, 255, 0.07);
          border-radius: 10px;
          margin-top: 12px;
          padding: 12px 14px 10px;
          position: relative;
          overflow: hidden;
        }
        .extraction-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }
        .extraction-title {
          font-size: 0.72rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--secondary-text-color, #bbb);
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .extraction-title ha-icon {
          --mdc-icon-size: 15px;
          color: var(--primary-color, #e67e22);
        }
        .extraction-badge {
          font-size: 0.65rem;
          font-weight: 700;
          text-transform: uppercase;
          padding: 2px 7px;
          border-radius: 10px;
          letter-spacing: 0.5px;
          display: inline-flex;
          align-items: center;
          gap: 4px;
        }
        .extraction-badge.live {
          background: rgba(230, 126, 34, 0.2);
          color: #e67e22;
          border: 1px solid rgba(230, 126, 34, 0.4);
        }
        .extraction-badge.live::before {
          content: "";
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #e67e22;
          box-shadow: 0 0 6px #e67e22;
          animation: pulse-dot 1.2s infinite ease-in-out;
        }
        .extraction-badge.completed {
          background: rgba(46, 204, 113, 0.15);
          color: #2ecc71;
          border: 1px solid rgba(46, 204, 113, 0.3);
        }
        .extraction-stats {
          display: flex;
          align-items: center;
          gap: 6px;
          flex-wrap: wrap;
        }
        .stat-chip {
          font-size: 0.68rem;
          color: var(--primary-text-color, #fff);
          background: rgba(255, 255, 255, 0.05);
          padding: 2px 6px;
          border-radius: 4px;
          font-variant-numeric: tabular-nums;
          display: inline-flex;
          align-items: center;
          gap: 3px;
        }
        .stat-chip ha-icon {
          --mdc-icon-size: 11px;
          color: var(--secondary-text-color, #888);
        }
        .chart-svg-container {
          position: relative;
          width: 100%;
        }
        .chart-svg {
          width: 100%;
          height: auto;
          display: block;
          user-select: none;
          touch-action: pan-y;
        }
        .chart-legend {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 14px;
          margin-top: 6px;
          font-size: 0.68rem;
          color: var(--secondary-text-color, #888);
        }
        .legend-item {
          display: inline-flex;
          align-items: center;
          gap: 5px;
        }
        .legend-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }
        .legend-dot.yield {
          background: #e67e22;
          box-shadow: 0 0 4px rgba(230, 126, 34, 0.5);
        }
        .legend-dot.flow {
          background: #3498db;
          box-shadow: 0 0 4px rgba(52, 152, 219, 0.5);
        }
        .legend-dot.temp {
          background: #e74c3c;
          box-shadow: 0 0 4px rgba(231, 76, 60, 0.5);
        }
        .curve-crosshair {
          stroke: rgba(255, 255, 255, 0.35);
          stroke-width: 1;
          stroke-dasharray: 2 2;
          pointer-events: none;
        }
        .curve-tooltip {
          position: absolute;
          top: 6px;
          pointer-events: none;
          background: rgba(18, 18, 18, 0.92);
          border: 1px solid rgba(255, 255, 255, 0.18);
          backdrop-filter: blur(8px);
          border-radius: 6px;
          padding: 4px 8px;
          font-size: 0.68rem;
          color: #fff;
          font-variant-numeric: tabular-nums;
          white-space: nowrap;
          z-index: 10;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
          transform: translateX(-50%);
          display: none;
        }
        @keyframes pulse-dot {
          0% { transform: scale(0.9); opacity: 0.7; }
          50% { transform: scale(1.3); opacity: 1; }
          100% { transform: scale(0.9); opacity: 0.7; }
        }
        .pulse-head {
          animation: pulse-dot 1.4s infinite ease-in-out;
          transform-origin: center;
        }

        /* Water Reservoir Gauge */
        .reservoir-section {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          padding: 14px 16px;
          margin-bottom: 14px;
        }
        .reservoir-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }
        .reservoir-title {
          font-size: 0.75rem;
          text-transform: uppercase;
          color: var(--secondary-text-color, #888);
          letter-spacing: 0.5px;
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .reservoir-title ha-icon {
          --mdc-icon-size: 15px;
          color: #3498db;
        }
        .reservoir-status {
          font-size: 0.82rem;
          font-weight: 600;
        }
        .progress-bar-container {
          height: 10px;
          background: rgba(255, 255, 255, 0.08);
          border-radius: 6px;
          overflow: hidden;
          position: relative;
          margin-bottom: 10px;
        }
        .progress-bar {
          height: 100%;
          border-radius: 6px;
          background: linear-gradient(90deg, #2980b9, #3498db);
          transition: width 0.5s ease-in-out, background 0.3s;
        }
        .progress-bar.low {
          background: linear-gradient(90deg, #c0392b, #e74c3c);
        }
        .reservoir-footer {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .reservoir-detail {
          font-size: 0.78rem;
          color: var(--secondary-text-color, #888);
        }
        .reservoir-actions {
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .action-btn {
          border-radius: 6px;
          padding: 5px 10px;
          font-size: 0.72rem;
          font-weight: 600;
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          gap: 4px;
          transition: all 0.2s;
        }
        .action-btn ha-icon {
          --mdc-icon-size: 13px;
        }
        .purge-btn {
          background: rgba(230, 126, 34, 0.15);
          border: 1px solid rgba(230, 126, 34, 0.3);
          color: #e67e22;
        }
        .purge-btn:hover {
          background: rgba(230, 126, 34, 0.25);
          border-color: #e67e22;
        }
        .refill-btn {
          background: rgba(52, 152, 219, 0.15);
          border: 1px solid rgba(52, 152, 219, 0.3);
          color: #3498db;
        }
        .refill-btn:hover {
          background: rgba(52, 152, 219, 0.25);
          border-color: #3498db;
        }

        /* Diagnostics Bar */
        .diag-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(85px, 1fr));
          gap: 8px;
          padding-top: 4px;
        }
        .diag-item {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.04);
          border-radius: 8px;
          padding: 8px 10px;
          display: flex;
          flex-direction: column;
        }
        .diag-label {
          font-size: 0.68rem;
          color: var(--secondary-text-color, #777);
          text-transform: uppercase;
        }
        .diag-val {
          font-size: 0.95rem;
          font-weight: 600;
          margin-top: 2px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        [data-entity-id],
        [data-entity-id] * {
          cursor: pointer !important;
        }
        .clickable,
        .clickable * {
          cursor: pointer !important;
        }
        .diag-item.clickable:hover {
          background: rgba(255, 255, 255, 0.12) !important;
          border-color: rgba(255, 255, 255, 0.25) !important;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25) !important;
          transform: translateY(-1px);
        }
        .metric-card.clickable:hover {
          background: rgba(0, 0, 0, 0.4) !important;
          box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35) !important;
          transform: translateY(-1px);
        }
        .progress-bar-container.clickable {
          cursor: pointer !important;
        }
        .progress-bar-container.clickable:hover {
          opacity: 0.85;
          filter: brightness(1.15);
        }

        /* Brew Controls & Quick Bar */
        .brew-controls-section {
          margin-bottom: 14px;
        }
        .cancel-banner {
          background: linear-gradient(135deg, rgba(231, 76, 60, 0.2), rgba(192, 57, 43, 0.3));
          border: 1px solid rgba(231, 76, 60, 0.5);
          border-radius: 10px;
          padding: 10px 14px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          animation: pulse-border 1.5s infinite ease-in-out;
        }
        @keyframes pulse-border {
          0% { box-shadow: 0 0 5px rgba(231, 76, 60, 0.2); }
          50% { box-shadow: 0 0 15px rgba(231, 76, 60, 0.4); }
          100% { box-shadow: 0 0 5px rgba(231, 76, 60, 0.2); }
        }
        .cancel-banner-info {
          display: flex;
          align-items: center;
          gap: 8px;
          font-weight: 600;
          font-size: 0.88rem;
          color: #ff7675;
        }
        .cancel-banner-btn {
          background: #e74c3c;
          color: #fff;
          border: none;
          border-radius: 6px;
          padding: 6px 14px;
          font-size: 0.8rem;
          font-weight: 700;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          cursor: pointer !important;
          transition: background 0.2s;
        }
        .cancel-banner-btn * {
          cursor: pointer !important;
        }
        .cancel-banner-btn:hover {
          background: #c0392b;
        }
        .quick-brew-row {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 6px;
        }
        .quick-chips-scroll {
          display: flex;
          align-items: center;
          gap: 6px;
          overflow-x: auto;
          scrollbar-width: none;
          -ms-overflow-style: none;
          flex: 1;
          padding: 2px 0;
        }
        .quick-chips-scroll::-webkit-scrollbar {
          display: none;
        }
        .quick-chip {
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 20px;
          padding: 5px 12px;
          font-size: 0.75rem;
          font-weight: 600;
          white-space: nowrap;
          display: inline-flex;
          align-items: center;
          gap: 5px;
          color: var(--primary-text-color, #eee);
          cursor: pointer !important;
          transition: all 0.2s;
        }
        .quick-chip * {
          cursor: pointer !important;
        }
        .quick-chip:hover {
          background: rgba(230, 126, 34, 0.15);
          border-color: rgba(230, 126, 34, 0.4);
          color: #fff;
          transform: translateY(-1px);
        }
        .quick-chip.active {
          background: rgba(230, 126, 34, 0.25);
          border-color: var(--primary-color, #e67e22);
          color: #fff;
        }
        .quick-chip ha-icon {
          --mdc-icon-size: 13px;
          color: var(--primary-color, #e67e22);
        }
        .studio-toggle-btn {
          background: rgba(230, 126, 34, 0.15);
          border: 1px solid rgba(230, 126, 34, 0.35);
          border-radius: 8px;
          padding: 6px 12px;
          font-size: 0.78rem;
          font-weight: 700;
          color: var(--primary-color, #e67e22);
          display: inline-flex;
          align-items: center;
          gap: 5px;
          cursor: pointer !important;
          white-space: nowrap;
          transition: all 0.2s;
        }
        .studio-toggle-btn * {
          cursor: pointer !important;
        }
        .studio-toggle-btn:hover {
          background: rgba(230, 126, 34, 0.25);
          border-color: var(--primary-color, #e67e22);
        }
        .studio-toggle-btn.active {
          background: var(--primary-color, #e67e22);
          color: #fff;
        }
        .studio-toggle-btn.active ha-icon {
          color: #fff;
        }

        /* Quick Confirmation Bar */
        .confirm-bar {
          background: rgba(230, 126, 34, 0.12);
          border: 1px solid rgba(230, 126, 34, 0.3);
          border-radius: 8px;
          padding: 8px 12px;
          margin-top: 6px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 0.8rem;
          animation: fade-in 0.2s ease-out;
        }
        .confirm-info {
          display: flex;
          align-items: center;
          gap: 6px;
          color: #fff;
        }
        .confirm-info strong {
          color: var(--primary-color, #e67e22);
        }
        .confirm-actions {
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .btn-confirm-brew {
          background: var(--primary-color, #e67e22);
          color: #fff;
          border: none;
          border-radius: 6px;
          padding: 5px 12px;
          font-size: 0.75rem;
          font-weight: 700;
          cursor: pointer !important;
          display: inline-flex;
          align-items: center;
          gap: 4px;
        }
        .btn-confirm-brew * {
          cursor: pointer !important;
        }
        .btn-confirm-brew:hover {
          filter: brightness(1.15);
        }
        .btn-confirm-edit {
          background: rgba(255, 255, 255, 0.08);
          color: #eee;
          border: 1px solid rgba(255, 255, 255, 0.15);
          border-radius: 6px;
          padding: 5px 10px;
          font-size: 0.72rem;
          font-weight: 600;
          cursor: pointer !important;
        }
        .btn-confirm-edit * {
          cursor: pointer !important;
        }
        .btn-confirm-dismiss {
          background: transparent;
          color: #888;
          border: none;
          padding: 4px 6px;
          font-size: 0.9rem;
          cursor: pointer !important;
        }
        .btn-confirm-dismiss * {
          cursor: pointer !important;
        }

        /* Expandable Brew Drawer */
        .brew-drawer {
          background: rgba(0, 0, 0, 0.35);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          margin-top: 8px;
          padding: 12px;
          animation: slide-down 0.25s ease-out;
        }
        @keyframes slide-down {
          from { opacity: 0; transform: translateY(-8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes fade-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }

        /* Drawer Main Tabs */
        .drawer-tabs {
          display: flex;
          align-items: center;
          gap: 6px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          padding-bottom: 8px;
          margin-bottom: 12px;
        }
        .tab-btn {
          background: transparent;
          border: none;
          border-bottom: 2px solid transparent;
          color: var(--secondary-text-color, #888);
          padding: 4px 10px;
          font-size: 0.78rem;
          font-weight: 700;
          cursor: pointer !important;
          display: inline-flex;
          align-items: center;
          gap: 5px;
          transition: all 0.2s;
        }
        .tab-btn * {
          cursor: pointer !important;
        }
        .tab-btn:hover {
          color: #eee;
        }
        .tab-btn.active {
          color: var(--primary-color, #e67e22);
          border-bottom-color: var(--primary-color, #e67e22);
        }

        /* Saved Subtabs */
        .saved-subtabs {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-bottom: 10px;
        }
        .subtab-btn {
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 14px;
          padding: 3px 10px;
          font-size: 0.72rem;
          color: var(--secondary-text-color, #999);
          cursor: pointer !important;
          transition: all 0.2s;
        }
        .subtab-btn * {
          cursor: pointer !important;
        }
        .subtab-btn:hover {
          color: #fff;
          background: rgba(255, 255, 255, 0.08);
        }
        .subtab-btn.active {
          background: rgba(230, 126, 34, 0.2);
          border-color: rgba(230, 126, 34, 0.4);
          color: #e67e22;
          font-weight: 600;
        }

        /* Profile Cards List */
        .profile-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
          max-height: 280px;
          overflow-y: auto;
          scrollbar-width: thin;
        }
        .profile-card {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 8px;
          padding: 8px 12px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          transition: all 0.2s;
        }
        .profile-card:hover {
          background: rgba(255, 255, 255, 0.06);
          border-color: rgba(255, 255, 255, 0.12);
        }
        .profile-info {
          display: flex;
          flex-direction: column;
          gap: 2px;
          flex: 1;
          min-width: 0;
        }
        .profile-header-line {
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .profile-name {
          font-size: 0.85rem;
          font-weight: 600;
          color: #fff;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .profile-roaster-badge {
          font-size: 0.65rem;
          padding: 1px 5px;
          border-radius: 4px;
          background: rgba(52, 152, 219, 0.15);
          color: #3498db;
          border: 1px solid rgba(52, 152, 219, 0.3);
          font-weight: 600;
        }
        .profile-specs {
          font-size: 0.72rem;
          color: var(--secondary-text-color, #888);
          display: flex;
          align-items: center;
          gap: 6px;
          font-variant-numeric: tabular-nums;
        }
        .profile-specs .highlight {
          color: var(--primary-color, #e67e22);
          font-weight: 600;
        }
        .profile-sparkline {
          width: 58px;
          height: 24px;
          flex-shrink: 0;
        }
        .profile-actions {
          display: flex;
          align-items: center;
          gap: 5px;
          flex-shrink: 0;
        }
        .icon-action-btn {
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 6px;
          padding: 5px;
          color: #aaa;
          cursor: pointer !important;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s;
        }
        .icon-action-btn * {
          cursor: pointer !important;
        }
        .icon-action-btn:hover {
          color: #fff;
          background: rgba(255, 255, 255, 0.12);
        }
        .icon-action-btn.fav.active {
          color: #f1c40f;
          border-color: rgba(241, 196, 15, 0.3);
        }
        .brew-pill-btn {
          background: var(--primary-color, #e67e22);
          color: #fff;
          border: none;
          border-radius: 6px;
          padding: 5px 10px;
          font-size: 0.74rem;
          font-weight: 700;
          cursor: pointer !important;
          display: inline-flex;
          align-items: center;
          gap: 4px;
          transition: all 0.2s;
        }
        .brew-pill-btn * {
          cursor: pointer !important;
        }
        .brew-pill-btn:hover {
          filter: brightness(1.15);
        }

        /* Search Section */
        .search-row {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-bottom: 10px;
        }
        .search-input {
          flex: 1;
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 6px;
          padding: 8px 12px;
          color: #fff;
          font-size: 0.82rem;
          outline: none;
        }
        .search-input:focus {
          border-color: var(--primary-color, #e67e22);
        }
        .search-submit-btn {
          background: rgba(230, 126, 34, 0.2);
          border: 1px solid rgba(230, 126, 34, 0.4);
          color: var(--primary-color, #e67e22);
          border-radius: 6px;
          padding: 8px 12px;
          font-size: 0.8rem;
          font-weight: 700;
          cursor: pointer !important;
          display: inline-flex;
          align-items: center;
          gap: 4px;
        }
        .search-submit-btn * {
          cursor: pointer !important;
        }
        .search-submit-btn:hover {
          background: var(--primary-color, #e67e22);
          color: #fff;
        }

        /* Interactive Curve Studio */
        .studio-container {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .presets-row {
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .preset-btn {
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 6px;
          padding: 4px 10px;
          font-size: 0.72rem;
          font-weight: 600;
          color: #aaa;
          cursor: pointer !important;
          transition: all 0.2s;
        }
        .preset-btn * {
          cursor: pointer !important;
        }
        .preset-btn:hover {
          color: #fff;
          background: rgba(255, 255, 255, 0.08);
        }
        .preset-btn.active {
          background: rgba(230, 126, 34, 0.25);
          border-color: var(--primary-color, #e67e22);
          color: #fff;
        }
        .studio-svg-box {
          position: relative;
          background: rgba(0, 0, 0, 0.4);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 10px;
          padding: 8px 6px;
        }
        .studio-svg {
          width: 100%;
          height: auto;
          display: block;
          touch-action: none;
          user-select: none;
        }
        .studio-handle {
          cursor: pointer !important;
          transition: r 0.15s ease, filter 0.15s ease;
        }
        .studio-handle:hover, .studio-handle.active {
          r: 5;
          filter: drop-shadow(0 0 5px var(--primary-color, #e67e22));
        }
        .studio-handle-hit {
          cursor: pointer !important;
        }
        .studio-floating-tooltip {
          position: absolute;
          top: 10px;
          right: 12px;
          background: rgba(18, 18, 18, 0.95);
          border: 1px solid var(--primary-color, #e67e22);
          border-radius: 6px;
          padding: 3px 8px;
          font-size: 0.72rem;
          color: #fff;
          font-weight: 600;
          pointer-events: none;
          display: none;
        }

        /* Studio Range Sliders Grid */
        .studio-sliders-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px;
        }
        .slider-control-group {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 8px;
          padding: 8px 10px;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .slider-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .slider-title {
          display: flex;
          align-items: center;
          gap: 5px;
          font-size: 0.72rem;
          color: var(--secondary-text-color, #aaa);
          font-weight: 600;
        }
        .slider-title ha-icon {
          --mdc-icon-size: 15px;
          color: var(--primary-color, #e67e22);
        }
        .slider-val-badge {
          font-size: 0.82rem;
          font-weight: 700;
          color: #fff;
          font-variant-numeric: tabular-nums;
        }
        .studio-range-slider {
          -webkit-appearance: none;
          appearance: none;
          width: 100%;
          height: 6px;
          border-radius: 3px;
          background: rgba(255, 255, 255, 0.12);
          outline: none;
          cursor: pointer !important;
          transition: background 0.2s;
        }
        .studio-range-slider::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: var(--primary-color, #e67e22);
          border: 2px solid #fff;
          cursor: pointer !important;
          box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
          transition: transform 0.15s ease;
        }
        .studio-range-slider::-webkit-slider-thumb:hover,
        .studio-range-slider::-webkit-slider-thumb:active {
          transform: scale(1.18);
        }
        .studio-range-slider::-moz-range-thumb {
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: var(--primary-color, #e67e22);
          border: 2px solid #fff;
          cursor: pointer !important;
          box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
        }

        /* Stage Color Pills Below SVG */
        .studio-stages-pills {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 6px;
          margin-top: 6px;
        }
        .stage-pill {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          font-size: 0.68rem;
          padding: 2px 8px;
          border-radius: 12px;
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: #ccc;
        }
        .stage-pill strong {
          color: #fff;
        }
        .stage-pill-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          display: inline-block;
        }
        .studio-params-row {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px;
        }
        .stepper-box {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 8px;
          padding: 6px 10px;
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .stepper-label {
          display: flex;
          flex-direction: column;
        }
        .stepper-label-title {
          font-size: 0.68rem;
          color: var(--secondary-text-color, #888);
          text-transform: uppercase;
        }
        .stepper-label-val {
          font-size: 1.05rem;
          font-weight: 700;
          color: #fff;
        }
        .stepper-controls {
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .step-ctrl-btn {
          width: 26px;
          height: 26px;
          border-radius: 6px;
          background: rgba(255, 255, 255, 0.08);
          border: 1px solid rgba(255, 255, 255, 0.12);
          color: #fff;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 0.9rem;
          font-weight: 700;
          cursor: pointer !important;
        }
        .step-ctrl-btn * {
          cursor: pointer !important;
        }
        .step-ctrl-btn:hover {
          background: rgba(230, 126, 34, 0.3);
          border-color: var(--primary-color, #e67e22);
        }
        .advanced-pills-row {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .adv-pill {
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 16px;
          padding: 4px 10px;
          font-size: 0.72rem;
          color: #aaa;
          cursor: pointer !important;
          display: inline-flex;
          align-items: center;
          gap: 4px;
          transition: all 0.2s;
        }
        .adv-pill * {
          cursor: pointer !important;
        }
        .adv-pill:hover {
          color: #fff;
          background: rgba(255, 255, 255, 0.08);
        }
        .adv-pill.active {
          background: rgba(52, 152, 219, 0.2);
          border-color: rgba(52, 152, 219, 0.4);
          color: #3498db;
          font-weight: 600;
        }
        .studio-actions-footer {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-top: 6px;
        }
        .btn-save-curve {
          background: rgba(255, 255, 255, 0.06);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 8px;
          color: #eee;
          padding: 8px 14px;
          font-size: 0.8rem;
          font-weight: 600;
          cursor: pointer !important;
          display: inline-flex;
          align-items: center;
          gap: 5px;
          transition: all 0.2s;
        }
        .btn-save-curve * {
          cursor: pointer !important;
        }
        .btn-save-curve:hover {
          background: rgba(255, 255, 255, 0.12);
          color: #fff;
        }
        .btn-brew-primary {
          background: linear-gradient(135deg, #e67e22, #d35400);
          border: none;
          border-radius: 8px;
          color: #fff;
          padding: 8px 18px;
          font-size: 0.85rem;
          font-weight: 700;
          cursor: pointer !important;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          box-shadow: 0 2px 10px rgba(230, 126, 34, 0.35);
          transition: all 0.2s;
        }
        .btn-brew-primary * {
          cursor: pointer !important;
        }
        .btn-brew-primary:hover {
          filter: brightness(1.12);
          box-shadow: 0 4px 15px rgba(230, 126, 34, 0.5);
          transform: translateY(-1px);
        }
      </style>
      <ha-card id="card-root">
      </ha-card>
    `;

    this._setupClickListener();
  }

  _handleRefill() {
    if (!this._hass) return;
    const btnEntity = this._resolvedEntities.refill_button;
    if (btnEntity && this._hass.states[btnEntity]) {
      this._hass.callService("button", "press", { entity_id: btnEntity });
    } else {
      this._hass.callService("morning", "refill_water", {});
    }
  }

  _handlePurge() {
    if (!this._hass) return;
    this._hass.callService("morning", "record_purge", {});
  }

  _escapeHtml(str) {
    if (typeof str !== "string") return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _executeBrew(recipe) {
    if (!this._hass) return;
    const entityId = this._config.entity;
    const data = {
      entity_id: entityId,
      name: recipe.name || "Custom Profile",
      temperature: Number(recipe.temperature) || 94,
      mass_output: Number(recipe.mass_output) || 40,
      water_output: Number(recipe.water_output) || 0,
      bloom_duration: recipe.bloom_enabled ? Number(recipe.bloom_duration) || 10 : 0,
    };
    if (recipe.id !== undefined && recipe.id !== null) {
      data.profile_id = String(recipe.id);
    }
    if (Array.isArray(recipe.stages) && recipe.stages.length >= 3) {
      data.stage1_pressure = Number(recipe.stages[0].pressure) || 3;
      data.stage2_pressure = Number(recipe.stages[1].pressure) || 7;
      data.stage3_pressure = Number(recipe.stages[2].pressure) || 5;
      data.stage2_weight = Number(recipe.stages[1].output) || 5;
      data.stage3_weight = Number(recipe.stages[2].output) || 30;
    }
    this._hass.callService("morning", "brew_recipe", data);
  }

  _executeCancelBrew() {
    if (!this._hass) return;
    const entityId = this._config.entity;
    this._hass.callService("morning", "cancel_brew", { entity_id: entityId });
  }

  _toggleFavoriteProfile(recipe) {
    if (!this._hass || !recipe) return;
    const entityId = this._config.entity;
    const profileId = recipe.id !== undefined && recipe.id !== null ? String(recipe.id) : recipe.name;
    this._hass.callService("morning", "toggle_favorite", {
      entity_id: entityId,
      profile_id: profileId,
      recipe: recipe,
    });
  }

  _saveCustomProfile(recipe) {
    if (!this._hass || !recipe) return;
    const entityId = this._config.entity;
    const promptName = window.prompt("Enter name for this custom brew curve:", recipe.name || "Custom Profile");
    if (!promptName || !promptName.trim()) return;
    const updatedRecipe = {
      ...recipe,
      name: promptName.trim(),
      id: Date.now(),
    };
    this._draftCurve.name = promptName.trim();
    this._hass.callService("morning", "save_profile", {
      entity_id: entityId,
      ...updatedRecipe,
    });
  }

  async _performSearch(query) {
    if (!query || !query.trim()) {
      this._searchResults = [];
      this._isSearching = false;
      this._brewSectionDirty = true;
      this._updateContent();
      return;
    }
    this._searchQuery = query.trim();
    this._isSearching = true;
    this._brewSectionDirty = true;
    this._updateContent();

    try {
      if (this._hass && typeof this._hass.callWS === "function") {
        const resp = await this._hass.callWS({
          type: "call_service",
          domain: "morning",
          service: "search_recipes",
          service_data: { query: this._searchQuery },
          return_response: true,
        });
        const results = resp?.response?.recipes || [];
        this._searchResults = results;
      } else {
        const statusState = this._getState("status");
        const catalog = statusState?.attributes?.recipe_catalog || {};
        const all = [
          ...(catalog.favorites || []),
          ...(catalog.recents || []),
          ...(catalog.custom || []),
          ...(catalog.machine || []),
        ];
        const q = this._searchQuery.toLowerCase();
        this._searchResults = all.filter((r) =>
          (r.name && r.name.toLowerCase().includes(q)) ||
          (r.roaster_name && r.roaster_name.toLowerCase().includes(q))
        );
      }
    } catch (err) {
      const statusState = this._getState("status");
      const catalog = statusState?.attributes?.recipe_catalog || {};
      const all = [
        ...(catalog.favorites || []),
        ...(catalog.recents || []),
        ...(catalog.custom || []),
        ...(catalog.machine || []),
      ];
      const q = this._searchQuery.toLowerCase();
      this._searchResults = all.filter((r) =>
        (r.name && r.name.toLowerCase().includes(q)) ||
        (r.roaster_name && r.roaster_name.toLowerCase().includes(q))
      );
    } finally {
      this._isSearching = false;
      this._brewSectionDirty = true;
      this._updateContent();
    }
  }

  _loadProfileIntoStudio(profile) {
    const mass = Number(profile.mass_output) || 40;
    this._draftCurve = {
      id: profile.id || Date.now(),
      name: profile.name || "Custom Profile",
      temperature: Number(profile.temperature) || 94,
      mass_output: mass,
      water_output: Number(profile.water_output) || 0,
      bloom_enabled: !!profile.bloom_enabled || (Number(profile.bloom_duration) || 0) > 0,
      bloom_duration: Number(profile.bloom_duration) || 10,
      bypass_enabled: !!profile.bypass_enabled || (Number(profile.water_output) || 0) > 0,
      stages: Array.isArray(profile.stages) && profile.stages.length >= 3
        ? profile.stages.map((s, idx) => ({
            id: s.id !== undefined ? s.id : idx,
            output: Number(s.output) || 0,
            pressure: Math.min(7, Math.max(1, Number(s.pressure) || 4)),
          }))
        : [
            { id: 0, output: 0, pressure: 3 },
            { id: 1, output: Math.round(mass * 0.2), pressure: 7 },
            { id: 2, output: Math.round(mass * 0.8), pressure: 5 },
          ],
      is_favorite: !!profile.is_favorite,
    };
    this._activePresetKey = "custom";
    this._activeBrewTab = "studio";
    this._brewDrawerOpen = true;
    this._confirmBrewProfile = null;
    this._brewSectionDirty = true;
    this._updateContent();
  }

  _applyPreset(key) {
    this._activePresetKey = key;
    if (key === "classic") {
      this._draftCurve.name = "Classic Espresso";
      this._draftCurve.temperature = 95;
      this._draftCurve.mass_output = 40;
      this._draftCurve.water_output = 0;
      this._draftCurve.bloom_duration = 0;
      this._draftCurve.bloom_enabled = false;
      this._draftCurve.bypass_enabled = false;
      this._draftCurve.stages = [
        { id: 0, output: 0, pressure: 3 },
        { id: 1, output: 5, pressure: 7 },
        { id: 2, output: 35, pressure: 5 },
      ];
    } else if (key === "short") {
      this._draftCurve.name = "Short (Ristretto)";
      this._draftCurve.temperature = 93;
      this._draftCurve.mass_output = 25;
      this._draftCurve.water_output = 0;
      this._draftCurve.bloom_duration = 0;
      this._draftCurve.bloom_enabled = false;
      this._draftCurve.bypass_enabled = false;
      this._draftCurve.stages = [
        { id: 0, output: 0, pressure: 3 },
        { id: 1, output: 4, pressure: 7 },
        { id: 2, output: 20, pressure: 5 },
      ];
    } else if (key === "bloom") {
      this._draftCurve.name = "Bloom & Brew";
      this._draftCurve.temperature = 93;
      this._draftCurve.mass_output = 35;
      this._draftCurve.water_output = 0;
      this._draftCurve.bloom_duration = 10;
      this._draftCurve.bloom_enabled = true;
      this._draftCurve.bypass_enabled = false;
      this._draftCurve.stages = [
        { id: 0, output: 0, pressure: 2 },
        { id: 1, output: 5, pressure: 6 },
        { id: 2, output: 30, pressure: 6 },
      ];
    } else if (key === "slow") {
      this._draftCurve.name = "Slow & Steady";
      this._draftCurve.temperature = 94;
      this._draftCurve.mass_output = 40;
      this._draftCurve.water_output = 0;
      this._draftCurve.bloom_duration = 10;
      this._draftCurve.bloom_enabled = true;
      this._draftCurve.bypass_enabled = false;
      this._draftCurve.stages = [
        { id: 0, output: 0, pressure: 2 },
        { id: 1, output: 10, pressure: 5 },
        { id: 2, output: 32, pressure: 6 },
      ];
    } else if (key === "fast") {
      this._draftCurve.name = "Fast Shot";
      this._draftCurve.temperature = 95;
      this._draftCurve.mass_output = 35;
      this._draftCurve.water_output = 0;
      this._draftCurve.bloom_duration = 0;
      this._draftCurve.bloom_enabled = false;
      this._draftCurve.bypass_enabled = false;
      this._draftCurve.stages = [
        { id: 0, output: 0, pressure: 7 },
        { id: 1, output: 15, pressure: 7 },
        { id: 2, output: 28, pressure: 4 },
      ];
    } else if (key === "americano") {
      this._draftCurve.name = "Americano";
      this._draftCurve.temperature = 94;
      this._draftCurve.mass_output = 35;
      this._draftCurve.water_output = 120;
      this._draftCurve.bloom_duration = 0;
      this._draftCurve.bloom_enabled = false;
      this._draftCurve.bypass_enabled = true;
      this._draftCurve.stages = [
        { id: 0, output: 0, pressure: 3 },
        { id: 1, output: 5, pressure: 7 },
        { id: 2, output: 30, pressure: 5 },
      ];
    }
    this._brewSectionDirty = true;
    this._updateContent();
  }

  _handleParamStep(param, delta) {
    if (param === "mass") {
      const cur = this._draftCurve.mass_output || 40;
      const next = Math.max(10, Math.min(250, cur + delta));
      this._draftCurve.mass_output = next;
      if (this._draftCurve.stages && this._draftCurve.stages.length >= 3) {
        if (this._draftCurve.stages[2].output >= next) {
          this._draftCurve.stages[2].output = Math.max(4, next - 4);
        }
        if (this._draftCurve.stages[1].output >= this._draftCurve.stages[2].output) {
          this._draftCurve.stages[1].output = Math.max(2, this._draftCurve.stages[2].output - 2);
        }
      }
    } else if (param === "temp") {
      const cur = this._draftCurve.temperature || 94;
      this._draftCurve.temperature = Math.max(65, Math.min(99, cur + delta));
    } else if (param === "bloom_sec" || param === "bloom") {
      const cur = this._draftCurve.bloom_duration || 0;
      this._draftCurve.bloom_duration = Math.max(0, Math.min(30, cur + delta));
      this._draftCurve.bloom_enabled = this._draftCurve.bloom_duration > 0;
    } else if (param === "water" || param === "bypass") {
      const cur = this._draftCurve.water_output || 0;
      this._draftCurve.water_output = Math.max(0, Math.min(250, cur + delta));
      this._draftCurve.bypass_enabled = this._draftCurve.water_output > 0;
    }
    this._activePresetKey = "custom";
    this._brewSectionDirty = true;
    this._updateContent();
  }

  _handleSliderChange(param, value) {
    const val = Number(value);
    const draft = this._draftCurve;
    if (param === "mass") {
      const next = Math.max(10, Math.min(250, val));
      draft.mass_output = next;
      if (draft.stages && draft.stages.length >= 3) {
        if (draft.stages[2].output >= next) {
          draft.stages[2].output = Math.max(4, next - 4);
        }
        if (draft.stages[1].output >= draft.stages[2].output) {
          draft.stages[1].output = Math.max(2, draft.stages[2].output - 2);
        }
      }
    } else if (param === "temp") {
      draft.temperature = Math.max(65, Math.min(99, val));
    } else if (param === "bloom") {
      draft.bloom_duration = Math.max(0, Math.min(30, val));
      draft.bloom_enabled = draft.bloom_duration > 0;
    } else if (param === "bypass") {
      draft.water_output = Math.max(0, Math.min(250, val));
      draft.bypass_enabled = draft.water_output > 0;
    }
    this._activePresetKey = "custom";

    // In-place update to preserve slider pointer capture during live drag
    const brewSec = this.shadowRoot.querySelector("#sec-brew");
    if (brewSec) {
      const badge = brewSec.querySelector(`.slider-val-badge[data-badge="${param}"]`);
      if (badge) {
        if (param === "mass") badge.textContent = `${draft.mass_output} g`;
        else if (param === "temp") badge.textContent = `${draft.temperature} °C`;
        else if (param === "bloom") badge.textContent = draft.bloom_duration ? `${draft.bloom_duration} s` : "Off (0s)";
        else if (param === "bypass") badge.textContent = draft.water_output ? `${draft.water_output} mL` : "None (0mL)";
      }
      const brewBtnSpan = brewSec.querySelector("#btn-studio-brew span");
      if (brewBtnSpan) {
        brewBtnSpan.textContent = `Brew Now (${draft.mass_output || 40}g @ ${draft.temperature || 94}°C${draft.water_output ? ` + ${draft.water_output}mL water` : ""})`;
      }
      const presetBtns = brewSec.querySelectorAll(".preset-btn");
      presetBtns.forEach((btn) => btn.classList.toggle("active", btn.getAttribute("data-preset") === "custom"));

      const svgBox = brewSec.querySelector(".studio-svg-box");
      if (svgBox) {
        const tempContainer = document.createElement("div");
        tempContainer.innerHTML = this._generateStudioSvg(draft);
        const newSvgBox = tempContainer.firstElementChild;
        if (newSvgBox) {
          svgBox.replaceWith(newSvgBox);
          this._setupStudioInteraction(newSvgBox);
        }
      }
      return;
    }

    this._brewSectionDirty = true;
    this._updateContent();
  }

  _handleToggle(toggle) {
    if (toggle === "bloom") {
      this._draftCurve.bloom_enabled = !this._draftCurve.bloom_enabled;
      if (this._draftCurve.bloom_enabled && !this._draftCurve.bloom_duration) {
        this._draftCurve.bloom_duration = 10;
      }
    } else if (toggle === "bypass") {
      this._draftCurve.bypass_enabled = !this._draftCurve.bypass_enabled;
    }
    this._activePresetKey = "custom";
    this._brewSectionDirty = true;
    this._updateContent();
  }

  _handleQuickChipClick(index) {
    const catalog = this._getState("status")?.attributes?.recipe_catalog || {};
    const quickList = this._getQuickProfiles(catalog);
    const profile = quickList[index];
    if (!profile) return;
    this._confirmBrewProfile = profile;
    this._brewSectionDirty = true;
    this._updateContent();
  }

  _getQuickProfiles(catalog) {
    const quick = catalog?.quick_profiles || catalog?.quick;
    if (quick && Array.isArray(quick) && quick.length > 0) {
      return quick;
    }
    const combined = [
      ...(catalog?.favorite_profiles || catalog?.favorites || []),
      ...(catalog?.recent_profiles || catalog?.recents || []),
      ...(catalog?.machine_profiles || catalog?.machine || []),
      ...(catalog?.custom_profiles || catalog?.custom || []),
    ];
    if (combined.length > 0) {
      return combined.slice(0, 6);
    }
    return [
      {
        id: "default-espresso",
        name: "Classic Espresso",
        temperature: 94,
        mass_output: 36,
        bloom_enabled: false,
        bloom_duration: 0,
        stages: [
          { id: 0, output: 0, pressure: 3 },
          { id: 1, output: 5, pressure: 7 },
          { id: 2, output: 30, pressure: 5 },
        ],
      },
      {
        id: "default-bloom",
        name: "Bloom & Extract",
        temperature: 93,
        mass_output: 40,
        bloom_enabled: true,
        bloom_duration: 10,
        stages: [
          { id: 0, output: 0, pressure: 2 },
          { id: 1, output: 8, pressure: 6 },
          { id: 2, output: 32, pressure: 6 },
        ],
      },
      {
        id: "default-lungo",
        name: "Long Shot",
        temperature: 95,
        mass_output: 60,
        bloom_enabled: false,
        bloom_duration: 0,
        stages: [
          { id: 0, output: 0, pressure: 6 },
          { id: 1, output: 20, pressure: 7 },
          { id: 2, output: 50, pressure: 4 },
        ],
      },
    ];
  }

  _renderBrewSection(recipeCatalog, isBrewing, machineId) {
    if (isBrewing) {
      return `
        <div class="brew-controls-section">
          <div class="cancel-banner">
            <div class="cancel-banner-info">
              <ha-icon icon="mdi:coffee-maker-check"></ha-icon>
              <span>Brewing in progress...</span>
            </div>
            <button class="cancel-banner-btn" id="btn-cancel-brew">
              <ha-icon icon="mdi:stop-circle-outline"></ha-icon>
              <span>Cancel Brew</span>
            </button>
          </div>
        </div>
      `;
    }

    const quickList = this._getQuickProfiles(recipeCatalog);
    const quickChipsHtml = quickList.map((p, idx) => {
      const isSelected = this._confirmBrewProfile && this._confirmBrewProfile.name === p.name;
      return `
        <button class="quick-chip${isSelected ? " active" : ""}" data-quick-chip-index="${idx}">
          <ha-icon icon="mdi:coffee-outline"></ha-icon>
          <span>${this._escapeHtml(p.name)}</span>
          <span style="opacity: 0.6; font-size: 0.68rem;">${p.temperature}°/${p.mass_output}g</span>
        </button>
      `;
    }).join("");

    return `
      <div class="brew-controls-section">
        <div class="quick-brew-row">
          <div class="quick-chips-scroll">
            ${quickChipsHtml}
          </div>
          <button class="studio-toggle-btn${this._brewDrawerOpen ? " active" : ""}" id="btn-toggle-drawer">
            <ha-icon icon="${this._brewDrawerOpen ? "mdi:chevron-up" : "mdi:tune-vertical"}"></ha-icon>
            <span>${this._brewDrawerOpen ? "Close" : "Brew Controls"}</span>
          </button>
        </div>
        ${this._confirmBrewProfile ? this._renderConfirmBar() : ""}
        ${this._brewDrawerOpen ? this._renderDrawer(recipeCatalog) : ""}
      </div>
    `;
  }

  _renderConfirmBar() {
    if (!this._confirmBrewProfile) return "";
    const p = this._confirmBrewProfile;
    const bypassStr = p.water_output > 0 ? ` + ${p.water_output}mL water` : "";
    const bloomStr = p.bloom_duration > 0 ? ` • ${p.bloom_duration}s bloom` : "";
    return `
      <div class="confirm-bar">
        <div class="confirm-info">
          <ha-icon icon="mdi:coffee-outline" style="color: var(--primary-color, #e67e22);"></ha-icon>
          <span>Brew <strong>${this._escapeHtml(p.name)}</strong> (${p.temperature}°C, ${p.mass_output}g${bypassStr}${bloomStr})?</span>
        </div>
        <div class="confirm-actions">
          <button class="btn-confirm-brew" id="btn-confirm-brew-now">
            <ha-icon icon="mdi:play"></ha-icon>
            <span>Brew Now</span>
          </button>
          <button class="btn-confirm-edit" id="btn-confirm-load-studio">
            <span>Edit in Studio</span>
          </button>
          <button class="btn-confirm-dismiss" id="btn-confirm-dismiss">✕</button>
        </div>
      </div>
    `;
  }

  _renderDrawer(recipeCatalog) {
    return `
      <div class="brew-drawer">
        <div class="drawer-tabs">
          <button class="tab-btn${this._activeBrewTab === "saved" ? " active" : ""}" data-tab="saved">
            <ha-icon icon="mdi:star-outline"></ha-icon>
            <span>Saved</span>
          </button>
          <button class="tab-btn${this._activeBrewTab === "search" ? " active" : ""}" data-tab="search">
            <ha-icon icon="mdi:magnify"></ha-icon>
            <span>Search Cloud</span>
          </button>
          <button class="tab-btn${this._activeBrewTab === "studio" ? " active" : ""}" data-tab="studio">
            <ha-icon icon="mdi:chart-bell-curve-cumulative"></ha-icon>
            <span>Curve Studio</span>
          </button>
        </div>
        <div class="drawer-body">
          ${this._renderDrawerTabContent(recipeCatalog)}
        </div>
      </div>
    `;
  }

  _renderDrawerTabContent(recipeCatalog) {
    if (this._activeBrewTab === "saved") {
      return this._renderSavedTab(recipeCatalog);
    }
    if (this._activeBrewTab === "search") {
      return this._renderSearchTab();
    }
    if (this._activeBrewTab === "studio") {
      return this._renderStudioTab();
    }
    return "";
  }

  _renderSavedTab(catalog) {
    const subtab = this._savedSubTab || "favorites";
    const favorites = catalog?.favorite_profiles || catalog?.favorites || [];
    const recents = catalog?.recent_profiles || catalog?.recents || [];
    const custom = catalog?.custom_profiles || catalog?.custom || [];
    const machine = catalog?.machine_profiles || catalog?.machine || [];

    let profiles = [];
    if (subtab === "favorites") {
      profiles = favorites;
    } else if (subtab === "recents") {
      profiles = recents;
    } else if (subtab === "custom") {
      profiles = custom;
    } else if (subtab === "machine") {
      profiles = machine;
    }

    return `
      <div class="saved-subtabs">
        <button class="subtab-btn${subtab === "favorites" ? " active" : ""}" data-subtab="favorites">Favorites (${favorites.length})</button>
        <button class="subtab-btn${subtab === "recents" ? " active" : ""}" data-subtab="recents">Recent (${recents.length})</button>
        <button class="subtab-btn${subtab === "custom" ? " active" : ""}" data-subtab="custom">Custom (${custom.length})</button>
        <button class="subtab-btn${subtab === "machine" ? " active" : ""}" data-subtab="machine">Machine Presets (${machine.length})</button>
      </div>
      ${this._renderProfileList(profiles, subtab !== "custom")}
    `;
  }

  _renderSearchTab() {
    return `
      <div class="search-row">
        <input type="text" class="search-input" id="search-input" placeholder="Search coffee, roaster, or recipe name..." value="${this._escapeHtml(this._searchQuery)}" />
        <button class="search-submit-btn" id="btn-submit-search">
          <ha-icon icon="mdi:magnify"></ha-icon>
          <span>Search</span>
        </button>
      </div>
      ${this._isSearching ? `
        <div style="text-align: center; padding: 24px; color: var(--secondary-text-color, #888);">
          <div>Searching Morning cloud recipes...</div>
        </div>
      ` : this._searchResults.length > 0 ? `
        ${this._renderProfileList(this._searchResults, true)}
      ` : this._searchQuery ? `
        <div style="text-align: center; padding: 24px; color: var(--secondary-text-color, #888); font-size: 0.82rem;">
          No recipes found matching "${this._escapeHtml(this._searchQuery)}".
        </div>
      ` : `
        <div style="text-align: center; padding: 24px; color: var(--secondary-text-color, #777); font-size: 0.8rem;">
          Enter a coffee bean name, roaster (e.g. "Stumptown", "April"), or origin to search cloud recipes.
        </div>
      `}
    `;
  }

  _renderStudioTab() {
    const draft = this._draftCurve;
    const preset = this._activePresetKey || "custom";

    return `
      <div class="studio-container">
        <!-- Presets Row Matching Drink Morning Reference App -->
        <div class="presets-row">
          <span style="font-size: 0.72rem; color: #888; font-weight: 600; margin-right: 4px;">PRESETS:</span>
          <button class="preset-btn${preset === "classic" ? " active" : ""}" data-preset="classic">Classic (40g)</button>
          <button class="preset-btn${preset === "short" ? " active" : ""}" data-preset="short">Short (25g)</button>
          <button class="preset-btn${preset === "bloom" ? " active" : ""}" data-preset="bloom">Bloom & Brew (35g)</button>
          <button class="preset-btn${preset === "slow" ? " active" : ""}" data-preset="slow">Slow & Steady (40g)</button>
          <button class="preset-btn${preset === "fast" ? " active" : ""}" data-preset="fast">Fast Shot (35g)</button>
          <button class="preset-btn${preset === "americano" ? " active" : ""}" data-preset="americano">Americano (35g+120mL)</button>
          <button class="preset-btn${preset === "custom" ? " active" : ""}" data-preset="custom">Custom</button>
        </div>

        <!-- Interactive SVG Area with 50% smaller handles, stage colors & bloom/bypass -->
        ${this._generateStudioSvg(draft)}

        <!-- Sliders with MDI Icons for Yield, Temp, Bloom & Water Bypass -->
        <div class="studio-sliders-grid">
          <!-- Brew Yield Slider -->
          <div class="slider-control-group">
            <div class="slider-header">
              <div class="slider-title">
                <ha-icon icon="mdi:scale"></ha-icon>
                <span>Yield Output</span>
              </div>
              <div style="display: flex; align-items: center; gap: 6px;">
                <button class="step-ctrl-btn" data-param="mass" data-step="-5">-5</button>
                <button class="step-ctrl-btn" data-param="mass" data-step="-1">-</button>
                <span class="slider-val-badge" data-badge="mass">${draft.mass_output || 40} g</span>
                <button class="step-ctrl-btn" data-param="mass" data-step="1">+</button>
                <button class="step-ctrl-btn" data-param="mass" data-step="5">+5</button>
              </div>
            </div>
            <input type="range" class="studio-range-slider" min="15" max="150" step="1" value="${draft.mass_output || 40}" data-slider="mass" />
          </div>

          <!-- Brew Temp Slider -->
          <div class="slider-control-group">
            <div class="slider-header">
              <div class="slider-title">
                <ha-icon icon="mdi:thermometer"></ha-icon>
                <span>Brew Temp</span>
              </div>
              <div style="display: flex; align-items: center; gap: 6px;">
                <button class="step-ctrl-btn" data-param="temp" data-step="-1">-</button>
                <span class="slider-val-badge" data-badge="temp">${draft.temperature || 94} °C</span>
                <button class="step-ctrl-btn" data-param="temp" data-step="1">+</button>
              </div>
            </div>
            <input type="range" class="studio-range-slider" min="65" max="99" step="1" value="${draft.temperature || 94}" data-slider="temp" />
          </div>

          <!-- Bloom Time Slider -->
          <div class="slider-control-group">
            <div class="slider-header">
              <div class="slider-title">
                <ha-icon icon="mdi:timer-sand"></ha-icon>
                <span>Bloom Time</span>
              </div>
              <div style="display: flex; align-items: center; gap: 6px;">
                <button class="step-ctrl-btn" data-param="bloom_sec" data-step="-2">-2</button>
                <span class="slider-val-badge" data-badge="bloom">${draft.bloom_duration ? `${draft.bloom_duration} s` : "Off (0s)"}</span>
                <button class="step-ctrl-btn" data-param="bloom_sec" data-step="2">+2</button>
              </div>
            </div>
            <input type="range" class="studio-range-slider" min="0" max="30" step="1" value="${draft.bloom_duration || 0}" data-slider="bloom" />
          </div>

          <!-- Water Bypass Slider (Americano) -->
          <div class="slider-control-group">
            <div class="slider-header">
              <div class="slider-title">
                <ha-icon icon="mdi:water-plus"></ha-icon>
                <span>Water Bypass</span>
              </div>
              <div style="display: flex; align-items: center; gap: 6px;">
                <button class="step-ctrl-btn" data-param="water" data-step="-10">-10</button>
                <span class="slider-val-badge" data-badge="bypass" style="color: #3498db;">${draft.water_output ? `${draft.water_output} mL` : "None (0mL)"}</span>
                <button class="step-ctrl-btn" data-param="water" data-step="10">+10</button>
              </div>
            </div>
            <input type="range" class="studio-range-slider" min="0" max="250" step="5" value="${draft.water_output || 0}" data-slider="bypass" />
          </div>
        </div>

        <!-- Footer Actions -->
        <div class="studio-actions-footer">
          <button class="btn-save-curve" id="btn-studio-save">
            <ha-icon icon="mdi:content-save-outline"></ha-icon>
            <span>Save Profile</span>
          </button>
          <button class="btn-brew-primary" id="btn-studio-brew">
            <ha-icon icon="mdi:coffee-maker"></ha-icon>
            <span>Brew Now (${draft.mass_output || 40}g @ ${draft.temperature || 94}°C${draft.water_output ? ` + ${draft.water_output}mL water` : ""})</span>
          </button>
        </div>
      </div>
    `;
  }

  _renderProfileList(profiles, showRoaster = true) {
    if (!Array.isArray(profiles) || profiles.length === 0) {
      return `<div style="text-align: center; padding: 20px; color: var(--secondary-text-color, #777); font-size: 0.8rem;">No profiles available in this list.</div>`;
    }
    return `
      <div class="profile-list">
        ${profiles.map((p) => this._renderProfileCard(p, showRoaster)).join("")}
      </div>
    `;
  }

  _renderProfileCard(profile, showRoaster = true) {
    const jsonStr = encodeURIComponent(JSON.stringify(profile));
    const isFav = !!profile.is_favorite;
    const bloomText = (profile.bloom_duration && profile.bloom_duration > 0) || profile.bloom_enabled
      ? ` • Bloom ${profile.bloom_duration || 10}s`
      : "";
    const bypassText = (profile.water_output && profile.water_output > 0) || profile.bypass_enabled
      ? ` • +${profile.water_output}mL water`
      : "";

    return `
      <div class="profile-card">
        <div class="profile-info">
          <div class="profile-header-line">
            <span class="profile-name">${this._escapeHtml(profile.name || "Unnamed Profile")}</span>
            ${showRoaster && (profile.roaster_name || profile.author_name) ? `
              <span class="profile-roaster-badge">${this._escapeHtml(profile.roaster_name || profile.author_name)}</span>
            ` : ""}
          </div>
          <div class="profile-specs">
            <span class="highlight">${profile.temperature || 94}°C</span>
            <span>•</span>
            <span>${profile.mass_output || 40}g yield</span>
            ${bloomText ? `<span>${bloomText}</span>` : ""}
            ${bypassText ? `<span style="color: #3498db; font-weight: 600;">${bypassText}</span>` : ""}
          </div>
        </div>
        ${this._renderSparklineSvg(profile.stages, profile.mass_output)}
        <div class="profile-actions">
          <button class="icon-action-btn fav${isFav ? " active" : ""}" data-action="toggle-fav" data-profile="${jsonStr}">
            <ha-icon icon="${isFav ? "mdi:star" : "mdi:star-outline"}"></ha-icon>
          </button>
          <button class="icon-action-btn" data-action="load-studio" data-profile="${jsonStr}">
            <ha-icon icon="mdi:tune-vertical"></ha-icon>
          </button>
          <button class="brew-pill-btn" data-action="brew-profile" data-profile="${jsonStr}">
            <ha-icon icon="mdi:coffee"></ha-icon>
            <span>Brew</span>
          </button>
        </div>
      </div>
    `;
  }

  _renderSparklineSvg(stages, massOutput) {
    if (!Array.isArray(stages) || stages.length < 3) {
      return `<svg class="profile-sparkline" viewBox="0 0 70 24"></svg>`;
    }
    const mass = massOutput || 40;
    const calcX = (w) => 3 + (Math.max(0, Math.min(mass, w)) / mass) * 64;
    const calcY = (p) => 21 - ((Math.max(1, Math.min(7, p)) - 1) / 6) * 18;

    const s0 = stages[0];
    const s1 = stages[1];
    const s2 = stages[2];

    const x0 = 3;
    const y0 = calcY(s0.pressure || 3);
    const x1 = calcX(s1.output || 5);
    const y1 = calcY(s1.pressure || 7);
    const x2 = calcX(s2.output || 30);
    const y2 = calcY(s2.pressure || 5);
    const xEnd = 67;
    const yEnd = y2;

    const areaPath = `M ${x0} 21 L ${x0} ${y0.toFixed(1)} L ${x1.toFixed(1)} ${y1.toFixed(1)} L ${x2.toFixed(1)} ${y2.toFixed(1)} L ${xEnd} ${yEnd.toFixed(1)} L ${xEnd} 21 Z`;

    return `
      <svg class="profile-sparkline" viewBox="0 0 70 24" xmlns="http://www.w3.org/2000/svg">
        <path d="${areaPath}" fill="rgba(230, 126, 34, 0.15)" />
        <line x1="${x0}" y1="${y0.toFixed(1)}" x2="${x1.toFixed(1)}" y2="${y1.toFixed(1)}" stroke="#1abc9c" stroke-width="1.8" stroke-linecap="round" />
        <line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="#e67e22" stroke-width="1.8" stroke-linecap="round" />
        <line x1="${x2.toFixed(1)}" y1="${y2.toFixed(1)}" x2="${xEnd}" y2="${yEnd.toFixed(1)}" stroke="#e74c3c" stroke-width="1.8" stroke-linecap="round" />
      </svg>
    `;
  }

  _generateStudioSvg(draft) {
    const mass = draft.mass_output || 40;
    const calcX = (w) => 40 + (w / mass) * 350;
    const calcY = (p) => 130 - ((p - 1) / 6) * 110;

    const s0 = draft.stages && draft.stages[0] ? draft.stages[0] : { output: 0, pressure: 3 };
    const s1 = draft.stages && draft.stages[1] ? draft.stages[1] : { output: 5, pressure: 7 };
    const s2 = draft.stages && draft.stages[2] ? draft.stages[2] : { output: Math.round(mass * 0.8), pressure: 5 };

    const x0 = 40;
    const y0 = calcY(s0.pressure);
    const x1 = calcX(s1.output);
    const y1 = calcY(s1.pressure);
    const x2 = calcX(s2.output);
    const y2 = calcY(s2.pressure);
    const xEnd = 390;
    const yEnd = y2;

    const hasBloom = draft.bloom_duration && draft.bloom_duration > 0;
    const hasBypass = draft.water_output && draft.water_output > 0;

    const areaPath = `M ${x0} 130 L ${x0} ${y0.toFixed(1)} L ${x1.toFixed(1)} ${y1.toFixed(1)} L ${x2.toFixed(1)} ${y2.toFixed(1)} L ${xEnd} ${yEnd.toFixed(1)} L ${xEnd} 130 Z`;

    const pressureLevels = [1, 2, 3, 4, 5, 6, 7];

    return `
      <div class="studio-svg-box">
        <div class="studio-floating-tooltip"></div>
        <svg class="studio-svg" viewBox="0 0 420 160" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="studioCurveGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#e67e22" stop-opacity="0.28" />
              <stop offset="100%" stop-color="#e67e22" stop-opacity="0.0" />
            </linearGradient>
            <linearGradient id="bloomZoneGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#f39c12" stop-opacity="0.25" />
              <stop offset="100%" stop-color="#f39c12" stop-opacity="0.04" />
            </linearGradient>
          </defs>

          <!-- Stage Background Columns -->
          <rect class="stage-bg-col0" x="${x0}" y="20" width="${Math.max(0, x1 - x0).toFixed(1)}" height="110" fill="rgba(26, 188, 156, 0.05)" />
          <rect class="stage-bg-col1" x="${x1.toFixed(1)}" y="20" width="${Math.max(0, x2 - x1).toFixed(1)}" height="110" fill="rgba(230, 126, 34, 0.05)" />
          <rect class="stage-bg-col2" x="${x2.toFixed(1)}" y="20" width="${Math.max(0, xEnd - x2).toFixed(1)}" height="110" fill="rgba(231, 76, 60, 0.05)" />

          <!-- Optional Bloom Column Marker -->
          ${hasBloom ? `
            <rect class="bloom-marker-rect" x="${(x1 - 8).toFixed(1)}" y="20" width="16" height="110" fill="url(#bloomZoneGrad)" />
            <line class="bloom-marker-line" x1="${x1.toFixed(1)}" y1="20" x2="${x1.toFixed(1)}" y2="130" stroke="#f39c12" stroke-width="1.5" stroke-dasharray="3 3" />
            <text class="bloom-marker-text" x="${x1.toFixed(1)}" y="16" fill="#f39c12" font-size="8" font-weight="bold" text-anchor="middle" font-family="sans-serif">⏳ ${draft.bloom_duration}s Bloom</text>
          ` : ""}

          <!-- Grid Lines & Pressure Labels -->
          ${pressureLevels.map((p) => {
            const py = calcY(p);
            const isMain = p === 1 || p === 4 || p === 7;
            return `
              <line x1="40" y1="${py.toFixed(1)}" x2="390" y2="${py.toFixed(1)}" stroke="rgba(255,255,255,${isMain ? "0.12" : "0.04"})" stroke-dasharray="${isMain ? "none" : "2 3"}" stroke-width="1" />
              <text x="34" y="${(py + 3).toFixed(1)}" fill="rgba(255,255,255,${isMain ? "0.5" : "0.25"})" font-size="8" text-anchor="end" font-family="sans-serif">${p}b</text>
            `;
          }).join("")}

          <!-- Weight Axis (X) -->
          <line x1="40" y1="130" x2="390" y2="130" stroke="rgba(255,255,255,0.2)" stroke-width="1" />
          <text x="40" y="145" fill="rgba(255,255,255,0.4)" font-size="8" text-anchor="middle" font-family="sans-serif">0g</text>
          <text x="${calcX(mass * 0.5).toFixed(1)}" y="145" fill="rgba(255,255,255,0.4)" font-size="8" text-anchor="middle" font-family="sans-serif">${Math.round(mass * 0.5)}g</text>
          <text x="390" y="145" fill="rgba(255,255,255,0.4)" font-size="8" text-anchor="middle" font-family="sans-serif">${mass}g</text>

          <!-- Curve Area Fill -->
          <path class="studio-curve-area" d="${areaPath}" fill="url(#studioCurveGrad)" />

          <!-- Segment 0: Pre-Infusion Line (Teal) -->
          <line class="studio-curve-seg0 stage-seg" data-seg="0" x1="${x0}" y1="${y0.toFixed(1)}" x2="${x1.toFixed(1)}" y2="${y1.toFixed(1)}" stroke="#1abc9c" stroke-width="2.5" stroke-linecap="round" />

          <!-- Segment 1: Infusion Line (Amber) -->
          <line class="studio-curve-seg1 stage-seg" data-seg="1" x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="#e67e22" stroke-width="2.5" stroke-linecap="round" />

          <!-- Segment 2: Post-Infusion Line (Coral) -->
          <line class="studio-curve-seg2 stage-seg" data-seg="2" x1="${x2.toFixed(1)}" y1="${y2.toFixed(1)}" x2="${xEnd}" y2="${yEnd.toFixed(1)}" stroke="#e74c3c" stroke-width="2.5" stroke-linecap="round" />

          <!-- Optional Bypass Water Flow Tail (Blue) -->
          ${hasBypass ? `
            <line class="stage-seg-bypass" x1="390" y1="${yEnd.toFixed(1)}" x2="414" y2="${yEnd.toFixed(1)}" stroke="#3498db" stroke-width="3" stroke-dasharray="2 3" stroke-linecap="round" />
            <circle cx="414" cy="${yEnd.toFixed(1)}" r="3" fill="#3498db" />
            <text x="402" y="145" fill="#3498db" font-size="7.5" font-weight="bold" text-anchor="middle" font-family="sans-serif">+${draft.water_output}mL</text>
          ` : ""}

          <!-- Draggable Handles: 50% smaller visual radius (r=3.5) + invisible touch target (r=14) -->
          <circle class="studio-handle" data-handle="0" cx="${x0}" cy="${y0.toFixed(1)}" r="3.5" fill="#fff" stroke="#1abc9c" stroke-width="1.8" />
          <circle class="studio-handle-hit" data-handle="0" cx="${x0}" cy="${y0.toFixed(1)}" r="14" fill="transparent" pointer-events="all" />

          <circle class="studio-handle" data-handle="1" cx="${x1.toFixed(1)}" cy="${y1.toFixed(1)}" r="3.5" fill="#fff" stroke="#e67e22" stroke-width="1.8" />
          <circle class="studio-handle-hit" data-handle="1" cx="${x1.toFixed(1)}" cy="${y1.toFixed(1)}" r="14" fill="transparent" pointer-events="all" />

          <circle class="studio-handle" data-handle="2" cx="${x2.toFixed(1)}" cy="${y2.toFixed(1)}" r="3.5" fill="#fff" stroke="#e74c3c" stroke-width="1.8" />
          <circle class="studio-handle-hit" data-handle="2" cx="${x2.toFixed(1)}" cy="${y2.toFixed(1)}" r="14" fill="transparent" pointer-events="all" />
        </svg>

        <!-- Stage Information Pills -->
        <div class="studio-stages-pills">
          <span class="stage-pill" data-pill="0">
            <span class="stage-pill-dot" style="background: #1abc9c;"></span>
            <strong>Pre-Infusion:</strong> <span class="pill-val">0g @ ${s0.pressure}b</span>
          </span>
          ${hasBloom ? `
            <span class="stage-pill" data-pill="bloom" style="border-color: rgba(243, 156, 18, 0.4); color: #f39c12;">
              <span class="stage-pill-dot" style="background: #f39c12;"></span>
              <strong>Bloom:</strong> ${draft.bloom_duration}s
            </span>
          ` : ""}
          <span class="stage-pill" data-pill="1">
            <span class="stage-pill-dot" style="background: #e67e22;"></span>
            <strong>Infusion:</strong> <span class="pill-val">${s1.output}g @ ${s1.pressure}b</span>
          </span>
          <span class="stage-pill" data-pill="2">
            <span class="stage-pill-dot" style="background: #e74c3c;"></span>
            <strong>Post-Infusion:</strong> <span class="pill-val">${s2.output}g @ ${s2.pressure}b</span>
          </span>
          ${hasBypass ? `
            <span class="stage-pill" data-pill="bypass" style="border-color: rgba(52, 152, 219, 0.4); color: #3498db;">
              <span class="stage-pill-dot" style="background: #3498db;"></span>
              <strong>Bypass:</strong> +${draft.water_output}mL
            </span>
          ` : ""}
        </div>
      </div>
    `;
  }

  _setupStudioInteraction(box) {
    if (!box) return;
    const svg = box.querySelector(".studio-svg");
    const tooltip = box.querySelector(".studio-floating-tooltip");
    if (!svg) return;

    const draft = this._draftCurve;
    const mass = draft.mass_output || 40;

    let activeHandle = null;
    let activeIdx = -1;

    const calcX = (w) => 40 + (w / mass) * 350;
    const calcY = (p) => 130 - ((p - 1) / 6) * 110;
    const inverseX = (x) => Math.round(((x - 40) / 350) * mass);
    const inverseY = (y) => Math.round(1 + ((130 - y) / 110) * 6);

    const updateSvg = () => {
      const s0 = draft.stages[0];
      const s1 = draft.stages[1];
      const s2 = draft.stages[2];

      const x0 = 40;
      const y0 = calcY(s0.pressure);
      const x1 = calcX(s1.output);
      const y1 = calcY(s1.pressure);
      const x2 = calcX(s2.output);
      const y2 = calcY(s2.pressure);
      const xEnd = 390;
      const yEnd = y2;

      const seg0 = svg.querySelector(".studio-curve-seg0");
      const seg1 = svg.querySelector(".studio-curve-seg1");
      const seg2 = svg.querySelector(".studio-curve-seg2");
      const areaEl = svg.querySelector(".studio-curve-area");

      if (seg0) {
        seg0.setAttribute("x1", String(x0));
        seg0.setAttribute("y1", y0.toFixed(1));
        seg0.setAttribute("x2", x1.toFixed(1));
        seg0.setAttribute("y2", y1.toFixed(1));
      }
      if (seg1) {
        seg1.setAttribute("x1", x1.toFixed(1));
        seg1.setAttribute("y1", y1.toFixed(1));
        seg1.setAttribute("x2", x2.toFixed(1));
        seg1.setAttribute("y2", y2.toFixed(1));
      }
      if (seg2) {
        seg2.setAttribute("x1", x2.toFixed(1));
        seg2.setAttribute("y1", y2.toFixed(1));
        seg2.setAttribute("x2", String(xEnd));
        seg2.setAttribute("y2", yEnd.toFixed(1));
      }
      if (areaEl) {
        const areaPath = `M ${x0} 130 L ${x0} ${y0.toFixed(1)} L ${x1.toFixed(1)} ${y1.toFixed(1)} L ${x2.toFixed(1)} ${y2.toFixed(1)} L ${xEnd} ${yEnd.toFixed(1)} L ${xEnd} 130 Z`;
        areaEl.setAttribute("d", areaPath);
      }

      // Update background column widths
      const bg0 = svg.querySelector(".stage-bg-col0");
      const bg1 = svg.querySelector(".stage-bg-col1");
      const bg2 = svg.querySelector(".stage-bg-col2");
      if (bg0) bg0.setAttribute("width", Math.max(0, x1 - x0).toFixed(1));
      if (bg1) {
        bg1.setAttribute("x", x1.toFixed(1));
        bg1.setAttribute("width", Math.max(0, x2 - x1).toFixed(1));
      }
      if (bg2) {
        bg2.setAttribute("x", x2.toFixed(1));
        bg2.setAttribute("width", Math.max(0, xEnd - x2).toFixed(1));
      }

      // Update bloom marker if present
      const bRect = svg.querySelector(".bloom-marker-rect");
      const bLine = svg.querySelector(".bloom-marker-line");
      const bText = svg.querySelector(".bloom-marker-text");
      if (bRect) bRect.setAttribute("x", (x1 - 8).toFixed(1));
      if (bLine) {
        bLine.setAttribute("x1", x1.toFixed(1));
        bLine.setAttribute("x2", x1.toFixed(1));
      }
      if (bText) bText.setAttribute("x", x1.toFixed(1));

      [0, 1, 2].forEach((idx) => {
        const cx = idx === 0 ? x0 : idx === 1 ? x1 : x2;
        const cy = idx === 0 ? y0 : idx === 1 ? y1 : y2;
        const h = svg.querySelector(`.studio-handle[data-handle="${idx}"]`);
        const hit = svg.querySelector(`.studio-handle-hit[data-handle="${idx}"]`);
        if (h) {
          h.setAttribute("cx", typeof cx === "number" ? cx.toFixed(1) : String(cx));
          h.setAttribute("cy", cy.toFixed(1));
        }
        if (hit) {
          hit.setAttribute("cx", typeof cx === "number" ? cx.toFixed(1) : String(cx));
          hit.setAttribute("cy", cy.toFixed(1));
        }
      });

      // Update stage pill text values
      const pill0 = box.querySelector('.stage-pill[data-pill="0"] .pill-val');
      if (pill0) pill0.textContent = `0g @ ${s0.pressure}b`;
      const pill1 = box.querySelector('.stage-pill[data-pill="1"] .pill-val');
      if (pill1) pill1.textContent = `${s1.output}g @ ${s1.pressure}b`;
      const pill2 = box.querySelector('.stage-pill[data-pill="2"] .pill-val');
      if (pill2) pill2.textContent = `${s2.output}g @ ${s2.pressure}b`;
    };

    const onPointerDown = (e) => {
      const handleEl = e.target.closest(".studio-handle, .studio-handle-hit");
      if (!handleEl) return;
      activeIdx = parseInt(handleEl.getAttribute("data-handle"), 10);
      activeHandle = svg.querySelector(`.studio-handle[data-handle="${activeIdx}"]`) || handleEl;
      activeHandle.classList.add("active");
      try {
        if (typeof handleEl.setPointerCapture === "function") {
          handleEl.setPointerCapture(e.pointerId);
        }
      } catch (_) {}
      e.preventDefault();
      e.stopPropagation();
    };

    const onPointerMove = (e) => {
      if (!activeHandle || activeIdx < 0) return;
      const rect = svg.getBoundingClientRect();
      const clientX = e.clientX;
      const clientY = e.clientY;
      const relX = clientX - rect.left;
      const relY = clientY - rect.top;
      const svgX = (relX / (rect.width || 420)) * 420;
      const svgY = (relY / (rect.height || 160)) * 160;

      const pClamped = Math.max(1, Math.min(7, inverseY(svgY)));

      if (activeIdx === 0) {
        draft.stages[0].pressure = pClamped;
        if (tooltip) {
          tooltip.textContent = `Pre-Infusion: 0g @ ${pClamped} bar`;
          tooltip.style.display = "block";
        }
      } else if (activeIdx === 1) {
        const wClamped = Math.max(2, Math.min(draft.stages[2].output - 2, inverseX(svgX)));
        draft.stages[1].output = wClamped;
        draft.stages[1].pressure = pClamped;
        if (tooltip) {
          tooltip.textContent = `Infusion: ${wClamped}g @ ${pClamped} bar`;
          tooltip.style.display = "block";
        }
      } else if (activeIdx === 2) {
        const wClamped = Math.max(draft.stages[1].output + 2, Math.min(mass - 2, inverseX(svgX)));
        draft.stages[2].output = wClamped;
        draft.stages[2].pressure = pClamped;
        if (tooltip) {
          tooltip.textContent = `Post-Infusion: ${wClamped}g @ ${pClamped} bar`;
          tooltip.style.display = "block";
        }
      }

      this._activePresetKey = "custom";
      if (box.parentElement) {
        const presetBtns = box.parentElement.querySelectorAll(".preset-btn");
        presetBtns.forEach((btn) => {
          btn.classList.toggle("active", btn.getAttribute("data-preset") === "custom");
        });
      }

      updateSvg();
    };

    const onPointerUp = (e) => {
      if (!activeHandle) return;
      activeHandle.classList.remove("active");
      try {
        if (typeof activeHandle.releasePointerCapture === "function") {
          activeHandle.releasePointerCapture(e.pointerId);
        }
      } catch (_) {}
      activeHandle = null;
      activeIdx = -1;
      if (tooltip) tooltip.style.display = "none";
    };

    svg.addEventListener("pointerdown", onPointerDown);
    svg.addEventListener("pointermove", onPointerMove);
    svg.addEventListener("pointerup", onPointerUp);
    svg.addEventListener("pointercancel", onPointerUp);
  }

  _renderDiagItem(id) {
    const entityId = this._resolvedEntities[id];
    const clickableClass = entityId ? " clickable" : "";
    const dataAttr = entityId ? ` data-entity-id="${entityId}"` : "";

    switch (id) {
      case "total_brews":
        return `
          <div class="diag-item${clickableClass}"${dataAttr}>
            <span class="diag-label">Total Brews</span>
            <span class="diag-val">${this._getValue("total_brews", "--")}</span>
          </div>`;
      case "limescale":
        return `
          <div class="diag-item${clickableClass}"${dataAttr}>
            <span class="diag-label">Limescale</span>
            <span class="diag-val">${this._getValue("limescale", "--")}</span>
          </div>`;
      case "child_lock": {
        const isLocked = this._getValue("child_lock", "off") === "on";
        return `
          <div class="diag-item${clickableClass}"${dataAttr}>
            <span class="diag-label">Child Lock</span>
            <span class="diag-val" style="color: ${isLocked ? "#e67e22" : "inherit"};">${isLocked ? "Active" : "Off"}</span>
          </div>`;
      }
      case "standby": {
        const timeout = this._getValue("standby", "--");
        return `
          <div class="diag-item${clickableClass}"${dataAttr}>
            <span class="diag-label">Standby</span>
            <span class="diag-val">${timeout !== "--" ? timeout + "s" : "--"}</span>
          </div>`;
      }
      case "firmware":
        return `
          <div class="diag-item${clickableClass}"${dataAttr}>
            <span class="diag-label">Firmware</span>
            <span class="diag-val">${this._getValue("firmware", "--")}</span>
          </div>`;
      case "slave_firmware":
        return `
          <div class="diag-item${clickableClass}"${dataAttr}>
            <span class="diag-label">Motor Controller</span>
            <span class="diag-val">${this._getValue("slave_firmware", "--")}</span>
          </div>`;
      case "lifetime_water": {
        const ltr = parseFloat(this._getValue("lifetime_water", "0.0") || "0.0");
        return `
          <div class="diag-item${clickableClass}"${dataAttr}>
            <span class="diag-label">Lifetime Water</span>
            <span class="diag-val">${ltr.toFixed(1)} L</span>
          </div>`;
      }
      case "fault_code":
        return `
          <div class="diag-item${clickableClass}"${dataAttr}>
            <span class="diag-label">Fault Code</span>
            <span class="diag-val">${this._getValue("fault_code", "None")}</span>
          </div>`;
      default:
        return "";
    }
  }

  _updateContent() {
    if (!this.shadowRoot) return;
    const root = this.shadowRoot.getElementById("card-root");
    if (!root) return;

    if (!this._config || !this._config.entity) {
      root.innerHTML = `
        <div style="padding: 24px 16px; text-align: center; color: var(--secondary-text-color, #888);">
          <ha-icon icon="mdi:coffee-maker-outline" style="--mdc-icon-size: 36px; margin-bottom: 8px; display: inline-block; color: var(--primary-color, #e67e22);"></ha-icon>
          <div style="font-weight: 600; font-size: 0.95rem; color: var(--primary-text-color, #fff);">Morning Coffee Machine Card</div>
          <div style="font-size: 0.8rem; margin-top: 4px;">Please select an entity in the card editor.</div>
        </div>
      `;
      return;
    }

    if (!this._hass || !this._hass.states) {
      root.innerHTML = `<div style="padding: 16px; text-align: center; color: #888;">Loading...</div>`;
      return;
    }

    const statusState = this._getState("status");
    if (!statusState) {
      root.innerHTML = `<div style="padding: 16px; text-align: center; color: #888;">Entity unavailable</div>`;
      return;
    }

    const machineName =
      this._config.name || statusState.attributes?.friendly_name || "Morning Coffee Machine";
    const rawStatus = (statusState.state || "unknown").toLowerCase();
    const isOnline = this._getValue("connectivity", "on") === "on";

    // Telemetry values
    const rawWaterMl = parseFloat(this._getValue("water_level", "850"));
    const waterLevelMl = Number.isFinite(rawWaterMl) ? rawWaterMl : 850;
    const rawWaterPct = parseFloat(this._getValue("water_pct", "100"));
    const waterLevelPct = Number.isFinite(rawWaterPct) ? rawWaterPct : 100;
    let rawWaterDisp = parseFloat(this._getValue("brew_water", "0.0") || "0.0");
    let waterDispensed = Number.isFinite(rawWaterDisp) ? rawWaterDisp : 0.0;
    let rawMassDisp = parseFloat(this._getValue("brew_mass", "0.0") || "0.0");
    let massDispensed = Number.isFinite(rawMassDisp) ? rawMassDisp : 0.0;
    let brewTemp = this._getValue("brew_temp", "--");
    let bloomDuration = this._getValue("brew_bloom", "0");

    const stage = (this._getValue("brew_stage", "idle") || "idle").toLowerCase();
    const isTerminalOrIdleStage = ["done", "cancel", "cancelled", "canceled", "abort", "idle", "ready", "eco"].includes(stage);
    const isHeating = (rawStatus === "heating" || stage === "heating") && !isTerminalOrIdleStage;
    const isPurge = (rawStatus === "purge" || stage === "purge") && !isTerminalOrIdleStage;
    const isBrewing =
      (["heating", "blooming", "brewing", "purge"].includes(stage) ||
        ["heating", "brewing", "purge"].includes(rawStatus)) &&
      !isTerminalOrIdleStage;
    const displayStatus = (rawStatus === "brewing" && isTerminalOrIdleStage)
      ? (stage === "done" ? "done" : "idle")
      : isPurge
      ? (isBrewing ? "purge" : "done")
      : isHeating
      ? "heating"
      : isBrewing
      ? "brewing"
      : rawStatus;

    const isPurgeCycle = isPurge || (stage === "done" && brewTemp === "--" && massDispensed === 0 && waterDispensed > 0);

    const statusColor = STATUS_COLORS[displayStatus] || "#888";
    const statusBg = `${statusColor}22`;

    let currentStepIndex = STAGE_ORDER.indexOf(stage);
    if (isHeating) {
      currentStepIndex = 0;
    } else if (!isBrewing) {
      currentStepIndex = stage === "done" ? 3 : -1;
    } else if (currentStepIndex === -1) {
      currentStepIndex = 2;
    }

    const heroClass = isBrewing ? "brew-hero brewing" : stage === "done" ? "brew-hero done" : "brew-hero";

    const brewWaterEnt = this._resolvedEntities.brew_water;
    const brewMassEnt = this._resolvedEntities.brew_mass;
    const brewTempEnt = this._resolvedEntities.brew_temp;
    const brewBloomEnt = this._resolvedEntities.brew_bloom;
    const waterLevelEnt = this._resolvedEntities.water_level;

    let headerHtml = "";
    // 1. Header & Title Section
    const showHeader = this._config.show_header !== false && this._config.show_title !== false;
    if (showHeader) {
      headerHtml = `
        <div class="header">
          <div class="brand">
            <div class="brand-icon">
              <ha-icon icon="mdi:coffee-maker"></ha-icon>
            </div>
            <div class="title-block">
              <div class="name">${machineName}</div>
              <div class="sub">MM-730 Smart Brewer</div>
            </div>
          </div>
          <div class="header-badges">
            <span class="badge status" style="color: ${statusColor}; background: ${statusBg};">
              ${displayStatus}
            </span>
            <span class="badge ${isOnline ? "online" : "offline"}">
              ${isOnline ? "Online" : "Offline"}
            </span>
          </div>
        </div>
      `;
    }

    // 2. Brewing / Extraction Progress Monitor
    let heroHtml = "";
    const showBrewSection = this._config.show_brew_section !== false;
    const showExtractionCurve = this._config.show_extraction_curve !== false;

    if (showBrewSection) {
      let extractionCurveHtml = "";
      if (showExtractionCurve) {
        const stageState = this._getState("brew_stage");
        const waterState = this._getState("brew_water");
        const rawProfile =
          stageState?.attributes?.extraction_profile ||
          waterState?.attributes?.extraction_profile;
        let profile = Array.isArray(rawProfile) ? rawProfile.slice() : [];

        // Fallback: sync metrics with latest profile point if sensor values lag or zero out
        const latestPt = profile && profile.length > 0 ? profile[profile.length - 1] : null;
        if (latestPt) {
          if (waterDispensed <= 0 && Number(latestPt.water) > 0) {
            waterDispensed = Number(latestPt.water);
          }
          if (massDispensed <= 0 && Number(latestPt.mass) > 0) {
            massDispensed = Number(latestPt.mass);
          }
          if ((brewTemp === "--" || brewTemp === "unknown") && Number(latestPt.temp) > 0) {
            brewTemp = String(latestPt.temp);
          }
        }

        const stats = this._getExtractionStats(profile);
        const svgContent = this._generateExtractionSvg(profile, isBrewing);

        extractionCurveHtml = `
          <div class="extraction-container">
            <div class="extraction-header">
              <div class="extraction-title">
                <ha-icon icon="mdi:chart-bell-curve-cumulative"></ha-icon>
                <span>Extraction Curve</span>
              </div>
              <div class="extraction-stats">
                ${
                  stats.duration > 0
                    ? `
                  <span class="stat-chip"><ha-icon icon="mdi:timer-outline"></ha-icon>${stats.duration}s</span>
                  <span class="stat-chip"><ha-icon icon="mdi:coffee"></ha-icon>${stats.finalYield}g</span>
                  <span class="stat-chip"><ha-icon icon="mdi:waves-arrow-up"></ha-icon>${stats.peakFlow} ml/s</span>
                  ${
                    stats.avgTemp !== "--"
                      ? `<span class="stat-chip"><ha-icon icon="mdi:thermometer"></ha-icon>${stats.avgTemp}°C</span>`
                      : ""
                  }
                `
                    : ""
                }
                <span class="extraction-badge ${isBrewing ? "live" : "completed"}">
                  ${isBrewing ? "Live" : "Profile"}
                </span>
              </div>
            </div>
            ${svgContent}
            ${
              profile && profile.length > 0
                ? `
              <div class="chart-legend">
                <div class="legend-item"><span class="legend-dot yield"></span> Yield (g / mL)</div>
                <div class="legend-item"><span class="legend-dot flow"></span> Flow Rate (mL/s)</div>
                <div class="legend-item"><span class="legend-dot temp"></span> Temp (°C)</div>
              </div>
            `
                : ""
            }
          </div>
        `;
      }
      const stageStateForStepper = this._getState("brew_stage");
      const rawStagesSeen = stageStateForStepper?.attributes?.stages_seen;
      const stagesSeen = Array.isArray(rawStagesSeen)
        ? rawStagesSeen.map((s) => String(s).toLowerCase())
        : null;

      const stepperHtml = isPurgeCycle
        ? `
          <div class="stepper">
            <div class="stepper-line"></div>
            <div class="${isBrewing ? "step active" : "step passed"}">
              <div class="step-circle">${!isBrewing ? "✓" : "1"}</div>
              <div class="step-label">Purge</div>
            </div>
            <div class="${!isBrewing && stage === "done" ? "step passed" : "step"}">
              <div class="step-circle">${!isBrewing && stage === "done" ? "✓" : "2"}</div>
              <div class="step-label">Done</div>
            </div>
          </div>
        `
        : `
          <div class="stepper">
            <div class="stepper-line"></div>
            ${STAGE_ORDER.map((stepName, idx) => {
              const isActive = currentStepIndex === idx && isBrewing;
              const isPriorOrDone = currentStepIndex > idx || (!isBrewing && stage === "done");
              const wasSeen =
                stagesSeen && stagesSeen.length > 0
                  ? stagesSeen.includes(stepName) || (stepName === "done" && stage === "done")
                  : true;
              const isPassed = !isActive && isPriorOrDone && wasSeen;
              const isSkipped = !isActive && isPriorOrDone && !wasSeen;
              const cls = isActive
                ? "step active"
                : isPassed
                ? "step passed"
                : isSkipped
                ? "step skipped"
                : "step";
              const circleContent = isPassed ? "✓" : isSkipped ? "–" : idx + 1;
              return `
                <div class="${cls}">
                  <div class="step-circle">${circleContent}</div>
                  <div class="step-label">${stepName}</div>
                </div>
              `;
            }).join("")}
          </div>
        `;

      heroHtml = `
        <div class="${heroClass}">
          ${stepperHtml}

          <div class="telemetry-grid">
            <div class="metric-card${brewWaterEnt ? " clickable" : ""}"${brewWaterEnt ? ` data-entity-id="${brewWaterEnt}"` : ""}>
              <div class="metric-header">
                <ha-icon icon="mdi:water-pump"></ha-icon>
                <span>Water Dispensed</span>
              </div>
              <div class="metric-value">
                ${waterDispensed.toFixed(1)}<span class="metric-unit">mL</span>
              </div>
            </div>

            <div class="metric-card${brewMassEnt ? " clickable" : ""}"${brewMassEnt ? ` data-entity-id="${brewMassEnt}"` : ""}>
              <div class="metric-header">
                <ha-icon icon="mdi:scale"></ha-icon>
                <span>Mass Output</span>
              </div>
              <div class="metric-value">
                ${massDispensed.toFixed(1)}<span class="metric-unit">g</span>
              </div>
            </div>

            <div class="metric-card${brewTempEnt ? " clickable" : ""}"${brewTempEnt ? ` data-entity-id="${brewTempEnt}"` : ""}>
              <div class="metric-header">
                <ha-icon icon="mdi:thermometer"></ha-icon>
                <span>Brew Temp</span>
              </div>
              <div class="metric-value">
                ${brewTemp}<span class="metric-unit">${brewTemp !== "--" ? "°C" : ""}</span>
              </div>
            </div>

            <div class="metric-card${brewBloomEnt ? " clickable" : ""}"${brewBloomEnt ? ` data-entity-id="${brewBloomEnt}"` : ""}>
              <div class="metric-header">
                <ha-icon icon="mdi:timer-outline"></ha-icon>
                <span>Bloom / Timer</span>
              </div>
              <div class="metric-value">
                ${bloomDuration}<span class="metric-unit">s</span>
              </div>
            </div>
          </div>
          ${showExtractionCurve ? extractionCurveHtml : ""}
        </div>
      `;
    }

    // 2.5 Brew Initiation & Controls Section
    let brewControlsHtml = "";
    const showBrewControls = this._config.show_brew_controls !== false;
    if (showBrewControls) {
      const catalog = statusState.attributes?.recipe_catalog || {};
      const machineId = statusState.attributes?.machine_id || "";
      brewControlsHtml = this._renderBrewSection(catalog, isBrewing, machineId);
    }

    // 3. Water Reservoir Section
    let reservoirHtml = "";
    const showWaterGauge = this._config.show_water_gauge !== false;
    if (showWaterGauge) {
      const isLow = waterLevelPct <= 15;
      const barClass = isLow ? "progress-bar low" : "progress-bar";
      reservoirHtml = `
        <div class="reservoir-section">
          <div class="reservoir-header">
            <div class="reservoir-title">
              <ha-icon icon="mdi:water"></ha-icon>
              <span>Water Reservoir</span>
            </div>
            <div class="reservoir-status" style="color: ${isLow ? "#e74c3c" : "#3498db"};">
              ${waterLevelPct.toFixed(0)}%
            </div>
          </div>
          <div class="progress-bar-container${waterLevelEnt ? " clickable" : ""}"${waterLevelEnt ? ` data-entity-id="${waterLevelEnt}"` : ""}>
            <div class="${barClass}" style="width: ${Math.min(100, Math.max(0, waterLevelPct))}%;"></div>
          </div>
          <div class="reservoir-footer">
            <div class="reservoir-detail">${waterLevelMl.toFixed(0)} mL remaining</div>
            <div class="reservoir-actions">
              <button class="action-btn purge-btn" id="purge-action">
                <ha-icon icon="mdi:water-sync"></ha-icon>
                <span>Purge</span>
              </button>
              <button class="action-btn refill-btn" id="refill-action">
                <ha-icon icon="mdi:water-plus"></ha-icon>
                <span>Refill</span>
              </button>
            </div>
          </div>
        </div>
      `;
    }

    // 4. Selectable Diagnostics Bar
    let diagHtml = "";
    const showDiagnostics = this._config.show_diagnostics !== false;
    const activeStats = Array.isArray(this._config.status_items)
      ? this._config.status_items
      : DEFAULT_STATUS_ITEMS;

    if (showDiagnostics && activeStats.length > 0) {
      const itemsHtml = activeStats
        .map((itemId) => this._renderDiagItem(itemId))
        .filter(Boolean)
        .join("");

      if (itemsHtml.trim().length > 0) {
        diagHtml = `<div class="diag-grid">${itemsHtml}</div>`;
      }
    }

    // Capture and preserve scroll positions
    const existingDrawer = root.querySelector(".drawer-body");
    const savedDrawerScroll = existingDrawer ? existingDrawer.scrollTop : (this._savedDrawerScroll || 0);
    const existingList = root.querySelector(".profile-list");
    const savedProfileScroll = existingList ? existingList.scrollTop : (this._savedProfileScroll || 0);
    this._savedDrawerScroll = savedDrawerScroll;
    this._savedProfileScroll = savedProfileScroll;

    const existingBrewSection = root.querySelector("#sec-brew");
    const isBrewingChanged = this._lastBrewingState !== isBrewing;

    if (!existingBrewSection) {
      root.innerHTML = `
        <div id="sec-header">${headerHtml}</div>
        <div id="sec-hero">${heroHtml}</div>
        <div id="sec-brew">${brewControlsHtml}</div>
        <div id="sec-reservoir">${reservoirHtml}</div>
        <div id="sec-diag">${diagHtml}</div>
      `;
      this._brewSectionDirty = false;
      this._lastBrewingState = isBrewing;

      if (showBrewControls && this._brewDrawerOpen && this._activeBrewTab === "studio") {
        const studioSvgBox = root.querySelector(".studio-svg-box");
        if (studioSvgBox) {
          this._setupStudioInteraction(studioSvgBox);
        }
      }

      if (showBrewControls && this._brewDrawerOpen && this._activeBrewTab === "search") {
        const searchInput = root.querySelector("#search-input");
        if (searchInput) {
          searchInput.addEventListener("input", (e) => {
            this._searchQuery = e.target.value;
          });
          searchInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              this._performSearch(this._searchQuery);
            }
          });
        }
      }
    } else {
      const secHeader = root.querySelector("#sec-header");
      if (secHeader && secHeader.innerHTML !== headerHtml) secHeader.innerHTML = headerHtml;

      const secHero = root.querySelector("#sec-hero");
      if (secHero) secHero.innerHTML = heroHtml;

      const secReservoir = root.querySelector("#sec-reservoir");
      if (secReservoir && secReservoir.innerHTML !== reservoirHtml) secReservoir.innerHTML = reservoirHtml;

      const secDiag = root.querySelector("#sec-diag");
      if (secDiag && secDiag.innerHTML !== diagHtml) secDiag.innerHTML = diagHtml;

      // Update brew section if dirty or brewing state toggled
      if (this._brewSectionDirty || isBrewingChanged) {
        existingBrewSection.innerHTML = brewControlsHtml;
        this._brewSectionDirty = false;
        this._lastBrewingState = isBrewing;

        if (showBrewControls && this._brewDrawerOpen && this._activeBrewTab === "studio") {
          const studioSvgBox = existingBrewSection.querySelector(".studio-svg-box");
          if (studioSvgBox) {
            this._setupStudioInteraction(studioSvgBox);
          }
        }

        if (showBrewControls && this._brewDrawerOpen && this._activeBrewTab === "search") {
          const searchInput = existingBrewSection.querySelector("#search-input");
          if (searchInput) {
            searchInput.addEventListener("input", (e) => {
              this._searchQuery = e.target.value;
            });
            searchInput.addEventListener("keydown", (e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                this._performSearch(this._searchQuery);
              }
            });
          }
        }

        // Restore scroll positions seamlessly
        if (savedDrawerScroll) {
          const newDrawer = existingBrewSection.querySelector(".drawer-body");
          if (newDrawer) newDrawer.scrollTop = savedDrawerScroll;
        }
        if (savedProfileScroll) {
          const newList = existingBrewSection.querySelector(".profile-list");
          if (newList) newList.scrollTop = savedProfileScroll;
        }
      }
    }

    if (showBrewSection && showExtractionCurve) {
      const container = root.querySelector(".extraction-container");
      if (
        container &&
        this._currentProfile &&
        this._currentProfile.length >= 2
      ) {
        this._setupChartInteraction(
          container,
          this._currentProfile,
          this._currentMaxT,
          this._currentMaxOutput,
          this._currentMaxFlow
        );
      }
    }
  }

  _getSmoothPath(points) {
    if (!points || points.length === 0) return "";
    if (points.length === 1) return `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
    let d = `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[Math.max(0, i - 1)];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[Math.min(points.length - 1, i + 2)];
      const cp1x = p1.x + (p2.x - p0.x) / 6;
      const cp1y = p1.y + (p2.y - p0.y) / 6;
      const cp2x = p2.x - (p3.x - p1.x) / 6;
      const cp2y = p2.y - (p3.y - p1.y) / 6;
      d += ` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)}, ${cp2x.toFixed(1)} ${cp2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
    }
    return d;
  }

  _getExtractionStats(profile) {
    if (!Array.isArray(profile) || profile.length === 0) {
      return { duration: "0.0", finalYield: "0.0", peakFlow: "0.0", avgTemp: "--" };
    }
    const last = profile[profile.length - 1];
    const duration = typeof last?.t === "number" ? last.t : 0;
    const yields = profile.map((p) => Math.max(Number(p.water) || 0, Number(p.mass) || 0));
    const finalYield = yields.length > 0 ? Math.max(...yields) : 0;
    const flows = profile.map((p) => Number(p.flow) || 0);
    const peakFlow = flows.length > 0 ? Math.max(...flows) : 0;
    const temps = profile.filter((p) => Number(p.temp) > 0).map((p) => Number(p.temp));
    const avgTemp = temps.length > 0 ? Math.round(temps.reduce((a, b) => a + b, 0) / temps.length) : 0;
    return {
      duration: duration.toFixed(1),
      finalYield: finalYield.toFixed(1),
      peakFlow: peakFlow.toFixed(1),
      avgTemp: avgTemp > 0 ? avgTemp : "--",
    };
  }

  _generateExtractionSvg(profile, isBrewing) {
    if (!Array.isArray(profile) || profile.length === 0) {
      this._currentProfile = null;
      return `
        <div style="padding: 18px 12px; text-align: center; color: var(--secondary-text-color, #777); font-size: 0.75rem;">
          <ha-icon icon="mdi:chart-bell-curve-cumulative" style="--mdc-icon-size: 24px; opacity: 0.35; display: block; margin: 0 auto 6px;"></ha-icon>
          Extraction curve will record and display here during brewing.
        </div>
      `;
    }

    const lastT = Number(profile[profile.length - 1]?.t) || 0;
    const maxT = Math.max(25, Math.ceil(lastT / 5) * 5);
    const yields = profile.map((p) => Math.max(Number(p.water) || 0, Number(p.mass) || 0));
    const rawMaxOutput = yields.length > 0 ? Math.max(...yields) : 0;
    const maxOutput = Math.max(30, Math.ceil(rawMaxOutput / 10) * 10);
    const flows = profile.map((p) => Number(p.flow) || 0);
    const rawMaxFlow = flows.length > 0 ? Math.max(...flows) : 0;
    const maxFlow = Math.max(3.0, Math.ceil(rawMaxFlow * 2) / 2);

    this._currentProfile = profile;
    this._currentMaxT = maxT;
    this._currentMaxOutput = maxOutput;
    this._currentMaxFlow = maxFlow;

    const calcX = (t) => 35 + (t / maxT) * 350;
    const calcYYield = (val) => 128 - ((val / maxOutput) * 113);
    const calcYFlow = (flow) => 128 - ((flow / maxFlow) * 113);
    const calcYTemp = (temp) => (temp > 0 ? 128 - (((Math.min(100, Math.max(60, temp)) - 60) / 40) * 113) : 128);

    const yieldPts = profile.map((p) => ({
      x: calcX(p.t),
      y: calcYYield(Math.max(p.water || 0, p.mass || 0)),
    }));
    const flowPts = profile.map((p) => ({
      x: calcX(p.t),
      y: calcYFlow(p.flow || 0),
    }));
    const tempPts = profile
      .filter((p) => p.temp > 0)
      .map((p) => ({
        x: calcX(p.t),
        y: calcYTemp(p.temp),
      }));

    const yieldPath = this._getSmoothPath(yieldPts);
    const flowPath = this._getSmoothPath(flowPts);
    const tempPath = this._getSmoothPath(tempPts);

    const firstPt = yieldPts[0];
    const lastPt = yieldPts[yieldPts.length - 1];
    const yieldAreaPath = `${yieldPath} L ${lastPt.x.toFixed(1)} 128 L ${firstPt.x.toFixed(1)} 128 Z`;

    const gridY1 = 128;
    const gridY2 = 128 - 113 * 0.33;
    const gridY3 = 128 - 113 * 0.66;
    const gridY4 = 15;

    const xTicks = [];
    const step = maxT <= 30 ? 5 : maxT <= 60 ? 10 : 15;
    for (let t = 0; t <= maxT; t += step) {
      xTicks.push(t);
    }

    return `
      <div class="chart-svg-container">
        <div class="curve-tooltip"></div>
        <svg class="chart-svg" viewBox="0 0 420 150" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="yieldGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#e67e22" stop-opacity="0.32" />
              <stop offset="100%" stop-color="#e67e22" stop-opacity="0.0" />
            </linearGradient>
            <filter id="flowGlow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="2" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          <!-- Grid Lines -->
          <line x1="35" y1="${gridY1}" x2="385" y2="${gridY1}" stroke="rgba(255,255,255,0.12)" stroke-width="1" />
          <line x1="35" y1="${gridY2.toFixed(1)}" x2="385" y2="${gridY2.toFixed(1)}" stroke="rgba(255,255,255,0.05)" stroke-width="1" stroke-dasharray="3 3" />
          <line x1="35" y1="${gridY3.toFixed(1)}" x2="385" y2="${gridY3.toFixed(1)}" stroke="rgba(255,255,255,0.05)" stroke-width="1" stroke-dasharray="3 3" />
          <line x1="35" y1="${gridY4}" x2="385" y2="${gridY4}" stroke="rgba(255,255,255,0.08)" stroke-width="1" stroke-dasharray="3 3" />

          <!-- Y Axis Labels Left (Yield in g/mL) -->
          <text x="30" y="18" fill="rgba(255,255,255,0.4)" font-size="8.5" text-anchor="end" font-family="sans-serif">${maxOutput}</text>
          <text x="30" y="${(gridY3 + 3).toFixed(1)}" fill="rgba(255,255,255,0.3)" font-size="8" text-anchor="end" font-family="sans-serif">${Math.round(maxOutput * 0.66)}</text>
          <text x="30" y="${(gridY2 + 3).toFixed(1)}" fill="rgba(255,255,255,0.3)" font-size="8" text-anchor="end" font-family="sans-serif">${Math.round(maxOutput * 0.33)}</text>
          <text x="30" y="131" fill="rgba(255,255,255,0.3)" font-size="8" text-anchor="end" font-family="sans-serif">0</text>

          <!-- Y Axis Labels Right (Temp in °C) -->
          <text x="390" y="18" fill="#e74c3c" opacity="0.6" font-size="8.5" text-anchor="start" font-family="sans-serif">100°</text>
          <text x="390" y="${(gridY2 + 3).toFixed(1)}" fill="#e74c3c" opacity="0.4" font-size="8" text-anchor="start" font-family="sans-serif">75°</text>
          <text x="390" y="131" fill="#e74c3c" opacity="0.3" font-size="8" text-anchor="start" font-family="sans-serif">60°</text>

          <!-- X Axis Ticks and Labels -->
          ${xTicks.map((t) => {
            const tx = calcX(t);
            return `
              <line x1="${tx.toFixed(1)}" y1="128" x2="${tx.toFixed(1)}" y2="132" stroke="rgba(255,255,255,0.15)" stroke-width="1" />
              <text x="${tx.toFixed(1)}" y="142" fill="rgba(255,255,255,0.4)" font-size="8" text-anchor="middle" font-family="sans-serif">${t}s</text>
            `;
          }).join("")}

          <!-- Yield Area Fill -->
          <path d="${yieldAreaPath}" fill="url(#yieldGrad)" />

          <!-- Temperature Curve (Red) -->
          ${tempPath ? `<path d="${tempPath}" fill="none" stroke="#e74c3c" stroke-width="1.6" stroke-dasharray="3 2" opacity="0.85" />` : ""}

          <!-- Flow Rate Curve (Blue) -->
          ${flowPath ? `<path d="${flowPath}" fill="none" stroke="#3498db" stroke-width="1.8" opacity="0.85" filter="url(#flowGlow)" />` : ""}

          <!-- Yield Curve (Amber / Gold) -->
          <path d="${yieldPath}" fill="none" stroke="#e67e22" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />

          <!-- Live Head Pulsing Dot -->
          ${isBrewing && lastPt ? `
            <circle cx="${lastPt.x.toFixed(1)}" cy="${lastPt.y.toFixed(1)}" r="7" fill="#e67e22" opacity="0.3" class="pulse-head" />
            <circle cx="${lastPt.x.toFixed(1)}" cy="${lastPt.y.toFixed(1)}" r="4" fill="#ffffff" stroke="#e67e22" stroke-width="2" />
          ` : ""}

          <!-- Interactive Elements -->
          <line class="curve-crosshair" y1="15" y2="128" x1="0" x2="0" style="display: none;" />
          <circle class="dot-yield" r="4" fill="#e67e22" stroke="#fff" stroke-width="1.5" style="display: none;" />
          <circle class="dot-flow" r="3.5" fill="#3498db" stroke="#fff" stroke-width="1.5" style="display: none;" />
          <circle class="dot-temp" r="3.5" fill="#e74c3c" stroke="#fff" stroke-width="1.5" style="display: none;" />
        </svg>
      </div>
    `;
  }

  _setupChartInteraction(container, profile, maxT, maxOutput, maxFlow) {
    if (!container || !profile || profile.length < 2) return;
    const svg = container.querySelector(".chart-svg");
    const crosshair = container.querySelector(".curve-crosshair");
    const tooltip = container.querySelector(".curve-tooltip");
    const dotYield = container.querySelector(".dot-yield");
    const dotFlow = container.querySelector(".dot-flow");
    const dotTemp = container.querySelector(".dot-temp");
    if (!svg || !crosshair || !tooltip) return;

    const onPointerMove = (e) => {
      const rect = svg.getBoundingClientRect();
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const relX = clientX - rect.left;
      const svgX = (relX / rect.width) * 420;

      const clampedX = Math.max(35, Math.min(385, svgX));
      const targetT = ((clampedX - 35) / 350) * maxT;

      let closest = profile[0];
      let minDiff = Math.abs(closest.t - targetT);
      for (let i = 1; i < profile.length; i++) {
        const diff = Math.abs(profile[i].t - targetT);
        if (diff < minDiff) {
          minDiff = diff;
          closest = profile[i];
        }
      }

      const ptX = 35 + (closest.t / maxT) * 350;
      const ptYYield = 128 - ((Math.max(closest.water || 0, closest.mass || 0) / maxOutput) * 113);
      const ptYFlow = 128 - (((closest.flow || 0) / maxFlow) * 113);
      const ptYTemp = closest.temp > 0 ? 128 - (((Math.min(100, Math.max(60, closest.temp)) - 60) / 40) * 113) : 128;

      crosshair.setAttribute("x1", ptX.toFixed(1));
      crosshair.setAttribute("x2", ptX.toFixed(1));
      crosshair.style.display = "block";

      if (dotYield) {
        dotYield.setAttribute("cx", ptX.toFixed(1));
        dotYield.setAttribute("cy", ptYYield.toFixed(1));
        dotYield.style.display = "block";
      }
      if (dotFlow) {
        dotFlow.setAttribute("cx", ptX.toFixed(1));
        dotFlow.setAttribute("cy", ptYFlow.toFixed(1));
        dotFlow.style.display = "block";
      }
      if (dotTemp) {
        dotTemp.setAttribute("cx", ptX.toFixed(1));
        dotTemp.setAttribute("cy", ptYTemp.toFixed(1));
        dotTemp.style.display = "block";
      }

      tooltip.innerHTML = `
        <span style="color: #aaa; margin-right: 4px;">${closest.t.toFixed(1)}s:</span>
        <span style="color: #e67e22; font-weight: 600;">${(closest.mass || closest.water || 0).toFixed(1)}g</span>
        <span style="color: #666; margin: 0 3px;">|</span>
        <span style="color: #3498db;">${(closest.flow || 0).toFixed(1)} ml/s</span>
        ${closest.temp > 0 ? `<span style="color: #666; margin: 0 3px;">|</span><span style="color: #e74c3c;">${closest.temp}°C</span>` : ""}
      `;
      const tipLeftPct = (ptX / 420) * 100;
      tooltip.style.left = `${Math.max(15, Math.min(85, tipLeftPct))}%`;
      tooltip.style.display = "block";
    };

    const onPointerLeave = () => {
      crosshair.style.display = "none";
      tooltip.style.display = "none";
      if (dotYield) dotYield.style.display = "none";
      if (dotFlow) dotFlow.style.display = "none";
      if (dotTemp) dotTemp.style.display = "none";
    };

    svg.addEventListener("mousemove", onPointerMove);
    svg.addEventListener("touchmove", onPointerMove, { passive: true });
    svg.addEventListener("mouseleave", onPointerLeave);
    svg.addEventListener("touchend", onPointerLeave);
  }

  _openMoreInfo(entityId, sourceNode = null) {
    if (!entityId || !this._hass) return;

    const targets = [sourceNode, this, window];
    try {
      const ha = document.querySelector("home-assistant");
      if (ha && !targets.includes(ha)) targets.push(ha);
    } catch (_) {}

    for (const target of targets) {
      if (target && typeof target.dispatchEvent === "function") {
        try {
          // 1. Standard Home Assistant more-info event
          target.dispatchEvent(
            new CustomEvent("hass-more-info", {
              bubbles: true,
              cancelable: true,
              composed: true,
              detail: { entityId },
            })
          );
          // 2. Modern Lovelace action event
          target.dispatchEvent(
            new CustomEvent("hass-action", {
              bubbles: true,
              cancelable: true,
              composed: true,
              detail: {
                config: {
                  entity: entityId,
                  tap_action: {
                    action: "more-info",
                  },
                },
                action: "tap",
              },
            })
          );
        } catch (_) {}
      }
    }
  }

  getCardSize() {
    return 4;
  }
}

// Visual Card Configuration Editor (with focus preservation and selectable status items)
class MorningCoffeeCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._isRendered = false;
  }

  setConfig(config) {
    this._config = {
      show_header: true,
      show_brew_section: true,
      show_brew_controls: true,
      show_water_gauge: true,
      show_diagnostics: true,
      status_items: [...DEFAULT_STATUS_ITEMS],
      ...config,
    };
    if (!this._isRendered) {
      this._render();
    } else {
      this._updateFieldValues();
    }
  }

  get hass() {
    return this._hass;
  }

  set hass(hass) {
    const wasRendered = this._isRendered;
    this._hass = hass;
    if (!wasRendered) {
      this._render();
    } else {
      this._updateEntityOptions();
    }
  }

  _render() {
    if (!this._hass) return;

    this.shadowRoot.innerHTML = `
      <style>
        .editor {
          display: flex;
          flex-direction: column;
          gap: 14px;
          padding: 8px 0;
          font-family: var(--paper-font-body1_-_font-family, sans-serif);
          color: var(--primary-text-color, #ffffff);
        }
        .section-title {
          font-size: 0.82rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--secondary-text-color, #888);
          border-bottom: 1px solid var(--divider-color, rgba(255, 255, 255, 0.1));
          padding-bottom: 4px;
          margin-top: 6px;
        }
        .row {
          display: flex;
          flex-direction: column;
        }
        label {
          font-size: 0.84rem;
          font-weight: 500;
          margin-bottom: 4px;
        }
        select, input[type="text"] {
          padding: 8px 10px;
          border-radius: 6px;
          border: 1px solid var(--divider-color, #444);
          background: var(--input-background-color, rgba(255,255,255,0.05));
          color: var(--primary-text-color, #fff);
          font-size: 0.9rem;
          box-sizing: border-box;
          width: 100%;
        }
        select:focus, input[type="text"]:focus {
          border-color: var(--primary-color, #e67e22);
          outline: none;
        }
        .checkbox-group {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .checkbox-row {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .checkbox-row label {
          margin-bottom: 0;
          cursor: pointer;
          font-size: 0.85rem;
        }
        .status-items-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 8px;
          padding: 10px;
        }
      </style>
      <div class="editor">
        <div class="section-title">Machine Entity</div>
        <div class="row">
          <label for="entity-select">Machine Status Entity (Required)</label>
          <select id="entity-select"></select>
        </div>

        <div class="row">
          <label for="name-input">Custom Card Title (Optional)</label>
          <input type="text" id="name-input" placeholder="e.g. Kitchen Morning Machine" />
        </div>

        <div class="section-title">Display Sections</div>
        <div class="checkbox-group">
          <div class="checkbox-row">
            <input type="checkbox" id="show-header" />
            <label for="show-header">Display Header (Title, Logo & Badges)</label>
          </div>
          <div class="checkbox-row">
            <input type="checkbox" id="show-brew" />
            <label for="show-brew">Display Brewing / Extraction Monitor</label>
          </div>
          <div class="checkbox-row">
            <input type="checkbox" id="show-controls" />
            <label for="show-controls">Display Brew Initiation & Controls</label>
          </div>
          <div class="checkbox-row">
            <input type="checkbox" id="show-curve" />
            <label for="show-curve">Display Extraction Curve (Live & Last Shot)</label>
          </div>
          <div class="checkbox-row">
            <input type="checkbox" id="show-gauge" />
            <label for="show-gauge">Display Water Reservoir Gauge</label>
          </div>
          <div class="checkbox-row">
            <input type="checkbox" id="show-diag" />
            <label for="show-diag">Display Bottom Status Items</label>
          </div>
        </div>

        <div class="section-title">Status Items to Display</div>
        <div class="status-items-grid" id="status-items-container">
          ${AVAILABLE_STATUS_ITEMS.map(
            (item) => `
            <div class="checkbox-row">
              <input type="checkbox" id="stat-${item.id}" data-stat-id="${item.id}" />
              <label for="stat-${item.id}">${item.label}</label>
            </div>
          `
          ).join("")}
        </div>
      </div>
    `;

    this._updateEntityOptions();
    this._attachEventListeners();
    this._isRendered = true;
    this._updateFieldValues();
  }

  _updateEntityOptions() {
    if (!this._hass || !this._hass.states) return;
    const select = this.shadowRoot.getElementById("entity-select");
    if (!select) return;

    const currentVal = (this._config && this._config.entity) || select.value;
    const statusEntities = Object.keys(this._hass.states).filter(
      (e) => e.startsWith("sensor.") && (e.endsWith("_status") || e.includes("morning"))
    );

    let html = `<option value="">Select a status entity...</option>`;
    statusEntities.forEach((e) => {
      const friendly = this._hass.states[e]?.attributes?.friendly_name || e;
      html += `<option value="${e}" ${currentVal === e ? "selected" : ""}>${e} (${friendly})</option>`;
    });
    select.innerHTML = html;
  }

  _attachEventListeners() {
    const select = this.shadowRoot.getElementById("entity-select");
    if (select) {
      select.addEventListener("change", (e) => this._valueChanged("entity", e.target.value));
    }

    const nameInput = this.shadowRoot.getElementById("name-input");
    if (nameInput) {
      nameInput.addEventListener("input", (e) => this._valueChanged("name", e.target.value));
    }

    const bindCheckbox = (id, key) => {
      const el = this.shadowRoot.getElementById(id);
      if (el) {
        el.addEventListener("change", (e) => this._valueChanged(key, e.target.checked));
      }
    };

    bindCheckbox("show-header", "show_header");
    bindCheckbox("show-brew", "show_brew_section");
    bindCheckbox("show-controls", "show_brew_controls");
    bindCheckbox("show-curve", "show_extraction_curve");
    bindCheckbox("show-gauge", "show_water_gauge");
    bindCheckbox("show-diag", "show_diagnostics");

    AVAILABLE_STATUS_ITEMS.forEach((item) => {
      const cb = this.shadowRoot.getElementById(`stat-${item.id}`);
      if (cb) {
        cb.addEventListener("change", (e) => this._statusItemToggled(item.id, e.target.checked));
      }
    });
  }

  _updateFieldValues() {
    if (!this._isRendered) return;
    const active = this.shadowRoot.activeElement;

    const nameInput = this.shadowRoot.getElementById("name-input");
    if (nameInput && active !== nameInput) {
      nameInput.value = this._config.name || "";
    }

    const select = this.shadowRoot.getElementById("entity-select");
    if (select && active !== select && select.value !== this._config.entity) {
      select.value = this._config.entity || "";
    }

    const setChecked = (id, val) => {
      const el = this.shadowRoot.getElementById(id);
      if (el && active !== el) {
        el.checked = val !== false;
      }
    };

    setChecked("show-header", this._config.show_header !== false && this._config.show_title !== false);
    setChecked("show-brew", this._config.show_brew_section !== false);
    setChecked("show-controls", this._config.show_brew_controls !== false);
    setChecked("show-curve", this._config.show_extraction_curve !== false);
    setChecked("show-gauge", this._config.show_water_gauge !== false);
    setChecked("show-diag", this._config.show_diagnostics !== false);

    const activeStats = Array.isArray(this._config.status_items)
      ? this._config.status_items
      : DEFAULT_STATUS_ITEMS;

    AVAILABLE_STATUS_ITEMS.forEach((item) => {
      const cb = this.shadowRoot.getElementById(`stat-${item.id}`);
      if (cb && active !== cb) {
        cb.checked = activeStats.includes(item.id);
      }
    });
  }

  _statusItemToggled(itemId, checked) {
    let current = Array.isArray(this._config.status_items)
      ? [...this._config.status_items]
      : [...DEFAULT_STATUS_ITEMS];

    if (checked && !current.includes(itemId)) {
      current.push(itemId);
    } else if (!checked && current.includes(itemId)) {
      current = current.filter((id) => id !== itemId);
    }

    this._valueChanged("status_items", current);
  }

  _valueChanged(key, value) {
    if (!this._config) return;
    if (this._config[key] === value) return;
    this._config = { ...this._config, [key]: value };
    const event = new CustomEvent("config-changed", {
      detail: { config: this._config },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }
}

function registerOrHotPatch(tagName, cls) {
  const existing = customElements.get(tagName);
  if (!existing) {
    customElements.define(tagName, cls);
    return;
  }
  for (const name of Object.getOwnPropertyNames(cls.prototype)) {
    if (name === "constructor") continue;
    const desc = Object.getOwnPropertyDescriptor(cls.prototype, name);
    if (desc) {
      Object.defineProperty(existing.prototype, name, desc);
    }
  }
  for (const name of Object.getOwnPropertyNames(cls)) {
    if (["length", "name", "prototype"].includes(name)) continue;
    const desc = Object.getOwnPropertyDescriptor(cls, name);
    if (desc) {
      Object.defineProperty(existing, name, desc);
    }
  }
}

registerOrHotPatch("morning-coffee-card", MorningCoffeeCard);
registerOrHotPatch("morning-coffee-card-editor", MorningCoffeeCardEditor);

// Force active elements in page to immediately update prototype and re-render
try {
  document.querySelectorAll("morning-coffee-card").forEach((card) => {
    if (card._render) card._render();
    if (card._updateContent) card._updateContent();
  });
} catch (_) {}

try {
  window.dispatchEvent(new CustomEvent("ll-custom-elements-loaded"));
  window.dispatchEvent(new CustomEvent("ll-rebuild"));
} catch (_) {}

window.customCards = window.customCards || [];
const existingCardMeta = window.customCards.find((c) => c.type === "morning-coffee-card");
if (!existingCardMeta) {
  window.customCards.push({
    type: "morning-coffee-card",
    name: "Morning Coffee Machine Card",
    description: "Display Morning Machine telemetry, water level, and live brewing progress.",
    preview: true,
    documentationURL: "https://github.com/arcsur/ha-morning",
  });
}

console.info(
  `%c MORNING-COFFEE-CARD %c v${CARD_VERSION} `,
  "color: white; background: #e67e22; font-weight: 700;",
  "color: #e67e22; background: rgba(230, 126, 34, 0.1); font-weight: 700;"
);

export { MorningCoffeeCard, MorningCoffeeCardEditor, CARD_VERSION, STAGE_ORDER };

