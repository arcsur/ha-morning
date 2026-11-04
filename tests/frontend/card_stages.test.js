import { describe, it, expect, beforeEach } from "vitest";
import { MorningCoffeeCard } from "../../custom_components/morning/frontend/morning-coffee-card.js";
import idleStates from "../fixtures/states_idle.json";
import heatingStates from "../fixtures/states_heating.json";
import brewingStates from "../fixtures/states_brewing.json";
import doneStates from "../fixtures/states_done.json";
import cancelStates from "../fixtures/states_cancel.json";

describe("MorningCoffeeCard Stage Progression & Transitions", () => {
  let card;

  beforeEach(() => {
    card = document.createElement("morning-coffee-card");
    document.body.appendChild(card);
    card.setConfig({ entity: "sensor.dagusmorning_status" });
  });

  it("activates Heating stage (step 0) and does not skip to blooming when status is heating", () => {
    card.hass = { states: heatingStates };

    const shadow = card.shadowRoot;
    const steps = shadow.querySelectorAll(".step");
    expect(steps.length).toBe(4); // Heating, Blooming, Brewing, Done

    // Heating step (index 0) must be active
    expect(steps[0].classList.contains("active")).toBe(true);
    // Heating step must NOT be marked passed with a checkmark
    expect(steps[0].querySelector(".step-circle").textContent.trim()).toBe("1");

    // Blooming (index 1) and Brewing (index 2) must NOT be active or passed
    expect(steps[1].classList.contains("active")).toBe(false);
    expect(steps[1].classList.contains("passed")).toBe(false);
    expect(steps[2].classList.contains("active")).toBe(false);
    expect(steps[2].classList.contains("passed")).toBe(false);
  });

  it("advances through Blooming to Brewing with passed checkmarks", () => {
    // Blooming state
    const bloomingStates = JSON.parse(JSON.stringify(brewingStates));
    bloomingStates["sensor.kitchen_dagusmorning_brew_stage"].state = "blooming";
    bloomingStates["sensor.dagusmorning_status"].state = "brewing";
    card.hass = { states: bloomingStates };

    let steps = card.shadowRoot.querySelectorAll(".step");
    // Heating passed
    expect(steps[0].classList.contains("passed")).toBe(true);
    expect(steps[0].querySelector(".step-circle").textContent.trim()).toBe("✓");
    // Blooming active
    expect(steps[1].classList.contains("active")).toBe(true);
    expect(steps[1].querySelector(".step-circle").textContent.trim()).toBe("2");

    // Now advance to Brewing
    card.hass = { states: brewingStates };
    steps = card.shadowRoot.querySelectorAll(".step");
    // Heating & Blooming passed
    expect(steps[0].classList.contains("passed")).toBe(true);
    expect(steps[1].classList.contains("passed")).toBe(true);
    // Brewing active
    expect(steps[2].classList.contains("active")).toBe(true);
  });

  it("marks all steps passed on Done state", () => {
    card.hass = { states: doneStates };

    const steps = card.shadowRoot.querySelectorAll(".step");
    expect(steps[0].classList.contains("passed")).toBe(true);
    expect(steps[1].classList.contains("passed")).toBe(true);
    expect(steps[2].classList.contains("passed")).toBe(true);
    expect(steps[3].classList.contains("passed")).toBe(true);
  });

  it("resets active brew steps cleanly when brew is canceled", () => {
    // First simulate brewing
    card.hass = { states: brewingStates };
    let steps = card.shadowRoot.querySelectorAll(".step");
    expect(steps[2].classList.contains("active")).toBe(true);

    // Cancel brew
    card.hass = { states: cancelStates };
    steps = card.shadowRoot.querySelectorAll(".step");

    // No step should be stuck in active
    const activeSteps = card.shadowRoot.querySelectorAll(".step.active");
    expect(activeSteps.length).toBe(0);

    // Brewing indicator badge should be Profile/Completed not Live
    const badge = card.shadowRoot.querySelector(".extraction-badge");
    if (badge) {
      expect(badge.classList.contains("live")).toBe(false);
    }
  });
});
