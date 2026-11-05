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

  it("renders range sliders with MDI icons for yield, temp, bloom, and water bypass", () => {
    const drawerBtn = card.shadowRoot.querySelector("#btn-toggle-drawer");
    drawerBtn.click();
    const studioTab = card.shadowRoot.querySelector('.tab-btn[data-tab="studio"]');
    studioTab.click();

    // Verify all 4 sliders exist with correct data-slider attributes
    const massSlider = card.shadowRoot.querySelector('.studio-range-slider[data-slider="mass"]');
    const tempSlider = card.shadowRoot.querySelector('.studio-range-slider[data-slider="temp"]');
    const bloomSlider = card.shadowRoot.querySelector('.studio-range-slider[data-slider="bloom"]');
    const bypassSlider = card.shadowRoot.querySelector('.studio-range-slider[data-slider="bypass"]');

    expect(massSlider).not.toBeNull();
    expect(tempSlider).not.toBeNull();
    expect(bloomSlider).not.toBeNull();
    expect(bypassSlider).not.toBeNull();

    // Verify MDI icons are rendered for each slider
    expect(card.shadowRoot.querySelector('ha-icon[icon="mdi:scale"]')).not.toBeNull();
    expect(card.shadowRoot.querySelector('ha-icon[icon="mdi:thermometer"]')).not.toBeNull();
    expect(card.shadowRoot.querySelector('ha-icon[icon="mdi:timer-sand"]')).not.toBeNull();
    expect(card.shadowRoot.querySelector('ha-icon[icon="mdi:water-plus"]')).not.toBeNull();

    // Test sliding bloom time to 15s
    bloomSlider.value = "15";
    bloomSlider.dispatchEvent(new Event("input", { bubbles: true }));
    expect(card._draftCurve.bloom_duration).toBe(15);
    expect(card._draftCurve.bloom_enabled).toBe(true);

    const bloomBadge = card.shadowRoot.querySelector('.slider-val-badge[data-badge="bloom"]');
    expect(bloomBadge.textContent).toContain("15 s");

    // Test sliding water bypass to 120mL (Americano)
    bypassSlider.value = "120";
    bypassSlider.dispatchEvent(new Event("input", { bubbles: true }));
    expect(card._draftCurve.water_output).toBe(120);
    expect(card._draftCurve.bypass_enabled).toBe(true);

    const bypassBadge = card.shadowRoot.querySelector('.slider-val-badge[data-badge="bypass"]');
    expect(bypassBadge.textContent).toContain("120 mL");
  });

  it("verifies 50% smaller handle radius and stage color coding in SVG curve", () => {
    const drawerBtn = card.shadowRoot.querySelector("#btn-toggle-drawer");
    drawerBtn.click();
    const studioTab = card.shadowRoot.querySelector('.tab-btn[data-tab="studio"]');
    studioTab.click();

    // Check handle radius is 3.5 (50% smaller than original 7)
    const handles = card.shadowRoot.querySelectorAll(".studio-handle");
    expect(handles.length).toBe(3);
    handles.forEach((h) => {
      expect(h.getAttribute("r")).toBe("3.5");
    });

    // Check hit targets exist for easy touch/mouse grab
    const hitTargets = card.shadowRoot.querySelectorAll(".studio-handle-hit");
    expect(hitTargets.length).toBe(3);
    hitTargets.forEach((hit) => {
      expect(hit.getAttribute("r")).toBe("14");
    });

    // Check 3 stage paths with distinct colors
    const seg0 = card.shadowRoot.querySelector('.stage-seg[data-seg="0"]');
    const seg1 = card.shadowRoot.querySelector('.stage-seg[data-seg="1"]');
    const seg2 = card.shadowRoot.querySelector('.stage-seg[data-seg="2"]');

    expect(seg0.getAttribute("stroke")).toBe("#1abc9c"); // Pre-Infusion
    expect(seg1.getAttribute("stroke")).toBe("#e67e22"); // Infusion
    expect(seg2.getAttribute("stroke")).toBe("#e74c3c"); // Post-Infusion

    // Check stage pills beneath SVG
    expect(card.shadowRoot.querySelector('.stage-pill[data-pill="0"]').textContent).toContain("Pre-Infusion");
    expect(card.shadowRoot.querySelector('.stage-pill[data-pill="1"]').textContent).toContain("Infusion");
    expect(card.shadowRoot.querySelector('.stage-pill[data-pill="2"]').textContent).toContain("Post-Infusion");
  });

  it("selects Americano preset with coffee yield and bypass water", () => {
    const drawerBtn = card.shadowRoot.querySelector("#btn-toggle-drawer");
    drawerBtn.click();
    const studioTab = card.shadowRoot.querySelector('.tab-btn[data-tab="studio"]');
    studioTab.click();

    const americanoBtn = card.shadowRoot.querySelector('.preset-btn[data-preset="americano"]');
    expect(americanoBtn).not.toBeNull();
    americanoBtn.click();

    expect(card._draftCurve.name).toBe("Americano");
    expect(card._draftCurve.mass_output).toBe(35);
    expect(card._draftCurve.water_output).toBe(120);
    expect(card._draftCurve.bypass_enabled).toBe(true);

    // Visual Cup Composition Meter reflects dilution water
    const cupWater = card.shadowRoot.querySelector(".cup-bar-water");
    expect(cupWater).not.toBeNull();
    expect(cupWater.textContent).toContain("120mL Water");

    const bypassBadge = card.shadowRoot.querySelector('.slider-val-badge[data-badge="bypass"]');
    expect(bypassBadge.textContent).toContain("+120 mL");

    // Brew Now button reflects coffee yield + bypass water
    const brewBtn = card.shadowRoot.querySelector("#btn-studio-brew");
    expect(brewBtn.textContent).toContain("35g @ 94°C + 120mL water");
  });

  it("clicking favorite star on recipe card calls morning.toggle_favorite service with entity_id", () => {
    const drawerBtn = card.shadowRoot.querySelector("#btn-toggle-drawer");
    drawerBtn.click();

    const favTab = card.shadowRoot.querySelector('.subtab-btn[data-subtab="favorites"]');
    if (favTab) favTab.click();

    const favBtn = card.shadowRoot.querySelector('.icon-action-btn.fav[data-action="toggle-fav"]');
    expect(favBtn).not.toBeNull();
    favBtn.click();

    expect(mockHass.callService).toHaveBeenCalledWith("morning", "toggle_favorite", expect.objectContaining({
      entity_id: "sensor.dagusmorning_status",
      profile_id: "fav-1",
    }));
  });

  it("clicking barista quick chips in Bloom and Cup Composition stations updates values and cup meter", () => {
    const drawerBtn = card.shadowRoot.querySelector("#btn-toggle-drawer");
    drawerBtn.click();
    const studioTab = card.shadowRoot.querySelector('.tab-btn[data-tab="studio"]');
    studioTab.click();

    // Tap Bloom 'Standard (10s)' quick chip
    const bloom10Chip = card.shadowRoot.querySelector('.quick-preset-chip.bloom-chip[data-val="10"]');
    expect(bloom10Chip).not.toBeNull();
    bloom10Chip.click();

    expect(card._draftCurve.bloom_duration).toBe(10);
    expect(card._draftCurve.bloom_enabled).toBe(true);
    expect(card.shadowRoot.querySelector('.slider-val-badge[data-badge="bloom"]').textContent).toContain("10 s");

    // Tap Bypass 'Americano (+120mL)' quick chip
    const bypass120Chip = card.shadowRoot.querySelector('.quick-preset-chip.bypass-chip[data-val="120"]');
    expect(bypass120Chip).not.toBeNull();
    bypass120Chip.click();

    expect(card._draftCurve.water_output).toBe(120);
    expect(card._draftCurve.bypass_enabled).toBe(true);
    expect(card.shadowRoot.querySelector('.cup-bar-water').textContent).toContain("120mL Water");
  });

  it("telemetry updates while drawer is open do not rebuild #sec-brew or jump scroll", () => {
    const drawerBtn = card.shadowRoot.querySelector("#btn-toggle-drawer");
    drawerBtn.click();

    const brewSectionBefore = card.shadowRoot.querySelector("#sec-brew");
    expect(brewSectionBefore).not.toBeNull();

    // Simulate 1Hz telemetry update arriving from Hass
    const updatedStates = JSON.parse(JSON.stringify(idleStates));
    updatedStates["sensor.dagusmorning_status"].attributes.live_telemetry = {
      brew_stage: "idle",
      water_ml: 12,
    };
    card.hass = {
      states: updatedStates,
      callService: vi.fn(),
    };

    const brewSectionAfter = card.shadowRoot.querySelector("#sec-brew");
    // #sec-brew element identity preserved (no innerHTML blowup of section container)
    expect(brewSectionAfter).toBe(brewSectionBefore);
    expect(card.shadowRoot.querySelector(".brew-drawer")).not.toBeNull();
  });

  it("enforces Lovelace UX Invariant: no HTML title tooltips anywhere on the card", () => {
    const elementsWithTitle = card.shadowRoot.querySelectorAll("[title]");
    expect(elementsWithTitle.length).toBe(0);
  });
});
