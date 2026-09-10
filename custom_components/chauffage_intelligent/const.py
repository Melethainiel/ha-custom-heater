"""Constants for Chauffage Intelligent integration."""

DOMAIN = "chauffage_intelligent"

# Named temperatures (palette). These are labels for temperature presets,
# they no longer drive any scheduling logic.
TEMP_CONFORT = "confort"
TEMP_ECO = "eco"
TEMP_HORS_GEL = "hors_gel"

TEMP_KEYS = [TEMP_CONFORT, TEMP_ECO, TEMP_HORS_GEL]

# Setpoint source (exposed as an attribute / sensor)
SOURCE_PLANNING = "planning"
SOURCE_MANUEL = "manuel"
SOURCE_DEFAUT = "defaut"
SOURCE_OFF = "off"

# Preset / select options
PRESET_PLANNING = "planning"

SELECT_OPTIONS = [PRESET_PLANNING, TEMP_CONFORT, TEMP_ECO, TEMP_HORS_GEL]

SELECT_OPTION_LABELS = {
    PRESET_PLANNING: "Planning",
    TEMP_CONFORT: "Confort",
    TEMP_ECO: "Éco",
    TEMP_HORS_GEL: "Hors-gel",
}

# Room types
ROOM_TYPES = [
    "salon",
    "chambre",
    "chambre_enfant",
    "bureau",
    "salle_de_bain",
    "autre",
]

# Default temperature palette by room type
DEFAULT_TEMPERATURES = {
    "salon": {TEMP_CONFORT: 20, TEMP_ECO: 17, TEMP_HORS_GEL: 7},
    "chambre": {TEMP_CONFORT: 18, TEMP_ECO: 16, TEMP_HORS_GEL: 7},
    "chambre_enfant": {TEMP_CONFORT: 19, TEMP_ECO: 17, TEMP_HORS_GEL: 7},
    "bureau": {TEMP_CONFORT: 19, TEMP_ECO: 17, TEMP_HORS_GEL: 7},
    "salle_de_bain": {TEMP_CONFORT: 22, TEMP_ECO: 17, TEMP_HORS_GEL: 7},
    "autre": {TEMP_CONFORT: 19, TEMP_ECO: 17, TEMP_HORS_GEL: 7},
}

# Default parameters
DEFAULT_UPDATE_INTERVAL = 300  # 5 minutes in seconds
DEFAULT_OFFSET = 0.0

# Setpoint application
SETPOINT_TOLERANCE = 0.1  # °C below which we consider the radiator already set

# Schedule
SCHEDULE_STEP_MINUTES = 30
SCHEDULE_SLOTS_PER_DAY = 24 * 60 // SCHEDULE_STEP_MINUTES  # 48
SCHEDULE_DAYS = 7

# Storage
STORAGE_KEY = f"{DOMAIN}.schedules"
STORAGE_VERSION = 1
LEGACY_LEARNING_FILE = f"{DOMAIN}_learned_rates.json"

# Frontend
PANEL_URL_PATH = "chauffage"
PANEL_STATIC_PATH = f"/{DOMAIN}_static"
PANEL_COMPONENT_NAME = "chauffage-intelligent-panel"

# Config keys
CONF_PIECES = "pieces"
CONF_UPDATE_INTERVAL = "update_interval"

# Piece config keys
CONF_PIECE_NAME = "name"
CONF_PIECE_ID = "id"
CONF_PIECE_AREA_ID = "area_id"
CONF_PIECE_TYPE = "type"
CONF_PIECE_RADIATEURS = "radiateurs"
CONF_PIECE_SONDE = "sonde"
CONF_PIECE_TEMPERATURES = "temperatures"
CONF_PIECE_OFFSET = "offset"

# Legacy config keys removed in version 2 (kept for migration)
LEGACY_CONF_KEYS = [
    "calendar",
    "presence_trackers",
    "security_factor",
    "min_preheat_time",
    "derivative_window",
]
