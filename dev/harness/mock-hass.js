/**
 * Mock Home Assistant Environment & State Controller for Card Harness
 */

import {
  idleStates,
  heatingStates,
  brewingStates,
  doneStates,
  cancelStates,
} from "./states-bundle.js";

export class MockHassManager {
  constructor(cardElement, onEventLogged = null) {
    this.card = cardElement;
    this.onEventLogged = onEventLogged;
    this.states = JSON.parse(JSON.stringify(idleStates));
    this.history = [];
    this._playbackTimer = null;

    this.hass = {
      states: this.states,
      callService: (domain, service, data) => {
        this.logEvent(`callService: ${domain}.${service}`, data);
      },
      callWS: (msg) => {
        this.logEvent(`callWS: ${msg.type}`, msg);
        if (msg.service === "search_recipes") {
          return Promise.resolve({
            response: {
              recipes: [
                {
                  id: "cloud-101",
                  name: `${msg.service_data?.query || "Specialty"} Gesha Lot 1`,
                  roaster_name: "Morning Curated",
                  temperature: 94,
                  mass_output: 38,
                  bloom_enabled: true,
                  bloom_duration: 12,
                  stages: [
                    { id: 0, output: 0, pressure: 2 },
                    { id: 1, output: 6, pressure: 7 },
                    { id: 2, output: 30, pressure: 5 },
                  ],
                },
                {
                  id: "cloud-102",
                  name: `${msg.service_data?.query || "Natural"} Anaerobic Filter`,
                  roaster_name: "Sey Coffee",
                  temperature: 92,
                  mass_output: 45,
                  bloom_enabled: true,
                  bloom_duration: 15,
                  stages: [
                    { id: 0, output: 0, pressure: 3 },
                    { id: 1, output: 8, pressure: 6 },
                    { id: 2, output: 35, pressure: 5 },
                  ],
                },
              ],
            },
          });
        }
        return Promise.resolve();
      },
    };

    // Intercept Lovelace / HA custom events from card
    window.addEventListener("hass-more-info", (e) => {
      this.logEvent("event: hass-more-info", e.detail);
    });
    window.addEventListener("hass-action", (e) => {
      this.logEvent("event: hass-action", e.detail);
    });
  }

  logEvent(name, payload) {
    const entry = {
      timestamp: new Date().toLocaleTimeString(),
      name,
      payload,
    };
    if (this.onEventLogged) {
      this.onEventLogged(entry);
    }
  }

  applyStates(newStates) {
    this.states = JSON.parse(JSON.stringify(newStates));
    this.hass.states = this.states;
    this.card.hass = this.hass;
  }

  setPreset(presetName) {
    this.stopPlayback();
    switch (presetName) {
      case "idle":
        this.applyStates(idleStates);
        break;
      case "heating":
        this.applyStates(heatingStates);
        break;
      case "blooming": {
        const s = JSON.parse(JSON.stringify(brewingStates));
        s["sensor.kitchen_dagusmorning_brew_stage"].state = "blooming";
        s["sensor.dagusmorning_status"].state = "brewing";
        s["sensor.kitchen_dagusmorning_brew_water_dispensed"].state = "15.0";
        s["sensor.kitchen_dagusmorning_brew_mass_dispensed"].state = "12.0";
        s["sensor.kitchen_dagusmorning_brew_bloom_duration"].state = "8";
        s["sensor.kitchen_dagusmorning_brew_stage"].attributes.extraction_profile = [
          { t: 0.0, water: 0.0, mass: 0.0, temp: 92, flow: 0.0 },
          { t: 2.0, water: 15.0, mass: 12.0, temp: 93, flow: 7.5 },
        ];
        this.applyStates(s);
        break;
      }
      case "brewing":
        this.applyStates(brewingStates);
        break;
      case "physical_no_bloom": {
        const s = JSON.parse(JSON.stringify(brewingStates));
        s["sensor.dagusmorning_status"].state = "brewing";
        s["sensor.kitchen_dagusmorning_brew_stage"].state = "brewing";
        s["sensor.kitchen_dagusmorning_brew_bloom_duration"].state = "0";
        s["sensor.kitchen_dagusmorning_brew_stage"].attributes.stages_seen = ["heating", "brewing"];
        s["sensor.kitchen_dagusmorning_brew_stage"].attributes.telemetry_source = "shadow";
        s["sensor.kitchen_dagusmorning_brew_stage"].attributes.extraction_profile = [
          { t: 0.0, water: 0.0, mass: 0.0, temp: 93, flow: 0.0, stage: "brewing" },
          { t: 4.0, water: 11.0, mass: 11.0, temp: 93, flow: 2.8, stage: "brewing" },
          { t: 10.0, water: 27.5, mass: 27.5, temp: 93, flow: 2.8, stage: "brewing" },
        ];
        this.applyStates(s);
        break;
      }
      case "done":
        this.applyStates(doneStates);
        break;
      case "cancel":
        this.applyStates(cancelStates);
        break;
      case "purge": {
        const s = JSON.parse(JSON.stringify(idleStates));
        s["sensor.dagusmorning_status"].state = "purge";
        s["sensor.kitchen_dagusmorning_brew_stage"].state = "purge";
        this.applyStates(s);
        break;
      }
      case "water_low": {
        const s = JSON.parse(JSON.stringify(idleStates));
        s["sensor.dagusmorning_status"].state = "water";
        s["sensor.kitchen_dagusmorning_water_tank_level"].state = "0.0";
        s["sensor.kitchen_dagusmorning_water_tank_percentage"].state = "0.0";
        this.applyStates(s);
        break;
      }
      case "empty_boot":
        this.applyStates({});
        break;
      default:
        console.warn("Unknown preset:", presetName);
    }
  }

