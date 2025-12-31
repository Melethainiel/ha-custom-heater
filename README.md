# Chauffage Intelligent

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Custom component Home Assistant pour gérer intelligemment des radiateurs Zigbee avec planification calendrier et anticipation du préchauffage.

## Fonctionnalités

- **Modes par pièce** : Confort, Eco, Hors-gel, Off
- **Planification via Google Calendar** : Contrôlez votre chauffage depuis votre calendrier
- **Détection de présence** : Passage automatique en mode Eco quand personne n'est à la maison
- **Anticipation du préchauffage** : Calcul automatique du temps nécessaire pour atteindre la température cible
- **Apprentissage automatique** : Le système apprend les vitesses de chauffe de chaque pièce pour améliorer les prédictions

## Installation

### HACS (recommandé)

1. Ouvrez HACS dans Home Assistant
2. Cliquez sur "Intégrations"
3. Cliquez sur les 3 points en haut à droite → "Dépôts personnalisés"
4. Ajoutez l'URL du dépôt avec la catégorie "Intégration"
5. Recherchez "Chauffage Intelligent" et installez
6. Redémarrez Home Assistant

### Installation manuelle

1. Téléchargez le dossier `custom_components/chauffage_intelligent`
2. Copiez-le dans votre dossier `config/custom_components/`
3. Redémarrez Home Assistant

## Configuration

### Prérequis

- **Calendrier Google** configuré dans Home Assistant
- **Device trackers** pour la détection de présence (app mobile HA, etc.)
- **Radiateurs** exposés comme entités `climate.*`
- **Sondes de température** (optionnel) comme entités `sensor.*`

### Ajout de l'intégration

1. Allez dans **Paramètres** → **Appareils et services**
2. Cliquez sur **Ajouter une intégration**
3. Recherchez "Chauffage Intelligent"
4. Suivez l'assistant de configuration :
   - Sélectionnez votre calendrier Google
   - Choisissez vos device trackers de présence
   - Ajoutez vos pièces une par une

### Événements calendrier

Créez des événements dans votre calendrier Google pour contrôler le chauffage :

| Événement | Effet |
|-----------|-------|
| `Absence` | Toute la maison en mode Hors-gel |
| `Confort` | Toute la maison en mode Confort |
| `Confort Bureau` | Seul le bureau en Confort |
| `Confort Chambre` | Seule la chambre en Confort |

> **Note** : Le matching est insensible à la casse (`confort bureau` = `Confort Bureau`)

## Logique de résolution du mode

Priorité (de la plus haute à la plus basse) :

1. Événement "Absence" → Hors-gel (forcé)
2. Personne à la maison → Eco
3. Événement "Confort {pièce}" → Confort pour cette pièce
4. Événement "Confort" → Confort global
5. Aucune condition → Eco (défaut)

## Entités créées

### Par pièce

| Entité | Description |
|--------|-------------|
| `climate.chauffage_{piece}` | Contrôle principal |
| `sensor.{piece}_mode_calcule` | Mode actuel |
| `sensor.{piece}_temperature_cible` | Consigne en °C |
| `sensor.{piece}_temps_prechauffage` | Minutes estimées |
| `sensor.{piece}_vitesse_chauffe` | °C/h actuel |
| `binary_sensor.{piece}_prechauffage_actif` | Anticipation en cours |

### Globales

| Entité | Description |
|--------|-------------|
| `binary_sensor.chauffage_maison_occupee` | Présence maison |
| `sensor.chauffage_mode_global` | Mode dominant |

## Services

### `chauffage_intelligent.set_mode`

Force un mode pour une pièce.

```yaml
service: chauffage_intelligent.set_mode
data:
  piece: bureau
  mode: confort  # confort | eco | hors_gel | off
  duree: 120     # minutes (optionnel)
```

### `chauffage_intelligent.reset_mode`

Annule l'override manuel.

```yaml
service: chauffage_intelligent.reset_mode
data:
  piece: bureau  # optionnel, toutes les pièces si omis
```

### `chauffage_intelligent.refresh`

Force un recalcul immédiat.

```yaml
service: chauffage_intelligent.refresh
```

## Températures par défaut

| Type de pièce | Confort | Eco | Hors-gel |
|---------------|---------|-----|----------|
| Salon | 20°C | 17°C | 7°C |
| Chambre | 18°C | 16°C | 7°C |
| Chambre enfant | 19°C | 17°C | 7°C |
| Bureau | 19°C | 17°C | 7°C |
| Salle de bain | 22°C | 17°C | 7°C |

## Anticipation du préchauffage

Le système calcule automatiquement le temps nécessaire pour atteindre la température cible en se basant sur :

- La température actuelle
- La vitesse de chauffe mesurée (°C/h)
- Un facteur de sécurité configurable (défaut: 1.3)

Si un événement "Confort" est prévu dans le calendrier, le préchauffage démarre automatiquement pour que la température cible soit atteinte à l'heure de l'événement.

## Apprentissage automatique

Le système apprend automatiquement les caractéristiques thermiques de chaque pièce :

- **Collecte** : Pendant les phases de chauffage, le système enregistre la vitesse de chauffe avec les conditions (heure, température extérieure)
- **Prédiction** : Les estimations sont pondérées selon la similarité avec les conditions actuelles
- **Persistance** : Les données sont sauvegardées dans `.storage/chauffage_intelligent_learned_rates.json`

### Attributs exposés

| Attribut | Description |
|----------|-------------|
| `vitesse_apprise` | Vitesse de chauffe prédite (°C/h) |
| `learning_samples` | Nombre d'observations enregistrées |
| `learning_avg_rate` | Vitesse moyenne apprise |

L'apprentissage nécessite au minimum 5 observations avant d'utiliser les prédictions.

## Développement

### Tests

```bash
pip install -r requirements-dev.txt
pytest tests/
```

### Structure

```
custom_components/chauffage_intelligent/
├── __init__.py       # Setup et services
├── coordinator.py    # Logique centrale
├── climate.py        # Entités Climate
├── sensor.py         # Entités Sensor
├── binary_sensor.py  # Binary Sensors
├── config_flow.py    # UI de configuration
└── const.py          # Constantes
```

## Licence

MIT License - Voir [LICENSE](LICENSE)
