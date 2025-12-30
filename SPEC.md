# Chauffage Intelligent - Spécifications Custom Component Home Assistant

## Résumé

Custom component Home Assistant pour gérer intelligemment des radiateurs Zigbee (Thermor Bilbao 4) avec :

- Modes par pièce (Confort, Eco, Hors-gel, Off)
- Planification via Google Calendar
- Détection de présence temps réel
- Anticipation du préchauffage basée sur la dérivée thermique

-----

## Contexte technique

### Matériel

- **Radiateurs** : Thermor Bilbao 4 connectés en Zigbee (ZHA)
- **Pas de fil pilote** : contrôle uniquement via la consigne de température
- **Sondes externes** : capteurs de température séparés dans chaque pièce (déjà dans HA)
- **Fallback** : si sonde externe indisponible, utiliser la sonde interne du radiateur

### Dépendances HA

- Intégration Google Calendar configurée
- Device trackers pour la présence (app mobile)
- Entities climate existantes pour chaque radiateur
- Entities sensor pour les sondes de température

-----

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SOURCES D'ENTRÉE                         │
├─────────────────────────────────────────────────────────────┤
│  Google Calendar          Device Trackers      Config UI    │
│  (événements)             (présence)           (pièces)     │
└──────────┬─────────────────────────────────────┬──────────┘
           │                     │                 │
           ▼                     ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│                 COORDINATOR (logique centrale)              │
│  - Parse événements calendrier                              │
│  - Calcule présence maison                                  │
│  - Résout le mode par pièce                                 │
│  - Calcule temps de préchauffage                            │
│  - Gère l'anticipation                                      │
└──────────┬─────────────────────────────────────────────────┬┘
           │                                                 │
           ▼                                                 ▼
┌─────────────────────────┐                 ┌─────────────────────────┐
│   ENTITÉS PAR PIÈCE     │                 │   ENTITÉS GLOBALES      │
│  - climate.chauffage_*  │                 │  - binary_sensor.       │
│  - sensor.*_mode        │                 │    maison_occupee       │
│  - sensor.*_prechauff   │                 │  - sensor.mode_global   │
└─────────┬───────────────┘                 └─────────────────────────┘
          │
          ▼
┌─────────────────────────┐
│  RADIATEURS ZIGBEE      │
│  (climate.bilbao_*)     │
│  Action: set_temperature│
└─────────────────────────┘
```

-----

## Logique de résolution du mode

### Priorités (de la plus haute à la plus basse)

```
1. Événement "Absence" dans calendrier     → Hors-gel (forcé, vacances)
2. Personne à la maison (device trackers)  → Eco (absence non planifiée)
3. Événement "Confort {pièce}" calendrier  → Confort pour cette pièce uniquement
4. Événement "Confort" calendrier          → Confort global
5. Aucune condition                        → Eco (défaut)
```

### Parsing des événements calendrier

|Événement        |Effet                                      |
|-----------------|-------------------------------------------|
|`Absence`        |Toute la maison en Hors-gel                |
|`Confort`        |Toute la maison en Confort                 |
|`Confort Bureau` |Seul le bureau en Confort, reste inchangé  |
|`Confort Chambre`|Seule la chambre en Confort, reste inchangé|

**Matching** : case-insensitive, trim whitespace

- `"confort bureau"` == `"Confort Bureau"` == `"CONFORT BUREAU"`

### Présence maison

```python
maison_occupee = any(
    state == "home"
    for tracker in configured_device_trackers
)
```

Comportement :

- Quelqu'un rentre → switch immédiat vers le mode calendrier
- Tout le monde part → passage en Eco (même si calendrier dit Confort)
- Invités : si un résident est home, les invités sont couverts

-----

## Températures par type de pièce

### Configuration par défaut (modifiable par pièce)

|Type de pièce |Confort|Eco |Hors-gel|
|--------------|-------|----|--------|
|salon         |20°C   |17°C|7°C     |
|chambre       |18°C   |16°C|7°C     |
|chambre_enfant|19°C   |17°C|7°C     |
|bureau        |19°C   |17°C|7°C     |
|salle_de_bain |22°C   |17°C|7°C     |

### Types de pièce disponibles

```python
ROOM_TYPES = [
    "salon",
    "chambre",
    "chambre_enfant",
    "bureau",
    "salle_de_bain",
    "autre"
]
```

-----

## Anticipation du préchauffage

### Calcul de la dérivée thermique

```python
# Calcul glissant sur les X dernières minutes
vitesse_chauffe = (temp_actuelle - temp_il_y_a_30min) / 30  # °C/min
vitesse_chauffe_h = vitesse_chauffe * 60  # °C/h
```

**Paramètres** :

- `time_window` : 30 minutes (configurable)
- Stockage des N dernières mesures pour calcul

### Calcul du temps de préchauffage

```python
def calculer_temps_prechauffage(
    temp_actuelle: float,
    temp_cible: float,
    vitesse_chauffe: float,  # °C/h, positif = chauffe
    facteur_securite: float = 1.3,
    temps_minimum: int = 30  # minutes
) -> int:
    """Retourne le temps estimé en minutes."""

    delta = temp_cible - temp_actuelle

    if delta <= 0:
        return 0  # Déjà à température

    if vitesse_chauffe <= 0:
        # Pas de données ou pièce qui refroidit
        # Utiliser une valeur par défaut conservative
        vitesse_chauffe = 1.0  # °C/h par défaut

    temps_brut = (delta / vitesse_chauffe) * 60  # minutes
    temps_avec_marge = temps_brut * facteur_securite

    return max(int(temps_avec_marge), temps_minimum)
