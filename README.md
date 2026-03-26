# Okovision - Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Intégration Home Assistant pour l'API locale Okovision. Permet de récupérer et afficher les données de capteurs Okovision directement dans Home Assistant.

## Fonctionnalités

- Connexion à l'API Okovision locale via API Key
- Découverte automatique de tous les capteurs exposés par l'API
- Support des types de capteurs : température, humidité, CO2, présence, luminosité, tension, courant, puissance, énergie, batterie
- Mise à jour configurable (10s à 3600s)
- Interface de configuration via l'UI Home Assistant

## Installation via HACS

1. Ouvrez HACS dans Home Assistant
2. Allez dans **Intégrations** → cliquez sur les 3 points en haut à droite → **Dépôts personnalisés**
3. Ajoutez l'URL : `https://github.com/nicouchot/okovision-ha` avec la catégorie **Integration**
4. Recherchez **Okovision** dans HACS et installez
5. Redémarrez Home Assistant

## Configuration

1. Allez dans **Paramètres** → **Appareils et services** → **Ajouter une intégration**
2. Recherchez **Okovision**
3. Renseignez :
   - **Adresse IP ou hostname** : l'adresse de votre serveur Okovision (ex: `192.168.1.100`)
   - **Port** : port de l'API (défaut : `8080`)
   - **Clé API** : votre clé d'authentification
   - **Intervalle de mise à jour** : en secondes (défaut : `30`)

## Format de l'API

L'intégration attend une API REST avec les endpoints suivants :

### `GET /api/status`
Vérification de connexion. Retourne HTTP 200 si ok.

### `GET /api/sensors`
Retourne la liste des capteurs :
```json
[
  {
    "id": "sensor_1",
    "name": "Température Bureau",
    "type": "temperature",
    "value": 21.5,
    "unit": "°C",
    "last_updated": "2024-01-01T12:00:00Z"
  }
]
```

Types supportés : `temperature`, `humidity`, `co2`, `pressure`, `illuminance`, `motion`, `occupancy`, `voltage`, `current`, `power`, `energy`, `battery`

### `GET /api/sensors/{id}`
Retourne un capteur spécifique.

## Authentification

L'API Key est transmise via le header HTTP :
```
Authorization: Bearer <api_key>
```

## Contribution

Les issues et pull requests sont les bienvenus sur [GitHub](https://github.com/nicouchot/okovision-ha).
