import { describe, it, expect, beforeEach, vi } from "vitest";
import { MorningCoffeeCard } from "../../custom_components/morning/frontend/morning-coffee-card.js";
import idleStates from "../fixtures/states_idle.json";

describe("MorningCoffeeCard Shadow DOM Events", () => {
  let card;
  let mockHass;

  beforeEach(() => {
    card = document.createElement("morning-coffee-card");
    document.body.appendChild(card);
    card.setConfig({ entity: "sensor.dagusmorning_status" });
    mockHass = {
      states: idleStates,
      callService: vi.fn(),
    };
    card.hass = mockHass;
  });

  it("dispatches hass-more-info CustomEvent that crosses shadow DOM boundaries", () => {
    let firedEvent = null;
    window.addEventListener("hass-more-info", (e) => {
      firedEvent = e;
    });

    const target = card.shadowRoot.querySelector("[data-entity-id]");
    expect(target).toBeDefined();

    target.click();

    expect(firedEvent).not.toBeNull();
    expect(firedEvent.bubbles).toBe(true);
    expect(firedEvent.composed).toBe(true);
    expect(firedEvent.detail.entityId).toBe(target.getAttribute("data-entity-id"));
  });

  it("calls morning.record_purge service on purge action click", () => {
    const purgeBtn = card.shadowRoot.querySelector("#purge-action");
    expect(purgeBtn).toBeDefined();

    purgeBtn.click();

    expect(mockHass.callService).toHaveBeenCalledWith("morning", "record_purge", {});
  });
});