  updateMetric(key, value) {
    if (!this.states) return;
    const s = this.states;
    if (key === "temp" && s["sensor.kitchen_dagusmorning_brew_temperature"]) {
      s["sensor.kitchen_dagusmorning_brew_temperature"].state = String(value);
    } else if (key === "water" && s["sensor.kitchen_dagusmorning_brew_water_dispensed"]) {
      s["sensor.kitchen_dagusmorning_brew_water_dispensed"].state = Number(value).toFixed(1);
    } else if (key === "mass" && s["sensor.kitchen_dagusmorning_brew_mass_dispensed"]) {
      s["sensor.kitchen_dagusmorning_brew_mass_dispensed"].state = Number(value).toFixed(1);
    } else if (key === "tank" && s["sensor.kitchen_dagusmorning_water_tank_level"]) {
      s["sensor.kitchen_dagusmorning_water_tank_level"].state = Number(value).toFixed(1);
      const pct = Math.round((Number(value) / 850) * 100);
      s["sensor.kitchen_dagusmorning_water_tank_percentage"].state = String(pct);
    } else if (key === "bloom" && s["sensor.kitchen_dagusmorning_brew_bloom_duration"]) {
      s["sensor.kitchen_dagusmorning_brew_bloom_duration"].state = String(value);
    }
    this.hass.states = this.states;
    this.card.hass = this.hass;
  }

  startPlayback(speed = 1.0, onProgress = null) {
    this.stopPlayback();
    this.setPreset("heating");

    let t = 0;
    let water = 0;
    let mass = 0;
    const profile = [];

    const intervalMs = Math.round(500 / speed);

    this._playbackTimer = setInterval(() => {
      t += 0.5;

      if (t < 3) {
        // Heating phase
        this.updateMetric("temp", Math.min(93, 80 + Math.round(t * 4)));
        if (onProgress) onProgress({ phase: "Heating", t, water, mass });
      } else if (t < 8) {
        // Blooming phase
        if (this.states["sensor.kitchen_dagusmorning_brew_stage"].state !== "blooming") {
          this.states["sensor.kitchen_dagusmorning_brew_stage"].state = "blooming";
          this.states["sensor.dagusmorning_status"].state = "brewing";
        }
        water = Math.min(20, (t - 3) * 4);
        mass = water * 0.8;
        this.updateMetric("water", water);
        this.updateMetric("mass", mass);
        this.updateMetric("bloom", Math.round(t - 3));
        profile.push({
          t: Number(t.toFixed(1)),
          water: Number(water.toFixed(1)),
          mass: Number(mass.toFixed(1)),
          temp: 93,
          flow: 4.0,
        });
        this.states["sensor.kitchen_dagusmorning_brew_stage"].attributes.extraction_profile = profile;
        this.card.hass = this.hass;
        if (onProgress) onProgress({ phase: "Blooming", t, water, mass });
      } else if (t < 20) {
        // Brewing / Extraction phase
        if (this.states["sensor.kitchen_dagusmorning_brew_stage"].state !== "brewing") {
          this.states["sensor.kitchen_dagusmorning_brew_stage"].state = "brewing";
        }
        water = 20 + (t - 8) * 5.0;
        mass = 16 + (t - 8) * 4.8;
        this.updateMetric("water", water);
        this.updateMetric("mass", mass);
        profile.push({
          t: Number(t.toFixed(1)),
          water: Number(water.toFixed(1)),
          mass: Number(mass.toFixed(1)),
          temp: 93 + (t % 2 === 0 ? 1 : 0),
          flow: 6.5,
        });
        this.states["sensor.kitchen_dagusmorning_brew_stage"].attributes.extraction_profile = profile;
        this.card.hass = this.hass;
        if (onProgress) onProgress({ phase: "Brewing", t, water, mass });
      } else {
        // Done phase
        this.stopPlayback();
        this.setPreset("done");
        if (onProgress) onProgress({ phase: "Done", t, water: 80, mass: 73.6 });
      }
    }, intervalMs);
  }

  stopPlayback() {
    if (this._playbackTimer) {
      clearInterval(this._playbackTimer);
      this._playbackTimer = null;
    }
  }
}
