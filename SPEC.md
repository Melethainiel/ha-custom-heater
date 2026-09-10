# Chauffage Intelligent — Spécifications

## Résumé

Custom component Home Assistant pilotant des radiateurs à partir d'un **planning
hebdomadaire intégré**, édité depuis un panneau dédié.

Principe directeur : **une température par plage horaire**, appliquée de façon
déterministe. Aucune dépendance externe, aucune prédiction, aucun apprentissage.

Version 1.0.0 — remplace l'architecture 0.x basée sur Google Calendar, la détection de
présence et l'anticipation de préchauffage.

---

## Contexte technique

### Matériel visé

- **Radiateurs** : Thermor Bilbao 4 en Zigbee (ZHA), et plus généralement toute entité
  `climate` acceptant `set_temperature`
- **Pas de fil pilote** : contrôle uniquement via la consigne
- **Sondes externes** : capteurs de température par pièce, déjà présents dans HA
- **Fallback** : si la sonde externe est indisponible, la sonde interne du radiateur

### Dépendances HA

`http`, `frontend`, `panel_custom`, `websocket_api`. Home Assistant ≥ 2024.11.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        PANNEAU (frontend/panel.js)               │
│  Grille 7 × 48 · palette · copie jour/semaine/pièce              │
└────────────────────────────┬─────────────────────────────────────┘
                             │ websocket
┌────────────────────────────▼─────────────────────────────────────┐
│                    websocket_api.py                              │
│  rooms · schedule/get · schedule/set · schedule/copy             │
│  override/set                                                    │
└────────────────────────────┬─────────────────────────────────────┘
                             │
        ┌────────────────────▼────────────────────┐
        │              COORDINATOR                │
        │  1. lire le planning de la pièce        │
        │  2. résoudre la consigne                │
        │  3. l'appliquer aux radiateurs          │
        │  4. armer un timer sur la transition    │
        └──────┬──────────────────────┬───────────┘
               │                      │
    ┌──────────▼──────────┐  ┌────────▼──────────────┐
    │  storage.py (Store) │  │  schedule.py          │
    │  plannings persistés│  │  fonctions pures      │
    └─────────────────────┘  └───────────────────────┘
               │
    ┌──────────▼──────────────────────────────────────┐
    │  ENTITÉS (une par pièce, groupées en device)    │
    │  climate · sensor ×2 · select                   │
    └──────────┬──────────────────────────────────────┘
               │
    ┌──────────▼──────────┐
    │  RADIATEURS         │
    │  set_temperature    │
    │  set_hvac_mode      │
    └─────────────────────┘
```

---

## Modèle de données

### Config entry (`entry.data`, VERSION 2)

```python
{
  "update_interval": 300,             # secondes
  "pieces": {
    "<area_id>": {
      "name": "Salon",
      "area_id": "salon",
      "type": "salon",
      "radiateurs": ["climate.bilbao_salon"],
      "sonde": "sensor.temperature_salon",       # ou None
      "temperatures": {"confort": 20.0, "eco": 17.0, "hors_gel": 7.0},
      "offset": 0.0,
    }
  }
}
```

`temperatures` est une **palette** : trois températures nommées réutilisées par le panneau
et par les presets. Elle ne définit aucun horaire.

### Plannings (`helpers.storage.Store`, clé `chauffage_intelligent.schedules`, v1)

Stockés hors du config entry : ils sont édités fréquemment depuis le panneau, sans
rechargement de l'intégration.

```json
{
  "schedules": {
    "salon": [
      {"day": 0, "start": "07:00", "end": "09:00", "temperature": 20.0},
      {"day": 0, "start": "17:30", "end": "22:00", "temperature": 20.0}
    ]
  }
}
```

- `day` : 0 = lundi … 6 = dimanche (aligné sur `datetime.weekday()`)
- `start` inclusif, `end` exclusif, `"24:00"` autorisé pour la fin de journée
- Les créneaux ne traversent jamais minuit : ils sont découpés à la normalisation

---

## Module `schedule.py`

Fonctions pures, sans dépendance à `hass`, donc entièrement testables unitairement.

| Fonction | Rôle |
|----------|------|
| `parse_time` / `format_time` | `"HH:MM"` ↔ minutes depuis minuit |
| `normalize_slots(slots)` | Valide, trie, découpe à minuit, résout les chevauchements, fusionne les créneaux adjacents de même température |
| `find_slot(slots, when)` | Le créneau couvrant `when`, ou `None` |
| `resolve_temperature(slots, when)` | La température à `when`, ou `None` |
| `next_transition(slots, when)` | Le prochain instant où la consigne change (sur 7 jours) |
| `slots_to_grid(slots)` | Grille 7 × 48 pour le panneau |
| `grid_to_slots(grid)` | Compression inverse des cellules contiguës |
| `default_schedule(temperatures)` | Planning de départ d'une nouvelle pièce |

### Règles de normalisation

- **Chevauchement** : le créneau défini en dernier gagne. Un créneau 07:00-12:00 à 20 °C
  suivi d'un 09:00-10:00 à 16 °C donne trois créneaux : 20 / 16 / 20.
- **Minuit** : un créneau 22:00-06:00 du lundi devient lundi 22:00-24:00 + mardi 00:00-06:00.
  Un créneau dimanche 23:00-01:00 déborde sur lundi.
- **Adjacence** : deux créneaux qui se touchent à la même température fusionnent, ce qui
  évite des transitions qui ne changeraient rien.
- Un créneau de longueur nulle est écarté ; un `day` hors [0, 6], une heure hors bornes ou
  une température non numérique lèvent `ScheduleError`.

---

## Résolution de la consigne

```
1. Pièce éteinte (hvac_mode: off)   → temperatures["hors_gel"]   source: off
2. Surcharge manuelle active        → température forcée          source: manuel
3. Créneau du planning              → température du créneau      source: planning
4. Défaut                           → temperatures["eco"]         source: defaut
```

### Surcharges manuelles

Stockées en mémoire : `{piece_id: (temperature, expiry | None)}`.

- Avec une durée explicite : expire après N minutes.
- Sans durée : expire à la **prochaine transition du planning** (`next_transition`), ce qui
  donne le comportement attendu d'un thermostat — on pousse la consigne maintenant, le
  planning reprend la main au créneau suivant.
- Sans planning du tout : l'expiration est `None`, la surcharge tient jusqu'à un `reset`.

Les surcharges sont perdues au redémarrage (comportement accepté).

---

## Application aux radiateurs

Pour chaque radiateur de la pièce :

```python
state = hass.states.get(entity_id)
if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
    log.warning(...); continue                      # (a)

