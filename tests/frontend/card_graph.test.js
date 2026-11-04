import { describe, it, expect, beforeEach } from "vitest";
import { MorningCoffeeCard } from "../../custom_components/morning/frontend/morning-coffee-card.js";
import brewingStates from "../fixtures/states_brewing.json";
import idleStates from "../fixtures/states_idle.json";

describe("MorningCoffeeCard SVG Extraction Graph", () => {
  let card;

  beforeEach(() => {
    card = document.createElement("morning-coffee-card");
    document.body.appendChild(card);
    card.setConfig({ entity: "sensor.dagusmorning_status" });
  });

  it("renders valid SVG curve without NaN or Infinity coordinates", () => {
    card.hass = { states: brewingStates };

    const shadow = card.shadowRoot;
    const svg = shadow.querySelector("svg.chart-svg");
    expect(svg).toBeDefined();
    expect(svg).not.toBeNull();

    const paths = svg.querySelectorAll("path");
    expect(paths.length).toBeGreaterThan(0);

    for (const path of paths) {
      const d = path.getAttribute("d");
      if (d) {
        expect(d).not.toContain("NaN");
        expect(d).not.toContain("Infinity");
        expect(d).not.toContain("undefined");
      }
    }
  });

  it("calculates accurate extraction summary stats chips", () => {
    card.hass = { states: brewingStates };

    const shadow = card.shadowRoot;
    const chips = Array.from(shadow.querySelectorAll(".stat-chip")).map((c) =>
      c.textContent.trim()
    );

    // Profile has: t: 8.0s, yield: 50.0g, peak flow: 7.5 ml/s, avg temp: 93°C
    expect(chips.some((c) => c.includes("8.0s"))).toBe(true);
    expect(chips.some((c) => c.includes("50.0g"))).toBe(true);
    expect(chips.some((c) => c.includes("7.5 ml/s"))).toBe(true);
    expect(chips.some((c) => c.includes("93°C"))).toBe(true);
  });

  it("handles empty extraction profile gracefully without crashing", () => {
    expect(() => {
      card.hass = { states: idleStates };
    }).not.toThrow();

    const shadow = card.shadowRoot;
    const svg = shadow.querySelector("svg.chart-svg");
    // In idle with empty profile, SVG placeholder is displayed instead of empty path
    if (svg) {
      const paths = svg.querySelectorAll("path");
      for (const path of paths) {
        const d = path.getAttribute("d");
        if (d) {
          expect(d).not.toContain("NaN");
        }
      }
    }
  });
});
