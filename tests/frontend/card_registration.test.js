import { describe, it, expect, beforeEach } from "vitest";

describe("MorningCoffeeCard Registration", () => {
  it("registers custom element morning-coffee-card", async () => {
    await import("../../custom_components/morning/frontend/morning-coffee-card.js");
    const cardClass = customElements.get("morning-coffee-card");
    expect(cardClass).toBeDefined();

    const editorClass = customElements.get("morning-coffee-card-editor");
    expect(editorClass).toBeDefined();

    const card = document.createElement("morning-coffee-card");
    expect(card).toBeInstanceOf(cardClass);
  });
});