target = clamp(consigne + offset,
               state.attributes["min_temp"],
               state.attributes["max_temp"])        # (b)

if state.state == HVACMode.OFF:
    await climate.set_hvac_mode(entity_id, HEAT)    # (c)

if abs(state.attributes["temperature"] - target) >= 0.1:
    await climate.set_temperature(entity_id, target)  # (d)
```

Justification de chaque point, par rapport à la v1 qui envoyait la consigne sans condition :

- **(a)** un radiateur injoignable ne reçoit rien : l'échec était auparavant avalé
  silencieusement par un `except`.
- **(b)** une consigne hors de la plage du radiateur (7 °C sur un appareil dont le minimum
  est 10 °C) était refusée sans que rien ne le signale.
- **(c)** un radiateur en `off` **ignore** la consigne : c'est la cause principale des
  consignes « qui ne prenaient pas ».
- **(d)** n'écrire que ce qui change évite de saturer le réseau Zigbee, et rend le système
  auto-réparateur : la comparaison se refait à chaque cycle, donc un envoi non pris en
  compte est réémis au suivant, sans logique de retry dédiée.

Une exception sur un radiateur est journalisée et n'interrompt pas les autres.

### Décalage de consigne (`offset`)

`setpoint_envoyé = consigne + offset`, défaut `0.0` (soit une consigne directe). Sert à
compenser l'écart entre la sonde interne du radiateur et la température réelle de la pièce.

---

## Déclenchement des recalculs

| Source | Rôle |
|--------|------|
| `async_track_point_in_time` sur `next_transition()` | Le changement de créneau tombe à la minute pile |
| `async_track_state_change_event` sur les radiateurs | Réapplication si la consigne dérive, si le radiateur est éteint, ou dès qu'il revient d'une coupure |
| `update_interval` (300 s par défaut) | Filet de sécurité |

Le timer de transition est réarmé à chaque cycle : il ne s'en empile jamais deux. Le listener
d'état ignore les changements qui ne portent ni sur l'état ni sur la consigne (un simple
relevé de température, par exemple).

---

## Entités

Une pièce = un `device` Home Assistant, identifié par `(DOMAIN, piece_id)`.

| Entity ID | Type | Description |
|-----------|------|-------------|
| `climate.chauffage_{piece}` | Climate | Consigne, marche/arrêt, presets |
| `sensor.{piece}_temperature_cible` | Sensor | Consigne résolue (°C) |
| `sensor.{piece}_source_consigne` | Sensor (enum) | `planning` / `manuel` / `defaut` / `off` |
| `select.{piece}_mode` | Select | Planning / Confort / Éco / Hors-gel |

### Entité climate

- `hvac_modes` : `HEAT`, `OFF` — `OFF` bascule la pièce en hors-gel
- `hvac_action` : `HEATING` si la pièce est sous sa consigne, `IDLE` sinon, `OFF` si éteinte
- `preset_modes` : `Planning`, `Confort`, `Éco`, `Hors-gel`
- `async_set_temperature` crée une surcharge jusqu'à la prochaine transition
- Attributs : `source_consigne`, `creneau_actuel` (`"07:00-09:00"`), `prochain_changement`
  (ISO 8601), `offset`, `radiateur_entities`, `sonde_entity`, `type_piece`

Le preset affiché est `Planning` dès qu'aucune surcharge n'est active, ou qu'une surcharge
porte une température absente de la palette.

---

## API WebSocket

| Commande | Entrée | Sortie |
|----------|--------|--------|
| `chauffage_intelligent/rooms` | — | pièces + état courant + géométrie de la grille |
| `chauffage_intelligent/schedule/get` | `piece_id` | `{slots, grid}` |
| `chauffage_intelligent/schedule/set` | `piece_id`, `grid` (7 × 48) | `{slots, grid}` normalisés |
| `chauffage_intelligent/schedule/copy` | `from_piece`, `to_pieces` | `{copied_to}` |
| `chauffage_intelligent/override/set` | `piece_id`, `temperature` (ou `null`), `duree?` | `{}` |

`schedule/set` reçoit la **grille** : le panneau n'a pas à compresser les créneaux, la
conversion (`grid_to_slots`) et la normalisation se font côté Python, donc sont testables.
La forme de la grille est validée par voluptuous avant d'atteindre le store.

---

## Panneau

Web component vanilla (`frontend/panel.js`) : aucune dépendance, aucune étape de build, le
fichier est servi tel quel via `async_register_static_paths`, et enregistré dans la barre
latérale par `panel_custom.async_register_panel` sous `/chauffage`.

- Grille 7 colonnes × 48 lignes (pas de 30 min), peinture au clic-glissé, y compris tactile
  (hit-testing par `elementFromPoint`, avec repli sur `event.target`)
- Palette : Confort / Éco / Hors-gel de la pièce, valeur libre, et « hors plage »
- Remplir une journée, copier une journée sur la semaine, copier vers une autre pièce
- Édition locale : un seul `schedule/set` à la validation, avec Annuler
- Couleurs par température (dégradé bleu → rouge) et variables CSS HA pour suivre le thème

L'URL du module porte un paramètre de version (`?v=`) pour éviter qu'un navigateur ne serve
une version périmée après une mise à jour.

---

## Config flow

### Étape 1 — général

`update_interval` uniquement.

### Étape 2 — ajout d'une pièce

Zone (parmi celles contenant une entité `climate`), puis type de pièce, radiateurs, sonde,
palette de trois températures, et décalage de consigne. Une pièce nouvellement créée reçoit
`default_schedule()`.

### Options

Ajouter / modifier / supprimer une pièce, modifier les paramètres. Supprimer une pièce purge
également son planning dans le `Store`. Les plannings s'éditent dans le panneau, pas ici.

---

## Migration du config entry v1 → v2

`async_migrate_entry` :

1. Retire `calendar`, `presence_trackers`, `security_factor`, `min_preheat_time`,
   `derivative_window`.
2. Ajoute `offset: 0.0` à chaque pièce.
3. Crée un planning par défaut pour chaque pièce existante.
4. Supprime `.storage/chauffage_intelligent_learned_rates.json`.
5. Passe l'entrée en version 2.

---

## Services

| Service | Champs |
|---------|--------|
| `set_temperature` | `piece`, `temperature`, `duree?` |
| `reset` | `piece?` |
| `refresh` | — |
| `set_schedule` | `piece`, `slots` |

`set_temperature`, `reset` et `set_schedule` lèvent `ServiceValidationError` sur une pièce
inconnue, de façon à ce que l'erreur remonte dans l'interface.

---

## Tests

| Fichier | Couvre |
|---------|--------|
| `test_schedule.py` | Normalisation, résolution aux bornes, transitions (dont dimanche → lundi), aller-retour grille |
| `test_apply.py` | Écriture conditionnelle, rallumage, bornage, indisponibilité, offset, réémission |
| `test_coordinator.py` | Priorités de résolution, expiration des surcharges, lecture de température, boucle de mise à jour, listeners |
| `test_storage.py` | Chargement, normalisation, planning corrompu, purge |
| `test_websocket_api.py` | Les cinq commandes, validation de la grille |
| `test_climate.py`, `test_sensor.py`, `test_select.py` | Entités |
| `test_config_flow.py` | Config flow et options |
| `test_init.py` | Setup, déchargement, migration, services |
| `test_panel.py` | Enregistrement du panneau, présence du fichier statique |

---

## Évolutions possibles

- [ ] Détection de fenêtre ouverte (chute rapide de température)
- [ ] Boost temporaire salle de bain depuis le panneau
- [ ] Import/export du planning en YAML depuis le panneau
- [ ] Historique des consignes appliquées