```

### Déclenchement anticipé

```python
def verifier_prechauffage(piece, evenements_calendrier):
    """Vérifie si on doit déclencher le préchauffage."""

    prochain_confort = trouver_prochain_evenement_confort(
        evenements_calendrier,
        piece
    )

    if not prochain_confort:
        return False

    temps_avant_event = (prochain_confort.start - now()).minutes
    temps_prechauffage = piece.temps_prechauffage_estime

    if temps_avant_event <= temps_prechauffage:
        return True  # Déclencher le préchauffage maintenant

    return False
```

-----

## Entités créées

### Par pièce

|Entity ID                                    |Type   |Description                       |
|---------------------------------------------|-------|----------------------------------|
|`climate.chauffage_{piece_id}`               |Climate|Entité principale, mode + consigne|
|`sensor.{piece_id}_mode_calcule`             |Sensor |Mode actuel résolu                |
|`sensor.{piece_id}_temperature_cible`        |Sensor |Consigne actuelle en °C           |
|`sensor.{piece_id}_temps_prechauffage`       |Sensor |Minutes estimées                  |
|`sensor.{piece_id}_vitesse_chauffe`          |Sensor |°C/h actuel                       |
|`binary_sensor.{piece_id}_prechauffage_actif`|Binary |True si anticipation en cours     |

### Globales

|Entity ID                               |Type  |Description    |
|----------------------------------------|------|---------------|
|`binary_sensor.chauffage_maison_occupee`|Binary|Présence maison|
|`sensor.chauffage_mode_global`          |Sensor|Mode dominant  |

### Attributs de l'entité climate

```python
{
    "mode_calcule": "confort",           # Mode résolu par la logique
    "source_mode": "calendrier",         # calendrier | presence | defaut
    "temperature_cible": 20.0,
    "temperature_actuelle": 18.5,
    "vitesse_chauffe": 1.2,              # °C/h
    "temps_prechauffage": 45,            # minutes
    "prechauffage_actif": False,
    "prochain_evenement": "2025-01-02T18:00:00",
    "radiateur_entity": "climate.bilbao_salon",
    "sonde_entity": "sensor.temperature_salon",
    "type_piece": "salon"
}
```

-----

## Services

### `chauffage_intelligent.set_mode`

Force un mode pour une pièce (override temporaire).

```yaml
service: chauffage_intelligent.set_mode
data:
  piece: bureau
  mode: confort  # confort | eco | hors_gel | off
  duree: 120     # minutes, optionnel (défaut: jusqu'au prochain changement calendrier)
```

### `chauffage_intelligent.reset_mode`

Annule l'override et revient au mode calculé.

```yaml
service: chauffage_intelligent.reset_mode
data:
  piece: bureau  # optionnel, toutes les pièces si omis
