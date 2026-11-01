/**
 * Morning Coffee Machine Lovelace Card
 * Custom card displaying machine diagnostics, water level, and live brewing telemetry.
 */

const CARD_VERSION = "1.3.9";

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
      show_water_gauge: true,
      show_diagnostics: true,
      status_items: [...DEFAULT_STATUS_ITEMS],
      ...config,
    };
    this._resolvedEntities = {};
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;

    if (this._config.entity) {
      const needsResolve =
        Object.keys(this._resolvedEntities).length === 0 ||
        this._resolvedEntities.status !== this._config.entity ||
        !this._resolvedEntities.total_brews ||
        !this._resolvedEntities.water_level ||
        !this._resolvedEntities.lifetime_water;
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

        const entityId = el.getAttribute("data-entity-id");
        if (entityId) {
          e.stopPropagation();
          this._openMoreInfo(entityId, el);
          return;
        }
      }
    });
  }

  _resolveEntities() {
    if (!this._hass) return;
    const mainEntity = this._config.entity;
    const states = this._hass.states;
    const explicit = this._config.entities || {};

    let slug = mainEntity.replace("sensor.", "").replace("_status", "");

    const findEntity = (typeKey, pattern, preferredDomain = null) => {
      if (explicit[typeKey] && states[explicit[typeKey]]) {
        return explicit[typeKey];
      }
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
    if (!this._hass || !this._resolvedEntities[key]) return null;
    return this._hass.states[this._resolvedEntities[key]];
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
    const root = this.shadowRoot.getElementById("card-root");
    if (!root) return;

    if (!this._config.entity) {
      root.innerHTML = `
        <div style="padding: 24px 16px; text-align: center; color: var(--secondary-text-color, #888);">
          <ha-icon icon="mdi:coffee-maker-outline" style="--mdc-icon-size: 36px; margin-bottom: 8px; display: inline-block; color: var(--primary-color, #e67e22);"></ha-icon>
          <div style="font-weight: 600; font-size: 0.95rem; color: var(--primary-text-color, #fff);">Morning Coffee Machine Card</div>
          <div style="font-size: 0.8rem; margin-top: 4px;">Please select an entity in the card editor.</div>
        </div>
      `;
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
    const rawWaterDisp = parseFloat(this._getValue("brew_water", "0.0") || "0.0");
    const waterDispensed = Number.isFinite(rawWaterDisp) ? rawWaterDisp : 0.0;
    const rawMassDisp = parseFloat(this._getValue("brew_mass", "0.0") || "0.0");
    const massDispensed = Number.isFinite(rawMassDisp) ? rawMassDisp : 0.0;
    const brewTemp = this._getValue("brew_temp", "--");
    const bloomDuration = this._getValue("brew_bloom", "0");

    const stage = (this._getValue("brew_stage", "idle") || "idle").toLowerCase();
    const isPurge = stage === "purge" || rawStatus === "purge";
    const isBrewing = (rawStatus === "brewing" && stage !== "done")
      || (rawStatus === "purge")
      || (stage === "purge")
      || (stage === "brewing" || stage === "heating" || stage === "blooming");
    const displayStatus = (rawStatus === "brewing" && stage === "done")
      ? "done"
      : isPurge
      ? (isBrewing ? "purge" : "done")
      : rawStatus;

    const isPurgeCycle = isPurge || (stage === "done" && brewTemp === "--" && massDispensed === 0 && waterDispensed > 0);

    const statusColor = STATUS_COLORS[displayStatus] || "#888";
    const statusBg = `${statusColor}22`;

    let currentStepIndex = STAGE_ORDER.indexOf(stage);
    if (currentStepIndex === -1) {
      currentStepIndex = isBrewing ? 2 : stage === "done" ? 3 : -1;
    }

    const heroClass = isBrewing ? "brew-hero brewing" : stage === "done" ? "brew-hero done" : "brew-hero";

    const brewWaterEnt = this._resolvedEntities.brew_water;
    const brewMassEnt = this._resolvedEntities.brew_mass;
    const brewTempEnt = this._resolvedEntities.brew_temp;
    const brewBloomEnt = this._resolvedEntities.brew_bloom;
    const waterLevelEnt = this._resolvedEntities.water_level;

    let html = "";

    // 1. Header & Title Section
    const showHeader = this._config.show_header !== false && this._config.show_title !== false;
    if (showHeader) {
      html += `
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
    const showBrewSection = this._config.show_brew_section !== false;
    if (showBrewSection) {
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
              const isPassed = currentStepIndex > idx || (!isBrewing && stage === "done");
              const isActive = currentStepIndex === idx && isBrewing;
              const cls = isActive ? "step active" : isPassed ? "step passed" : "step";
              return `
                <div class="${cls}">
                  <div class="step-circle">${isPassed ? "✓" : idx + 1}</div>
                  <div class="step-label">${stepName}</div>
                </div>
              `;
            }).join("")}
          </div>
        `;

      html += `
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
        </div>
      `;
    }

    // 3. Water Reservoir Section
    const showWaterGauge = this._config.show_water_gauge !== false;
    if (showWaterGauge) {
      const isLow = waterLevelPct <= 15;
      const barClass = isLow ? "progress-bar low" : "progress-bar";
      html += `
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
              <button class="action-btn purge-btn" id="purge-action" title="Record Purge Rinse">
                <ha-icon icon="mdi:water-sync"></ha-icon>
                <span>Purge</span>
              </button>
              <button class="action-btn refill-btn" id="refill-action" title="Refill Reservoir">
                <ha-icon icon="mdi:water-plus"></ha-icon>
                <span>Refill</span>
              </button>
            </div>
          </div>
        </div>
      `;
    }

    // 4. Selectable Diagnostics Bar
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
        html += `<div class="diag-grid">${itemsHtml}</div>`;
      }
    }

    root.innerHTML = html;
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
