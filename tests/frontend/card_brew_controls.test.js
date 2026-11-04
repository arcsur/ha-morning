import { describe, it, expect, beforeEach, vi } from "vitest";
import { MorningCoffeeCard } from "../../custom_components/morning/frontend/morning-coffee-card.js";
import idleStates from "../fixtures/states_idle.json";
import brewingStates from "../fixtures/states_brewing.json";

describe("MorningCoffeeCard Brew Initiation & Controls", () => {
  let card;
  let mockHass;

  const sampleCatalog = {
    quick: [
      {
        id: "quick-1",
        name: "Morning Glory",
        temperature: 94,
        mass_output: 38,
        bloom_enabled: true,
        bloom_duration: 12,
        stages: [
          { id: 0, output: 0, pressure: 3 },
          { id: 1, output: 6, pressure: 7 },
          { id: 2, output: 30, pressure: 5 },
        ],
      },
      {
        id: "quick-2",
        name: "Daily Driver",
        temperature: 92,
        mass_output: 45,
        bloom_enabled: false,
        bloom_duration: 0,
        stages: [
          { id: 0, output: 0, pressure: 2 },
          { id: 1, output: 10, pressure: 6 },
          { id: 2, output: 38, pressure: 6 },
        ],
      },
    ],
    favorites: [
      {
        id: "fav-1",
        name: "Ethiopia Yirgacheffe",
        roaster_name: "April Coffee",
        temperature: 93,
        mass_output: 40,
        bloom_enabled: true,
        bloom_duration: 15,
        is_favorite: true,
        stages: [
          { id: 0, output: 0, pressure: 2 },
          { id: 1, output: 8, pressure: 6 },
          { id: 2, output: 32, pressure: 5 },
        ],
      },
    ],
    recents: [
      {
        id: "rec-1",
        name: "Colombia Geisha",
        roaster_name: "Tim Wendelboe",
        temperature: 95,
        mass_output: 35,
        bloom_enabled: false,
        bloom_duration: 0,
        stages: [
          { id: 0, output: 0, pressure: 4 },
          { id: 1, output: 5, pressure: 7 },
          { id: 2, output: 28, pressure: 5 },
        ],
      },
    ],
    custom: [],
    machine: [],
  };

  beforeEach(() => {
    card = document.createElement("morning-coffee-card");
    document.body.appendChild(card);
    card.setConfig({
      entity: "sensor.dagusmorning_status",
      show_brew_controls: true,
    });

    const statesWithCatalog = JSON.parse(JSON.stringify(idleStates));
    statesWithCatalog["sensor.dagusmorning_status"].attributes.recipe_catalog = sampleCatalog;

    mockHass = {
      states: statesWithCatalog,
      callService: vi.fn(),
      callWS: vi.fn().mockResolvedValue({
        response: {
          recipes: [
            {
              id: "cloud-1",
              name: "Cloud Gesha Bloom",
              roaster_name: "Onyx Coffee Lab",
              temperature: 94,
              mass_output: 36,
              bloom_enabled: true,
              bloom_duration: 10,
              stages: [
                { id: 0, output: 0, pressure: 2 },
                { id: 1, output: 6, pressure: 7 },
                { id: 2, output: 28, pressure: 5 },
              ],
            },
          ],
        },
      }),
    };
    card.hass = mockHass;
  });

  it("renders quick chip scroll bar in idle state", () => {
    const controls = card.shadowRoot.querySelector(".brew-controls-section");
    expect(controls).not.toBeNull();

    const chips = card.shadowRoot.querySelectorAll(".quick-chip");
    expect(chips.length).toBe(2);
    expect(chips[0].textContent).toContain("Morning Glory");
    expect(chips[1].textContent).toContain("Daily Driver");

    const drawerBtn = card.shadowRoot.querySelector("#btn-toggle-drawer");
    expect(drawerBtn).not.toBeNull();
    expect(drawerBtn.textContent).toContain("Brew Controls");
  });

  it("clicking a quick chip opens confirmation bar and brew now triggers service", () => {
    const chip = card.shadowRoot.querySelector('.quick-chip[data-quick-chip-index="0"]');
    expect(chip).not.toBeNull();
    chip.click();

    const confirmBar = card.shadowRoot.querySelector(".confirm-bar");
    expect(confirmBar).not.toBeNull();
    expect(confirmBar.textContent).toContain("Morning Glory");
    expect(confirmBar.textContent).toContain("94°C");

    const brewNowBtn = card.shadowRoot.querySelector("#btn-confirm-brew-now");
    expect(brewNowBtn).not.toBeNull();
    brewNowBtn.click();

    expect(mockHass.callService).toHaveBeenCalledWith("morning", "brew_recipe", {
      entity_id: "sensor.dagusmorning_status",
      profile_id: "quick-1",
      name: "Morning Glory",
      temperature: 94,
      mass_output: 38,
      water_output: 0,
      bloom_duration: 12,
      stage1_pressure: 3,
      stage2_pressure: 7,
      stage3_pressure: 5,
      stage2_weight: 6,
      stage3_weight: 30,
    });

    expect(card.shadowRoot.querySelector(".confirm-bar")).toBeNull();
  });

  it("dismissing confirmation bar removes it", () => {
    const chip = card.shadowRoot.querySelector('.quick-chip[data-quick-chip-index="0"]');
    chip.click();
    expect(card.shadowRoot.querySelector(".confirm-bar")).not.toBeNull();

    const dismissBtn = card.shadowRoot.querySelector("#btn-confirm-dismiss");
    expect(dismissBtn).not.toBeNull();
    dismissBtn.click();

    expect(card.shadowRoot.querySelector(".confirm-bar")).toBeNull();
  });

  it("toggles the brew drawer and switches tabs", () => {
    const drawerBtn = card.shadowRoot.querySelector("#btn-toggle-drawer");
    expect(card.shadowRoot.querySelector(".brew-drawer")).toBeNull();

    drawerBtn.click();
    const drawer = card.shadowRoot.querySelector(".brew-drawer");
    expect(drawer).not.toBeNull();

    // Default tab is 'saved'
    expect(card.shadowRoot.querySelector('.tab-btn[data-tab="saved"].active')).not.toBeNull();
    expect(card.shadowRoot.querySelector(".saved-subtabs")).not.toBeNull();

    // Switch to Search tab
    const searchTab = card.shadowRoot.querySelector('.tab-btn[data-tab="search"]');
    searchTab.click();
    expect(card.shadowRoot.querySelector("#search-input")).not.toBeNull();
    expect(card.shadowRoot.querySelector("#btn-submit-search")).not.toBeNull();

    // Switch to Studio tab
    const studioTab = card.shadowRoot.querySelector('.tab-btn[data-tab="studio"]');
    studioTab.click();
    expect(card.shadowRoot.querySelector(".studio-svg")).not.toBeNull();
    expect(card.shadowRoot.querySelectorAll(".studio-handle").length).toBe(3);
  });

  it("switches presets in Curve Studio and updates SVG & draft values", () => {
    const drawerBtn = card.shadowRoot.querySelector("#btn-toggle-drawer");
    drawerBtn.click();
    const studioTab = card.shadowRoot.querySelector('.tab-btn[data-tab="studio"]');
    studioTab.click();

    // Select Short preset
    const shortPreset = card.shadowRoot.querySelector('.preset-btn[data-preset="short"]');
    expect(shortPreset).not.toBeNull();
    shortPreset.click();

    expect(card._draftCurve.mass_output).toBe(25);
    expect(card._draftCurve.temperature).toBe(93);

    // Select Slow & Steady preset
    const slowPreset = card.shadowRoot.querySelector('.preset-btn[data-preset="slow"]');
    slowPreset.click();
    expect(card._draftCurve.mass_output).toBe(40);
    expect(card._draftCurve.temperature).toBe(94);
    expect(card._draftCurve.bloom_enabled).toBe(true);

    // Click Stepper to increment temperature
    const tempPlus = card.shadowRoot.querySelector('.step-ctrl-btn[data-param="temp"][data-step="1"]');
    tempPlus.click();
    expect(card._draftCurve.temperature).toBe(95);

    // Click Stepper to increment mass output by 5g
    const massPlus = card.shadowRoot.querySelector('.step-ctrl-btn[data-param="mass"][data-step="5"]');
    massPlus.click();
    expect(card._draftCurve.mass_output).toBe(45);
  });

  it("initiates brew directly from Curve Studio Brew Now button", () => {
    const drawerBtn = card.shadowRoot.querySelector("#btn-toggle-drawer");
    drawerBtn.click();
    const studioTab = card.shadowRoot.querySelector('.tab-btn[data-tab="studio"]');
    studioTab.click();

    const brewNowBtn = card.shadowRoot.querySelector("#btn-studio-brew");
    expect(brewNowBtn).not.toBeNull();
    brewNowBtn.click();

    expect(mockHass.callService).toHaveBeenCalledWith("morning", "brew_recipe", expect.objectContaining({
      entity_id: "sensor.dagusmorning_status",
      mass_output: 40,
      temperature: 94,
    }));
  });

  it("searches recipes in Cloud Search tab and brews from search result", async () => {
    const drawerBtn = card.shadowRoot.querySelector("#btn-toggle-drawer");
    drawerBtn.click();
    const searchTab = card.shadowRoot.querySelector('.tab-btn[data-tab="search"]');
    searchTab.click();

    const searchInput = card.shadowRoot.querySelector("#search-input");
    const searchBtn = card.shadowRoot.querySelector("#btn-submit-search");

    searchInput.value = "Onyx";
    card._searchQuery = "Onyx";
    searchBtn.click();

    // Wait for search promise to resolve
    await new Promise((r) => setTimeout(r, 10));

    expect(mockHass.callWS).toHaveBeenCalledWith(expect.objectContaining({
      domain: "morning",
      service: "search_recipes",
      service_data: { query: "Onyx" },
    }));

    const resultCards = card.shadowRoot.querySelectorAll(".profile-card");
    expect(resultCards.length).toBe(1);
    expect(resultCards[0].textContent).toContain("Cloud Gesha Bloom");
    expect(resultCards[0].textContent).toContain("Onyx Coffee Lab");

    const brewBtn = resultCards[0].querySelector('[data-action="brew-profile"]');
    expect(brewBtn).not.toBeNull();
    brewBtn.click();

    expect(mockHass.callService).toHaveBeenCalledWith("morning", "brew_recipe", expect.objectContaining({
      entity_id: "sensor.dagusmorning_status",
      name: "Cloud Gesha Bloom",
      temperature: 94,
      mass_output: 36,
    }));
  });

  it("shows active Cancel banner during brewing and clicking it cancels brew", () => {
    const brewingStateMock = JSON.parse(JSON.stringify(brewingStates));
    card.hass = {
      states: brewingStateMock,
      callService: vi.fn(),
    };

    const cancelBanner = card.shadowRoot.querySelector(".cancel-banner");
    expect(cancelBanner).not.toBeNull();
    expect(cancelBanner.textContent).toContain("Brewing in progress");

    const cancelBtn = card.shadowRoot.querySelector("#btn-cancel-brew");
    expect(cancelBtn).not.toBeNull();
    cancelBtn.click();

    expect(card.hass.callService).toHaveBeenCalledWith("morning", "cancel_brew", {
      entity_id: "sensor.dagusmorning_status",
    });
  });

  it("enforces Lovelace UX Invariant: no HTML title tooltips anywhere on the card", () => {
    const elementsWithTitle = card.shadowRoot.querySelectorAll("[title]");
    expect(elementsWithTitle.length).toBe(0);
  });
});