```

### `chauffage_intelligent.refresh`

Force un recalcul immédiat de tous les modes.

```yaml
service: chauffage_intelligent.refresh
```

-----

## Configuration UI (Config Flow)

### Étape 1 : Configuration générale

```
- Calendrier Google : [liste déroulante des calendar.*]
- Device trackers présence : [multi-select des device_tracker.*]
- Intervalle de mise à jour : 5 min (défaut)
- Facteur sécurité préchauffage : 1.3 (défaut)
- Temps minimum préchauffage : 30 min (défaut)
```

### Étape 2 : Ajout d'une pièce

```
- Nom : "Bureau"
- ID : "bureau" (auto-généré, modifiable)
- Type : [salon | chambre | chambre_enfant | bureau | salle_de_bain | autre]
- Radiateur : [liste des climate.*]
- Sonde température : [liste des sensor.* avec device_class=temperature]
- Températures :
  - Confort : 19°C (pré-rempli selon type)
  - Eco : 17°C
  - Hors-gel : 7°C
```

### Options (après installation)

```
- Ajouter une pièce
- Modifier une pièce
- Supprimer une pièce
- Modifier les paramètres globaux
```

-----

## Structure des fichiers

```
custom_components/
└── chauffage_intelligent/
    ├── __init__.py           # Setup, register services
    ├── manifest.json         # Metadata, dependencies
    ├── const.py              # Constantes, valeurs par défaut
    ├── config_flow.py        # UI de configuration
    ├── coordinator.py        # DataUpdateCoordinator (logique centrale)
    ├── climate.py            # Entités Climate
    ├── sensor.py             # Entités Sensor
    ├── binary_sensor.py      # Entités Binary Sensor
    ├── services.yaml         # Définition des services
    ├── strings.json          # Traductions EN
    └── translations/
        └── fr.json           # Traductions FR
```

-----

## manifest.json

```json
{
  "domain": "chauffage_intelligent",
  "name": "Chauffage Intelligent",
  "version": "1.0.0",
  "documentation": "https://github.com/xxx/chauffage_intelligent",
  "dependencies": [],
  "codeowners": [],
  "requirements": [],
  "iot_class": "local_polling",
  "config_flow": true,
  "integration_type": "hub"
}
```

-----

## Constantes (const.py)

```python
DOMAIN = "chauffage_intelligent"

# Modes
MODE_CONFORT = "confort"
MODE_ECO = "eco"
MODE_HORS_GEL = "hors_gel"
MODE_OFF = "off"

MODES = [MODE_CONFORT, MODE_ECO, MODE_HORS_GEL, MODE_OFF]

# Types de pièces avec températures par défaut
DEFAULT_TEMPERATURES = {
    "salon": {MODE_CONFORT: 20, MODE_ECO: 17, MODE_HORS_GEL: 7},
    "chambre": {MODE_CONFORT: 18, MODE_ECO: 16, MODE_HORS_GEL: 7},
    "chambre_enfant": {MODE_CONFORT: 19, MODE_ECO: 17, MODE_HORS_GEL: 7},
    "bureau": {MODE_CONFORT: 19, MODE_ECO: 17, MODE_HORS_GEL: 7},
    "salle_de_bain": {MODE_CONFORT: 22, MODE_ECO: 17, MODE_HORS_GEL: 7},
    "autre": {MODE_CONFORT: 19, MODE_ECO: 17, MODE_HORS_GEL: 7},
}

# Paramètres par défaut
DEFAULT_UPDATE_INTERVAL = 300  # 5 minutes
DEFAULT_SECURITY_FACTOR = 1.3
DEFAULT_MIN_PREHEAT_TIME = 30  # minutes
DEFAULT_DERIVATIVE_WINDOW = 30  # minutes

