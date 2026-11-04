import { describe, it, expect, beforeEach } from "vitest";
import { MorningCoffeeCard } from "../../custom_components/morning/frontend/morning-coffee-card.js";
import brewingStates from "../fixtures/states_brewing.json";
import doneStates from "../fixtures/states_done.json";

describe("MorningCoffeeCard Telemetry & Sticky Metrics", () => {
  let card;

  beforeEach(() => {
    card = document.createElement("morning-coffee-card");
    document.body.appendChild(card);
    card.setConfig({ entity: "sensor.dagusmorning_status" });
  });

  it("renders live telemetry metrics accurately during brew", () => {
    card.hass = { states: brewingStates };

    const shadow = card.shadowRoot;
    const metricValues = Array.from(shadow.querySelectorAll(".metric-value")).map((el) =>
      el.textContent.trim()
    );

    // Dispensed water: 50.0mL, mass: 45.0g, temp: 93°C, bloom: 12s
    expect(metricValues.some((v) => v.includes("50.0"))).toBe(true);
    expect(metricValues.some((v) => v.includes("45.0"))).toBe(true);
    expect(metricValues.some((v) => v.includes("93"))).toBe(true);
    expect(metricValues.some((v) => v.includes("12"))).toBe(true);
  });

  it("falls back to extraction profile latest point if sensor entities lag at 0", () => {
    // Construct lagged state where sensors say 0 but extraction profile has yield
    const laggedStates = JSON.parse(JSON.stringify(brewingStates));
    laggedStates["sensor.kitchen_dagusmorning_brew_water_dispensed"].state = "0.0";
    laggedStates["sensor.kitchen_dagusmorning_brew_mass_dispensed"].state = "0.0";
    laggedStates["sensor.kitchen_dagusmorning_brew_temperature"].state = "unknown";

    card.hass = { states: laggedStates };

    const shadow = card.shadowRoot;
    const metricValues = Array.from(shadow.querySelectorAll(".metric-value")).map((el) =>
      el.textContent.trim()
    );

    // Latest point in extraction_profile: water 50.0, mass 45.0, temp 93
    expect(metricValues.some((v) => v.includes("50"))).toBe(true);
    expect(metricValues.some((v) => v.includes("45"))).toBe(true);
    expect(metricValues.some((v) => v.includes("93"))).toBe(true);
  });

  it("retains sticky metrics after brew completes and machine returns to ready", () => {
    card.hass = { states: doneStates };

    const shadow = card.shadowRoot;
    const metricValues = Array.from(shadow.querySelectorAll(".metric-value")).map((el) =>
      el.textContent.trim()
    );

    // Sticky values must remain displayed, not reset to blank or dashes
    expect(metricValues.some((v) => v.includes("50.0"))).toBe(true);
    expect(metricValues.some((v) => v.includes("45.0"))).toBe(true);
    expect(metricValues.some((v) => v.includes("93"))).toBe(true);
  });
});
