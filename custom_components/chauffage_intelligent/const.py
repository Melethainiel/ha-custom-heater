"""Constants for Chauffage Intelligent integration."""

DOMAIN = "chauffage_intelligent"

# Modes
MODE_CONFORT = "confort"
MODE_ECO = "eco"
MODE_HORS_GEL = "hors_gel"
MODE_OFF = "off"

MODES = [MODE_CONFORT, MODE_ECO, MODE_HORS_GEL, MODE_OFF]

# Room types
ROOM_TYPES = [
    "salon",
    "chambre",
    "chambre_enfant",
    "bureau",
    "salle_de_bain",
    "autre",
]

# Default temperatures by room type
DEFAULT_TEMPERATURES = {
    "salon": {MODE_CONFORT: 20, MODE_ECO: 17, MODE_HORS_GEL: 7},
    "chambre": {MODE_CONFORT: 18, MODE_ECO: 16, MODE_HORS_GEL: 7},
    "chambre_enfant": {MODE_CONFORT: 19, MODE_ECO: 17, MODE_HORS_GEL: 7},
    "bureau": {MODE_CONFORT: 19, MODE_ECO: 17, MODE_HORS_GEL: 7},
    "salle_de_bain": {MODE_CONFORT: 22, MODE_ECO: 17, MODE_HORS_GEL: 7},
    "autre": {MODE_CONFORT: 19, MODE_ECO: 17, MODE_HORS_GEL: 7},
}

# Default parameters
DEFAULT_UPDATE_INTERVAL = 300  # 5 minutes in seconds
DEFAULT_SECURITY_FACTOR = 1.3
DEFAULT_MIN_PREHEAT_TIME = 30  # minutes
DEFAULT_DERIVATIVE_WINDOW = 30  # minutes
DEFAULT_HEATING_RATE = 1.0  # °C/h fallback when no data

# Calendar events
EVENT_ABSENCE = "absence"
EVENT_CONFORT = "confort"

# Mode sources
SOURCE_CALENDAR = "calendrier"
SOURCE_PRESENCE = "presence"
SOURCE_DEFAULT = "defaut"
SOURCE_OVERRIDE = "override"
SOURCE_ANTICIPATION = "anticipation"

# Home states
STATE_HOME = "home"
STATE_NOT_HOME = "not_home"

# Config keys
CONF_CALENDAR = "calendar"
CONF_PRESENCE_TRACKERS = "presence_trackers"
CONF_PIECES = "pieces"
CONF_SECURITY_FACTOR = "security_factor"
CONF_MIN_PREHEAT_TIME = "min_preheat_time"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_DERIVATIVE_WINDOW = "derivative_window"

# Piece config keys
CONF_PIECE_NAME = "name"
CONF_PIECE_ID = "id"
CONF_PIECE_TYPE = "type"
CONF_PIECE_RADIATEUR = "radiateur"
CONF_PIECE_SONDE = "sonde"
CONF_PIECE_TEMPERATURES = "temperatures"
