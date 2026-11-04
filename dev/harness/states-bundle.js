// Generated fixture bundle for browser harness
export const idleStates = {
  "sensor.dagusmorning_status": {
    "entity_id": "sensor.dagusmorning_status",
    "state": "ready",
    "attributes": {
      "friendly_name": "DagusMorning Status",
      "icon": "mdi:coffee-maker",
      "recipe_catalog": {
        "quick": [
          { "id": "1", "name": "Morning Glory", "temperature": 94, "mass_output": 38, "bloom_enabled": true, "bloom_duration": 12, "stages": [{ "id": 0, "output": 0, "pressure": 3 }, { "id": 1, "output": 6, "pressure": 7 }, { "id": 2, "output": 30, "pressure": 5 }] },
          { "id": "2", "name": "Daily Driver", "temperature": 92, "mass_output": 45, "bloom_enabled": false, "bloom_duration": 0, "stages": [{ "id": 0, "output": 0, "pressure": 2 }, { "id": 1, "output": 10, "pressure": 6 }, { "id": 2, "output": 38, "pressure": 6 }] }
        ],
        "favorites": [
          { "id": "fav-1", "name": "Ethiopia Yirgacheffe", "roaster_name": "April Coffee", "temperature": 93, "mass_output": 40, "bloom_enabled": true, "bloom_duration": 15, "is_favorite": true, "stages": [{ "id": 0, "output": 0, "pressure": 2 }, { "id": 1, "output": 8, "pressure": 6 }, { "id": 2, "output": 32, "pressure": 5 }] }
        ],
        "recents": [
          { "id": "rec-1", "name": "Colombia Geisha", "roaster_name": "Tim Wendelboe", "temperature": 95, "mass_output": 35, "bloom_enabled": false, "bloom_duration": 0, "stages": [{ "id": 0, "output": 0, "pressure": 4 }, { "id": 1, "output": 5, "pressure": 7 }, { "id": 2, "output": 28, "pressure": 5 }] }
        ],
        "custom": [],
        "machine": []
      }
    }
  },
  "sensor.kitchen_dagusmorning_brew_stage": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_stage",
    "state": "idle",
    "attributes": {
      "friendly_name": "DagusMorning Brew Stage",
      "icon": "mdi:progress-clock",
      "extraction_profile": []
    }
  },
  "binary_sensor.dagusmorning_brewing": {
    "entity_id": "binary_sensor.dagusmorning_brewing",
    "state": "off",
    "attributes": {
      "friendly_name": "DagusMorning Brewing"
    }
  },
  "sensor.kitchen_dagusmorning_water_tank_level": {
    "entity_id": "sensor.kitchen_dagusmorning_water_tank_level",
    "state": "511.0",
    "attributes": {
      "unit_of_measurement": "mL",
      "device_class": "volume",
      "friendly_name": "DagusMorning Water Tank Level"
    }
  },
  "sensor.kitchen_dagusmorning_water_tank_percentage": {
    "entity_id": "sensor.kitchen_dagusmorning_water_tank_percentage",
    "state": "60.1",
    "attributes": {
      "unit_of_measurement": "%",
      "friendly_name": "DagusMorning Water Tank Percentage"
    }
  },
  "sensor.kitchen_dagusmorning_brew_water_dispensed": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_water_dispensed",
    "state": "0.0",
    "attributes": {
      "unit_of_measurement": "mL",
      "device_class": "volume",
      "friendly_name": "DagusMorning Brew Water Dispensed"
    }
  },
  "sensor.kitchen_dagusmorning_brew_mass_dispensed": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_mass_dispensed",
    "state": "0.0",
    "attributes": {
      "unit_of_measurement": "g",
      "device_class": "weight",
      "friendly_name": "DagusMorning Brew Mass Dispensed"
    }
  },
  "sensor.kitchen_dagusmorning_brew_temperature": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_temperature",
    "state": "unknown",
    "attributes": {
      "unit_of_measurement": "\u00b0C",
      "device_class": "temperature",
      "friendly_name": "DagusMorning Brew Temperature"
    }
  },
  "sensor.kitchen_dagusmorning_brew_bloom_duration": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_bloom_duration",
    "state": "0",
    "attributes": {
      "unit_of_measurement": "s",
      "device_class": "duration",
      "friendly_name": "DagusMorning Bloom Duration"
    }
  },
  "sensor.dagusmorning_total_brews": {
    "entity_id": "sensor.dagusmorning_total_brews",
    "state": "2685",
    "attributes": {
      "friendly_name": "DagusMorning Total Brews",
      "state_class": "total_increasing"
    }
  },
  "sensor.kitchen_dagusmorning_lifetime_water_used": {
    "entity_id": "sensor.kitchen_dagusmorning_lifetime_water_used",
    "state": "0.52",
    "attributes": {
      "unit_of_measurement": "L",
      "device_class": "volume",
      "friendly_name": "DagusMorning Lifetime Water Used"
    }
  }
};
export const heatingStates = {
  "sensor.dagusmorning_status": {
    "entity_id": "sensor.dagusmorning_status",
    "state": "heating",
    "attributes": {
      "friendly_name": "DagusMorning Status",
      "icon": "mdi:coffee-maker",
      "recipe_catalog": {
        "quick": [
          { "id": "1", "name": "Morning Glory", "temperature": 94, "mass_output": 38, "bloom_enabled": true, "bloom_duration": 12, "stages": [{ "id": 0, "output": 0, "pressure": 3 }, { "id": 1, "output": 6, "pressure": 7 }, { "id": 2, "output": 30, "pressure": 5 }] },
          { "id": "2", "name": "Daily Driver", "temperature": 92, "mass_output": 45, "bloom_enabled": false, "bloom_duration": 0, "stages": [{ "id": 0, "output": 0, "pressure": 2 }, { "id": 1, "output": 10, "pressure": 6 }, { "id": 2, "output": 38, "pressure": 6 }] }
        ],
        "favorites": [
          { "id": "fav-1", "name": "Ethiopia Yirgacheffe", "roaster_name": "April Coffee", "temperature": 93, "mass_output": 40, "bloom_enabled": true, "bloom_duration": 15, "is_favorite": true, "stages": [{ "id": 0, "output": 0, "pressure": 2 }, { "id": 1, "output": 8, "pressure": 6 }, { "id": 2, "output": 32, "pressure": 5 }] }
        ],
        "recents": [
          { "id": "rec-1", "name": "Colombia Geisha", "roaster_name": "Tim Wendelboe", "temperature": 95, "mass_output": 35, "bloom_enabled": false, "bloom_duration": 0, "stages": [{ "id": 0, "output": 0, "pressure": 4 }, { "id": 1, "output": 5, "pressure": 7 }, { "id": 2, "output": 28, "pressure": 5 }] }
        ],
        "custom": [],
        "machine": []
      }
    }
  },
  "sensor.kitchen_dagusmorning_brew_stage": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_stage",
    "state": "heating",
    "attributes": {
      "friendly_name": "DagusMorning Brew Stage",
      "icon": "mdi:progress-clock",
      "extraction_profile": []
    }
  },
  "binary_sensor.dagusmorning_brewing": {
    "entity_id": "binary_sensor.dagusmorning_brewing",
    "state": "on",
    "attributes": {
      "friendly_name": "DagusMorning Brewing"
    }
  },
  "sensor.kitchen_dagusmorning_water_tank_level": {
    "entity_id": "sensor.kitchen_dagusmorning_water_tank_level",
    "state": "511.0",
    "attributes": {
      "unit_of_measurement": "mL",
      "device_class": "volume",
      "friendly_name": "DagusMorning Water Tank Level"
    }
  },
  "sensor.kitchen_dagusmorning_water_tank_percentage": {
    "entity_id": "sensor.kitchen_dagusmorning_water_tank_percentage",
    "state": "60.1",
    "attributes": {
      "unit_of_measurement": "%",
      "friendly_name": "DagusMorning Water Tank Percentage"
    }
  },
  "sensor.kitchen_dagusmorning_brew_water_dispensed": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_water_dispensed",
    "state": "0.0",
    "attributes": {
      "unit_of_measurement": "mL",
      "device_class": "volume",
      "friendly_name": "DagusMorning Brew Water Dispensed"
    }
  },
  "sensor.kitchen_dagusmorning_brew_mass_dispensed": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_mass_dispensed",
    "state": "0.0",
    "attributes": {
      "unit_of_measurement": "g",
      "device_class": "weight",
      "friendly_name": "DagusMorning Brew Mass Dispensed"
    }
  },
  "sensor.kitchen_dagusmorning_brew_temperature": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_temperature",
    "state": "88",
    "attributes": {
      "unit_of_measurement": "\u00b0C",
      "device_class": "temperature",
      "friendly_name": "DagusMorning Brew Temperature"
    }
  },
  "sensor.kitchen_dagusmorning_brew_bloom_duration": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_bloom_duration",
    "state": "0",
    "attributes": {
      "unit_of_measurement": "s",
      "device_class": "duration",
      "friendly_name": "DagusMorning Bloom Duration"
    }
  },
  "sensor.dagusmorning_total_brews": {
    "entity_id": "sensor.dagusmorning_total_brews",
    "state": "2685",
    "attributes": {
      "friendly_name": "DagusMorning Total Brews",
      "state_class": "total_increasing"
    }
  },
  "sensor.kitchen_dagusmorning_lifetime_water_used": {
    "entity_id": "sensor.kitchen_dagusmorning_lifetime_water_used",
    "state": "0.52",
    "attributes": {
      "unit_of_measurement": "L",
      "device_class": "volume",
      "friendly_name": "DagusMorning Lifetime Water Used"
    }
  }
};
export const brewingStates = {
  "sensor.dagusmorning_status": {
    "entity_id": "sensor.dagusmorning_status",
    "state": "brewing",
    "attributes": {
      "friendly_name": "DagusMorning Status",
      "icon": "mdi:coffee-maker",
      "recipe_catalog": {
        "quick": [
          { "id": "1", "name": "Morning Glory", "temperature": 94, "mass_output": 38, "bloom_enabled": true, "bloom_duration": 12, "stages": [{ "id": 0, "output": 0, "pressure": 3 }, { "id": 1, "output": 6, "pressure": 7 }, { "id": 2, "output": 30, "pressure": 5 }] },
          { "id": "2", "name": "Daily Driver", "temperature": 92, "mass_output": 45, "bloom_enabled": false, "bloom_duration": 0, "stages": [{ "id": 0, "output": 0, "pressure": 2 }, { "id": 1, "output": 10, "pressure": 6 }, { "id": 2, "output": 38, "pressure": 6 }] }
        ],
        "favorites": [
          { "id": "fav-1", "name": "Ethiopia Yirgacheffe", "roaster_name": "April Coffee", "temperature": 93, "mass_output": 40, "bloom_enabled": true, "bloom_duration": 15, "is_favorite": true, "stages": [{ "id": 0, "output": 0, "pressure": 2 }, { "id": 1, "output": 8, "pressure": 6 }, { "id": 2, "output": 32, "pressure": 5 }] }
        ],
        "recents": [
          { "id": "rec-1", "name": "Colombia Geisha", "roaster_name": "Tim Wendelboe", "temperature": 95, "mass_output": 35, "bloom_enabled": false, "bloom_duration": 0, "stages": [{ "id": 0, "output": 0, "pressure": 4 }, { "id": 1, "output": 5, "pressure": 7 }, { "id": 2, "output": 28, "pressure": 5 }] }
        ],
        "custom": [],
        "machine": []
      }
    }
  },
  "sensor.kitchen_dagusmorning_brew_stage": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_stage",
    "state": "brewing",
    "attributes": {
      "friendly_name": "DagusMorning Brew Stage",
      "icon": "mdi:progress-clock",
      "extraction_profile": [
        {
          "t": 0.0,
          "water": 0.0,
          "mass": 0.0,
          "temp": 93,
          "flow": 0.0
        },
        {
          "t": 2.0,
          "water": 10.0,
          "mass": 8.0,
          "temp": 93,
          "flow": 5.0
        },
        {
          "t": 4.0,
          "water": 22.0,
          "mass": 18.0,
          "temp": 93,
          "flow": 6.0
        },
        {
          "t": 6.0,
          "water": 35.0,
          "mass": 30.0,
          "temp": 94,
          "flow": 6.5
        },
        {
          "t": 8.0,
          "water": 50.0,
          "mass": 45.0,
          "temp": 93,
          "flow": 7.5
        }
      ]
    }
  },
  "binary_sensor.dagusmorning_brewing": {
    "entity_id": "binary_sensor.dagusmorning_brewing",
    "state": "on",
    "attributes": {
      "friendly_name": "DagusMorning Brewing"
    }
  },
  "sensor.kitchen_dagusmorning_water_tank_level": {
    "entity_id": "sensor.kitchen_dagusmorning_water_tank_level",
    "state": "461.0",
    "attributes": {
      "unit_of_measurement": "mL",
      "device_class": "volume",
      "friendly_name": "DagusMorning Water Tank Level"
    }
  },
  "sensor.kitchen_dagusmorning_water_tank_percentage": {
    "entity_id": "sensor.kitchen_dagusmorning_water_tank_percentage",
    "state": "54.2",
    "attributes": {
      "unit_of_measurement": "%",
      "friendly_name": "DagusMorning Water Tank Percentage"
    }
  },
  "sensor.kitchen_dagusmorning_brew_water_dispensed": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_water_dispensed",
    "state": "50.0",
    "attributes": {
      "unit_of_measurement": "mL",
      "device_class": "volume",
      "friendly_name": "DagusMorning Brew Water Dispensed"
    }
  },
  "sensor.kitchen_dagusmorning_brew_mass_dispensed": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_mass_dispensed",
    "state": "45.0",
    "attributes": {
      "unit_of_measurement": "g",
      "device_class": "weight",
      "friendly_name": "DagusMorning Brew Mass Dispensed"
    }
  },
  "sensor.kitchen_dagusmorning_brew_temperature": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_temperature",
    "state": "93",
    "attributes": {
      "unit_of_measurement": "\u00b0C",
      "device_class": "temperature",
      "friendly_name": "DagusMorning Brew Temperature"
    }
  },
  "sensor.kitchen_dagusmorning_brew_bloom_duration": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_bloom_duration",
    "state": "12",
    "attributes": {
      "unit_of_measurement": "s",
      "device_class": "duration",
      "friendly_name": "DagusMorning Bloom Duration"
    }
  },
  "sensor.dagusmorning_total_brews": {
    "entity_id": "sensor.dagusmorning_total_brews",
    "state": "2685",
    "attributes": {
      "friendly_name": "DagusMorning Total Brews",
      "state_class": "total_increasing"
    }
  },
  "sensor.kitchen_dagusmorning_lifetime_water_used": {
    "entity_id": "sensor.kitchen_dagusmorning_lifetime_water_used",
    "state": "0.52",
    "attributes": {
      "unit_of_measurement": "L",
      "device_class": "volume",
      "friendly_name": "DagusMorning Lifetime Water Used"
    }
  }
};
export const doneStates = {
  "sensor.dagusmorning_status": {
    "entity_id": "sensor.dagusmorning_status",
    "state": "ready",
    "attributes": {
      "friendly_name": "DagusMorning Status",
      "icon": "mdi:coffee-maker",
      "recipe_catalog": {
        "quick": [
          { "id": "1", "name": "Morning Glory", "temperature": 94, "mass_output": 38, "bloom_enabled": true, "bloom_duration": 12, "stages": [{ "id": 0, "output": 0, "pressure": 3 }, { "id": 1, "output": 6, "pressure": 7 }, { "id": 2, "output": 30, "pressure": 5 }] },
          { "id": "2", "name": "Daily Driver", "temperature": 92, "mass_output": 45, "bloom_enabled": false, "bloom_duration": 0, "stages": [{ "id": 0, "output": 0, "pressure": 2 }, { "id": 1, "output": 10, "pressure": 6 }, { "id": 2, "output": 38, "pressure": 6 }] }
        ],
        "favorites": [
          { "id": "fav-1", "name": "Ethiopia Yirgacheffe", "roaster_name": "April Coffee", "temperature": 93, "mass_output": 40, "bloom_enabled": true, "bloom_duration": 15, "is_favorite": true, "stages": [{ "id": 0, "output": 0, "pressure": 2 }, { "id": 1, "output": 8, "pressure": 6 }, { "id": 2, "output": 32, "pressure": 5 }] }
        ],
        "recents": [
          { "id": "rec-1", "name": "Colombia Geisha", "roaster_name": "Tim Wendelboe", "temperature": 95, "mass_output": 35, "bloom_enabled": false, "bloom_duration": 0, "stages": [{ "id": 0, "output": 0, "pressure": 4 }, { "id": 1, "output": 5, "pressure": 7 }, { "id": 2, "output": 28, "pressure": 5 }] }
        ],
        "custom": [],
        "machine": []
      }
    }
  },
  "sensor.kitchen_dagusmorning_brew_stage": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_stage",
    "state": "done",
    "attributes": {
      "friendly_name": "DagusMorning Brew Stage",
      "icon": "mdi:progress-clock",
      "extraction_profile": [
        {
          "t": 0.0,
          "water": 0.0,
          "mass": 0.0,
          "temp": 93,
          "flow": 0.0
        },
        {
          "t": 2.0,
          "water": 10.0,
          "mass": 8.0,
          "temp": 93,
          "flow": 5.0
        },
        {
          "t": 4.0,
          "water": 22.0,
          "mass": 18.0,
          "temp": 93,
          "flow": 6.0
        },
        {
          "t": 6.0,
          "water": 35.0,
          "mass": 30.0,
          "temp": 94,
          "flow": 6.5
        },
        {
          "t": 8.0,
          "water": 50.0,
          "mass": 45.0,
          "temp": 93,
          "flow": 7.5
        },
        {
          "t": 10.0,
          "water": 50.0,
          "mass": 45.0,
          "temp": 93,
          "flow": 0.0
        }
      ]
    }
  },
  "binary_sensor.dagusmorning_brewing": {
    "entity_id": "binary_sensor.dagusmorning_brewing",
    "state": "off",
    "attributes": {
      "friendly_name": "DagusMorning Brewing"
    }
  },
  "sensor.kitchen_dagusmorning_water_tank_level": {
    "entity_id": "sensor.kitchen_dagusmorning_water_tank_level",
    "state": "461.0",
    "attributes": {
      "unit_of_measurement": "mL",
      "device_class": "volume",
      "friendly_name": "DagusMorning Water Tank Level"
    }
  },
  "sensor.kitchen_dagusmorning_water_tank_percentage": {
    "entity_id": "sensor.kitchen_dagusmorning_water_tank_percentage",
    "state": "54.2",
    "attributes": {
      "unit_of_measurement": "%",
      "friendly_name": "DagusMorning Water Tank Percentage"
    }
  },
  "sensor.kitchen_dagusmorning_brew_water_dispensed": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_water_dispensed",
    "state": "50.0",
    "attributes": {
      "unit_of_measurement": "mL",
      "device_class": "volume",
      "friendly_name": "DagusMorning Brew Water Dispensed"
    }
  },
  "sensor.kitchen_dagusmorning_brew_mass_dispensed": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_mass_dispensed",
    "state": "45.0",
    "attributes": {
      "unit_of_measurement": "g",
      "device_class": "weight",
      "friendly_name": "DagusMorning Brew Mass Dispensed"
    }
  },
  "sensor.kitchen_dagusmorning_brew_temperature": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_temperature",
    "state": "93",
    "attributes": {
      "unit_of_measurement": "\u00b0C",
      "device_class": "temperature",
      "friendly_name": "DagusMorning Brew Temperature"
    }
  },
  "sensor.kitchen_dagusmorning_brew_bloom_duration": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_bloom_duration",
    "state": "12",
    "attributes": {
      "unit_of_measurement": "s",
      "device_class": "duration",
      "friendly_name": "DagusMorning Bloom Duration"
    }
  },
  "sensor.dagusmorning_total_brews": {
    "entity_id": "sensor.dagusmorning_total_brews",
    "state": "2686",
    "attributes": {
      "friendly_name": "DagusMorning Total Brews",
      "state_class": "total_increasing"
    }
  },
  "sensor.kitchen_dagusmorning_lifetime_water_used": {
    "entity_id": "sensor.kitchen_dagusmorning_lifetime_water_used",
    "state": "0.57",
    "attributes": {
      "unit_of_measurement": "L",
      "device_class": "volume",
      "friendly_name": "DagusMorning Lifetime Water Used"
    }
  }
};
export const cancelStates = {
  "sensor.dagusmorning_status": {
    "entity_id": "sensor.dagusmorning_status",
    "state": "ready",
    "attributes": {
      "friendly_name": "DagusMorning Status",
      "icon": "mdi:coffee-maker",
      "recipe_catalog": {
        "quick": [
          { "id": "1", "name": "Morning Glory", "temperature": 94, "mass_output": 38, "bloom_enabled": true, "bloom_duration": 12, "stages": [{ "id": 0, "output": 0, "pressure": 3 }, { "id": 1, "output": 6, "pressure": 7 }, { "id": 2, "output": 30, "pressure": 5 }] },
          { "id": "2", "name": "Daily Driver", "temperature": 92, "mass_output": 45, "bloom_enabled": false, "bloom_duration": 0, "stages": [{ "id": 0, "output": 0, "pressure": 2 }, { "id": 1, "output": 10, "pressure": 6 }, { "id": 2, "output": 38, "pressure": 6 }] }
        ],
        "favorites": [
          { "id": "fav-1", "name": "Ethiopia Yirgacheffe", "roaster_name": "April Coffee", "temperature": 93, "mass_output": 40, "bloom_enabled": true, "bloom_duration": 15, "is_favorite": true, "stages": [{ "id": 0, "output": 0, "pressure": 2 }, { "id": 1, "output": 8, "pressure": 6 }, { "id": 2, "output": 32, "pressure": 5 }] }
        ],
        "recents": [
          { "id": "rec-1", "name": "Colombia Geisha", "roaster_name": "Tim Wendelboe", "temperature": 95, "mass_output": 35, "bloom_enabled": false, "bloom_duration": 0, "stages": [{ "id": 0, "output": 0, "pressure": 4 }, { "id": 1, "output": 5, "pressure": 7 }, { "id": 2, "output": 28, "pressure": 5 }] }
        ],
        "custom": [],
        "machine": []
      }
    }
  },
  "sensor.kitchen_dagusmorning_brew_stage": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_stage",
    "state": "idle",
    "attributes": {
      "friendly_name": "DagusMorning Brew Stage",
      "icon": "mdi:progress-clock",
      "extraction_profile": [
        {
          "t": 0.0,
          "water": 0.0,
          "mass": 0.0,
          "temp": 93,
          "flow": 0.0
        },
        {
          "t": 2.0,
          "water": 8.0,
          "mass": 6.0,
          "temp": 93,
          "flow": 4.0
        }
      ]
    }
  },
  "binary_sensor.dagusmorning_brewing": {
    "entity_id": "binary_sensor.dagusmorning_brewing",
    "state": "off",
    "attributes": {
      "friendly_name": "DagusMorning Brewing"
    }
  },
  "sensor.kitchen_dagusmorning_water_tank_level": {
    "entity_id": "sensor.kitchen_dagusmorning_water_tank_level",
    "state": "503.0",
    "attributes": {
      "unit_of_measurement": "mL",
      "device_class": "volume",
      "friendly_name": "DagusMorning Water Tank Level"
    }
  },
  "sensor.kitchen_dagusmorning_water_tank_percentage": {
    "entity_id": "sensor.kitchen_dagusmorning_water_tank_percentage",
    "state": "59.2",
    "attributes": {
      "unit_of_measurement": "%",
      "friendly_name": "DagusMorning Water Tank Percentage"
    }
  },
  "sensor.kitchen_dagusmorning_brew_water_dispensed": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_water_dispensed",
    "state": "8.0",
    "attributes": {
      "unit_of_measurement": "mL",
      "device_class": "volume",
      "friendly_name": "DagusMorning Brew Water Dispensed"
    }
  },
  "sensor.kitchen_dagusmorning_brew_mass_dispensed": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_mass_dispensed",
    "state": "6.0",
    "attributes": {
      "unit_of_measurement": "g",
      "device_class": "weight",
      "friendly_name": "DagusMorning Brew Mass Dispensed"
    }
  },
  "sensor.kitchen_dagusmorning_brew_temperature": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_temperature",
    "state": "93",
    "attributes": {
      "unit_of_measurement": "\u00b0C",
      "device_class": "temperature",
      "friendly_name": "DagusMorning Brew Temperature"
    }
  },
  "sensor.kitchen_dagusmorning_brew_bloom_duration": {
    "entity_id": "sensor.kitchen_dagusmorning_brew_bloom_duration",
    "state": "0",
    "attributes": {
      "unit_of_measurement": "s",
      "device_class": "duration",
      "friendly_name": "DagusMorning Bloom Duration"
    }
  },
  "sensor.dagusmorning_total_brews": {
    "entity_id": "sensor.dagusmorning_total_brews",
    "state": "2685",
    "attributes": {
      "friendly_name": "DagusMorning Total Brews",
      "state_class": "total_increasing"
    }
  },
  "sensor.kitchen_dagusmorning_lifetime_water_used": {
    "entity_id": "sensor.kitchen_dagusmorning_lifetime_water_used",
    "state": "0.52",
    "attributes": {
      "unit_of_measurement": "L",
      "device_class": "volume",
      "friendly_name": "DagusMorning Lifetime Water Used"
    }
  }
};
