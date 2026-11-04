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

  it("resets active brew steps when brew_stage is cancel or idle even if status sensor lags at brewing", () => {
    card.hass = { states: brewingStates };
    expect(card.shadowRoot.querySelectorAll(".step.active").length).toBe(1);

    // Simulate live IoT cancel arriving before 30s REST poll updates status sensor
    const laggedCancelStates = JSON.parse(JSON.stringify(brewingStates));
    laggedCancelStates["sensor.dagusmorning_status"].state = "brewing";
    laggedCancelStates["sensor.kitchen_dagusmorning_brew_stage"].state = "cancel";
    card.hass = { states: laggedCancelStates };

    expect(card.shadowRoot.querySelectorAll(".step.active").length).toBe(0);
    const badge = card.shadowRoot.querySelector(".extraction-badge");
    if (badge) {
      expect(badge.classList.contains("live")).toBe(false);
    }

    // Also verify when brew_stage settles to idle while status sensor still says brewing
    laggedCancelStates["sensor.kitchen_dagusmorning_brew_stage"].state = "idle";
    card.hass = { states: laggedCancelStates };
    expect(card.shadowRoot.querySelectorAll(".step.active").length).toBe(0);
  });

  it("activates live brew stages immediately when IoT brew_stage updates before 30s status poll", () => {
    // 1. Live IoT heating while status sensor still says eco
    const liveHeating = JSON.parse(JSON.stringify(idleStates));
    liveHeating["sensor.dagusmorning_status"].state = "eco";
    liveHeating["sensor.kitchen_dagusmorning_brew_stage"].state = "heating";
    card.hass = { states: liveHeating };

    let steps = card.shadowRoot.querySelectorAll(".step");
    expect(steps[0].classList.contains("active")).toBe(true);
    expect(steps[0].classList.contains("passed")).toBe(false);

    // 2. Live IoT blooming while status sensor still says eco
    const liveBlooming = JSON.parse(JSON.stringify(brewingStates));
    liveBlooming["sensor.dagusmorning_status"].state = "eco";
    liveBlooming["sensor.kitchen_dagusmorning_brew_stage"].state = "blooming";
    card.hass = { states: liveBlooming };

    steps = card.shadowRoot.querySelectorAll(".step");
    expect(steps[0].classList.contains("passed")).toBe(true);
    expect(steps[1].classList.contains("active")).toBe(true);

    // 3. Live IoT brewing while status sensor still says ready
    const liveBrewing = JSON.parse(JSON.stringify(brewingStates));
    liveBrewing["sensor.dagusmorning_status"].state = "ready";
    liveBrewing["sensor.kitchen_dagusmorning_brew_stage"].state = "brewing";
    card.hass = { states: liveBrewing };

    steps = card.shadowRoot.querySelectorAll(".step");
    expect(steps[0].classList.contains("passed")).toBe(true);
    expect(steps[1].classList.contains("passed")).toBe(true);
    expect(steps[2].classList.contains("active")).toBe(true);
    const badge = card.shadowRoot.querySelector(".extraction-badge");
    expect(badge.classList.contains("live")).toBe(true);
  });
});