# Événements calendrier
EVENT_ABSENCE = "absence"
EVENT_CONFORT = "confort"
```

-----

## Coordinator - Logique principale

Le `DataUpdateCoordinator` est le cœur du component :

```python
class ChauffageIntelligentCoordinator(DataUpdateCoordinator):
    """Coordonne les mises à jour et la logique."""

    def __init__(self, hass, config):
        self.calendar_entity = config["calendar"]
        self.presence_trackers = config["presence_trackers"]
        self.pieces = config["pieces"]
        self.security_factor = config["security_factor"]
        self.min_preheat_time = config["min_preheat_time"]

        # Historique températures pour dérivée
        self._temp_history: dict[str, list[tuple[datetime, float]]] = {}

        # Overrides manuels
        self._mode_overrides: dict[str, tuple[str, datetime | None]] = {}

    async def _async_update_data(self):
        """Mise à jour périodique."""

        # 1. Lire état calendrier
        calendar_events = await self._get_calendar_events()

        # 2. Calculer présence
        maison_occupee = self._compute_presence()

        # 3. Pour chaque pièce
        pieces_data = {}
        for piece_id, piece_config in self.pieces.items():

            # Lire température actuelle
            temp_actuelle = self._get_temperature(piece_config)

            # Calculer vitesse de chauffe
            vitesse = self._compute_derivative(piece_id, temp_actuelle)

            # Résoudre le mode
            mode, source = self._resolve_mode(
                piece_id,
                calendar_events,
                maison_occupee
            )

            # Calculer consigne
            consigne = piece_config["temperatures"][mode]

            # Calculer temps préchauffage
            temps_prechauffe = self._compute_preheat_time(
                temp_actuelle,
                consigne,
                vitesse
            )

            # Vérifier anticipation
            prechauffage_actif = self._check_preheat_trigger(
                piece_id,
                calendar_events,
                temps_prechauffe
            )

            # Si préchauffage anticipé, passer en confort maintenant
            if prechauffage_actif and mode == MODE_ECO:
                mode = MODE_CONFORT
                consigne = piece_config["temperatures"][MODE_CONFORT]
                source = "anticipation"

            # Appliquer la consigne au radiateur
            await self._set_radiator_temperature(
                piece_config["radiateur"],
                consigne
            )

            pieces_data[piece_id] = {
                "mode": mode,
                "source": source,
                "consigne": consigne,
                "temperature": temp_actuelle,
                "vitesse_chauffe": vitesse,
                "temps_prechauffage": temps_prechauffe,
                "prechauffage_actif": prechauffage_actif,
            }

        return {
            "maison_occupee": maison_occupee,
            "pieces": pieces_data,
        }
```

-----

## Gestion du fallback sonde

```python
def _get_temperature(self, piece_config: dict) -> float | None:
    """Récupère la température, avec fallback sur sonde radiateur."""

    # Essayer la sonde externe
    sonde_entity = piece_config.get("sonde")
    if sonde_entity:
        state = self.hass.states.get(sonde_entity)
        if state and state.state not in ("unknown", "unavailable"):
            return float(state.state)

    # Fallback : température du radiateur
    radiateur_entity = piece_config["radiateur"]
    state = self.hass.states.get(radiateur_entity)
    if state and state.attributes.get("current_temperature"):
        return float(state.attributes["current_temperature"])

    return None
```

-----

## Parsing événements calendrier

```python
def _parse_calendar_events(self, events: list) -> dict:
    """Parse les événements en cours."""

    result = {
        "absence": False,
        "confort_global": False,
        "confort_pieces": set(),
    }

    for event in events:
        summary = event.get("summary", "").lower().strip()

        if summary == "absence":
            result["absence"] = True

        elif summary == "confort":
            result["confort_global"] = True

        elif summary.startswith("confort "):
            # Extraire le nom de la pièce
            piece_name = summary[8:].strip()
            result["confort_pieces"].add(piece_name)

    return result
```

-----

## Notes d'implémentation

### Intervalle de mise à jour

- Défaut : 5 minutes
- Le calendrier HA est déjà mis à jour régulièrement
- Les device trackers émettent des events, pas besoin de polling fréquent

### Persistance

- Les overrides manuels sont perdus au redémarrage (acceptable)
- L'historique de température pour la dérivée est recalculé après redémarrage

### Thread safety

- Utiliser `async_add_executor_job` si calculs lourds
- Le coordinator gère déjà la synchronisation

### Logging

- Logger les changements de mode
- Logger les déclenchements d'anticipation
- Niveau DEBUG pour les calculs de dérivée

-----

## Tests à prévoir

1. **Mode resolution**
- Absence calendrier → Hors-gel
- Confort calendrier + personne home → Confort
- Confort calendrier + nobody home → Eco
- Confort Bureau → Bureau en Confort, autres en Eco
1. **Préchauffage**
- Event dans 2h, temps estimé 1h30 → pas encore
- Event dans 1h, temps estimé 1h30 → déclencher
1. **Fallback sonde**
- Sonde dispo → utiliser sonde
- Sonde indispo → utiliser radiateur
1. **Présence**
- 1 tracker home → occupé
- Tous trackers not_home → inoccupé

-----

## Évolutions futures possibles

- [ ] Boost salle de bain (mode temporaire 30 min)
- [ ] Prise en compte météo extérieure
- [ ] Détection fenêtre ouverte (chute rapide de température)
- [ ] Apprentissage automatique des vitesses de chauffe par conditions
- [ ] Multi-calendrier (un par pièce optionnellement)
- [ ] Intégration avec Scheduler component
