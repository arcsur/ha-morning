import { describe, it, expect, beforeEach } from "vitest";
import { MorningCoffeeCard } from "../../custom_components/morning/frontend/morning-coffee-card.js";
import idleStates from "../fixtures/states_idle.json";

describe("MorningCoffeeCard Entity Resolution & Startup", () => {
  let card;

  beforeEach(() => {
    card = document.createElement("morning-coffee-card");
    document.body.appendChild(card);
  });

  it("handles early startup with empty or undefined hass safely", () => {
    expect(() => {
      card.setConfig({ entity: "sensor.dagusmorning_status" });
      card.hass = undefined;
    }).not.toThrow();

    expect(() => {
      card.hass = {};
    }).not.toThrow();

    expect(() => {
      card.hass = { states: {} };
    }).not.toThrow();
  });

  it("resolves sibling entities from status sensor entity_id", () => {
    card.setConfig({ entity: "sensor.dagusmorning_status" });
    card.hass = { states: idleStates };

    expect(card._resolvedEntities.status).toBe("sensor.dagusmorning_status");
    expect(card._resolvedEntities.water_level).toBe("sensor.kitchen_dagusmorning_water_tank_level");
    expect(card._resolvedEntities.water_pct).toBe("sensor.kitchen_dagusmorning_water_tank_percentage");
    expect(card._resolvedEntities.brew_water).toBe("sensor.kitchen_dagusmorning_brew_water_dispensed");
    expect(card._resolvedEntities.brew_mass).toBe("sensor.kitchen_dagusmorning_brew_mass_dispensed");
    expect(card._resolvedEntities.brew_temp).toBe("sensor.kitchen_dagusmorning_brew_temperature");
    expect(card._resolvedEntities.brew_stage).toBe("sensor.kitchen_dagusmorning_brew_stage");
    expect(card._resolvedEntities.brew_bloom).toBe("sensor.kitchen_dagusmorning_brew_bloom_duration");
    expect(card._resolvedEntities.total_brews).toBe("sensor.dagusmorning_total_brews");
    expect(card._resolvedEntities.lifetime_water).toBe("sensor.kitchen_dagusmorning_lifetime_water_used");
  });

  it("re-resolves when initially missing sibling entities appear later in hass", () => {
    card.setConfig({ entity: "sensor.dagusmorning_status" });
    // Partial states during early boot: only status exists
    card.hass = {
      states: {
        "sensor.dagusmorning_status": idleStates["sensor.dagusmorning_status"],
      },
    };

    expect(card._resolvedEntities.brew_water).toBeNull();

    // Sibling entities appear in subsequent update
    card.hass = { states: idleStates };
    expect(card._resolvedEntities.brew_water).toBe("sensor.kitchen_dagusmorning_brew_water_dispensed");
    expect(card._resolvedEntities.brew_temp).toBe("sensor.kitchen_dagusmorning_brew_temperature");
  });
});
