# Chauffage Intelligent

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Custom component Home Assistant pour piloter des radiateurs (Zigbee ou autres) à partir
d'un **planning hebdomadaire intégré**, édité depuis un panneau dédié dans la barre latérale.

Une température par plage horaire. Pas de calendrier externe, pas de prédiction.

## Fonctionnalités

- **Planning hebdomadaire intégré** : une grille 7 jours × 48 créneaux de 30 min par pièce,
  peinte à la souris ou au doigt depuis le panneau « Chauffage ».
- **Une température par créneau** : la consigne est celle du créneau courant, point.
- **Application fiable de la consigne** : le radiateur est rallumé s'il est éteint, la
  consigne est bornée à sa plage, et n'est réécrite que si elle a réellement changé.
- **Surcharge manuelle** : forcez une température depuis l'entité climate ; elle rend la
  main au planning au créneau suivant.
- **Décalage de consigne par pièce** : si le radiateur régule au-dessus ou en dessous de la
  température réelle de la pièce.

## Installation

### HACS (recommandé)

1. HACS → Intégrations → ⋮ → Dépôts personnalisés
2. Ajoutez l'URL du dépôt, catégorie « Intégration »
3. Installez « Chauffage Intelligent », puis redémarrez Home Assistant

### Manuelle

Copiez `custom_components/chauffage_intelligent` dans votre dossier `config/custom_components/`,
puis redémarrez Home Assistant.

> Home Assistant 2024.11 ou plus récent est requis.

## Configuration

### Prérequis

- Des radiateurs exposés comme entités `climate.*`, rattachés à une **zone** (area)
- Optionnel mais recommandé : une sonde de température par pièce (`sensor.*` avec
  `device_class: temperature`)

### Ajout de l'intégration

1. **Paramètres** → **Appareils et services** → **Ajouter une intégration**
2. Recherchez « Chauffage Intelligent »
3. Réglez l'intervalle de vérification, puis ajoutez vos pièces une par une :
   - Zone (les zones contenant une entité `climate` sont proposées)
   - Type de pièce, radiateurs, sonde de température
   - Palette de températures : Confort / Éco / Hors-gel
   - Décalage de consigne (laissez à 0 pour commencer)

Chaque pièce reçoit un planning de départ (semaine 07h-09h et 17h30-22h en confort,
week-end 08h-22h) que vous ajustez ensuite dans le panneau.

## Le panneau « Chauffage »

Un lien **Chauffage** apparaît dans la barre latérale après l'installation.

- **Onglets** en haut : une pièce à la fois, avec sa température actuelle, sa consigne, la
  source de cette consigne et le prochain changement.
- **Palette** : choisissez Confort, Éco, Hors-gel, une valeur libre, ou « Hors plage ».
- **Grille** : cliquez-glissez pour peindre les créneaux. Cliquez sur un nom de jour pour
  remplir la journée entière, sur ⇥ pour copier cette journée sur toute la semaine.
- **Copier vers…** duplique le planning de la pièce courante vers une autre.
- Rien n'est appliqué avant **Enregistrer**.

Un créneau laissé « hors plage » retombe sur la température **Éco** de la pièce.

## Résolution de la consigne

Priorité, de la plus haute à la plus basse :

| # | Condition | Consigne |
|---|-----------|----------|
| 1 | Pièce éteinte (`hvac_mode: off`) | Hors-gel |
| 2 | Surcharge manuelle active | La température forcée |
| 3 | Un créneau du planning couvre l'instant présent | La température du créneau |
| 4 | Sinon | Éco |

La consigne est recalculée :

- à chaque changement de créneau, **à la minute pile** ;
- à chaque changement d'état d'un radiateur (consigne modifiée à la main, radiateur éteint,
  radiateur qui revient après une coupure) ;
- toutes les 5 minutes par défaut, en filet de sécurité.

## Application aux radiateurs

Pour chaque radiateur de la pièce, à chaque recalcul :

1. Radiateur `unavailable` ou inexistant → on n'écrit pas, un avertissement est journalisé.
2. `consigne + décalage`, borné à `min_temp` / `max_temp` du radiateur.
3. Radiateur en `off` → `climate.set_hvac_mode` vers `heat` (un radiateur éteint ignore la
   consigne).
4. `climate.set_temperature` **uniquement** si la valeur diffère de plus de 0,1 °C de celle
   que le radiateur annonce.

Le point 4 évite de saturer le réseau Zigbee, et rend le système auto-réparateur : une
consigne qui n'a pas été prise en compte est réémise au cycle suivant.

### Décalage de consigne

Le radiateur régule sur **sa** sonde interne, souvent plus chaude que la pièce. Si votre
salon plafonne à 18 °C alors que la consigne est à 20 °C, réglez un décalage de `+2` dans
les options de la pièce : le composant enverra 22 °C au radiateur pour obtenir 20 °C dans
la pièce. Laissé à `0`, le comportement est celui d'une consigne directe.

## Entités créées

Une pièce = un appareil Home Assistant regroupant :

| Entité | Description |
|--------|-------------|
| `climate.chauffage_{piece}` | Contrôle principal : consigne, marche/arrêt, presets |
| `sensor.{piece}_temperature_cible` | Consigne résolue en °C |
| `sensor.{piece}_source_consigne` | `planning` / `manuel` / `defaut` / `off` |
| `select.{piece}_mode` | Planning / Confort / Éco / Hors-gel |

### Presets de l'entité climate

| Preset | Effet |
|--------|-------|
| Planning | Annule la surcharge, le planning reprend la main |
| Confort / Éco / Hors-gel | Force la valeur correspondante de la palette de la pièce |

Régler directement la température sur l'entité climate crée une surcharge jusqu'au prochain
créneau. `hvac_mode: off` bascule la pièce en hors-gel.

## Services

### `chauffage_intelligent.set_temperature`

```yaml
action: chauffage_intelligent.set_temperature
data:
  piece: bureau
  temperature: 21
  duree: 120   # minutes, optionnel (défaut : jusqu'au prochain créneau)
```

### `chauffage_intelligent.reset`

```yaml
action: chauffage_intelligent.reset
data:
  piece: bureau   # optionnel, toutes les pièces si omis
```

### `chauffage_intelligent.set_schedule`

Remplace le planning d'une pièce. Utile pour les automatisations et les sauvegardes ;
l'édition courante se fait dans le panneau.

```yaml
action: chauffage_intelligent.set_schedule
data:
  piece: bureau
  slots:
    - day: 0        # 0 = lundi … 6 = dimanche
      start: "07:00"
      end: "09:00"
      temperature: 20
```

### `chauffage_intelligent.refresh`

Force un recalcul et une réapplication immédiate.

## Températures par défaut

| Type de pièce | Confort | Éco | Hors-gel |
|---------------|---------|-----|----------|
| Salon | 20 °C | 17 °C | 7 °C |
| Chambre | 18 °C | 16 °C | 7 °C |
| Chambre enfant | 19 °C | 17 °C | 7 °C |
| Bureau | 19 °C | 17 °C | 7 °C |
| Salle de bain | 22 °C | 17 °C | 7 °C |

Ces valeurs ne sont qu'une palette de départ : seules les températures posées dans le
planning déterminent le chauffage.

## Migration depuis la version 1.x

La mise à jour est automatique au démarrage :

- Les pièces, radiateurs, sondes et palettes de températures sont conservés.
- Le calendrier Google, les device trackers de présence, l'anticipation de préchauffage et
  l'apprentissage des vitesses de chauffe sont supprimés, ainsi que le fichier
  `.storage/chauffage_intelligent_learned_rates.json`.
- Chaque pièce reçoit un planning de départ, à ajuster dans le panneau.

Entités disparues : `binary_sensor.chauffage_maison_occupee`,
`binary_sensor.{piece}_prechauffage_actif`, `sensor.chauffage_mode_global`,
`sensor.{piece}_mode_calcule`, `sensor.{piece}_temps_prechauffage`,
`sensor.{piece}_vitesse_chauffe`. Les services `set_mode` et `reset_mode` sont remplacés par
`set_temperature` et `reset`.

## Développement

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/
.venv/bin/ruff check custom_components tests
```

### Structure

```
custom_components/chauffage_intelligent/
├── __init__.py         # Setup, migration, services
├── coordinator.py      # Résolution et application des consignes
├── schedule.py         # Modèle de planning (fonctions pures)
├── storage.py          # Persistance des plannings
├── websocket_api.py    # API du panneau
├── panel.py            # Enregistrement du panneau
├── frontend/panel.js   # Éditeur de planning
├── entity.py           # Entité de base
├── climate.py          # Entités Climate
├── sensor.py           # Entités Sensor
├── select.py           # Entités Select
├── config_flow.py      # UI de configuration
└── const.py            # Constantes
```

## Licence

MIT License — voir [LICENSE](LICENSE)
