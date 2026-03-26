# OkoVision – Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Intégration Home Assistant pour le système de monitoring chaudière à pellets **OkoVision**.
Se connecte à l'API locale `ha_api.php` via polling REST.

## Entités exposées

### Capteurs (sensor)

| Entité | Description | Unité |
|--------|-------------|-------|
| Température extérieure max | Température max du jour | °C |
| Température extérieure min | Température min du jour | °C |
| Consommation pellets du jour | Pellets brûlés (chauffage) | kg |
| Consommation pellets ECS du jour | Pellets brûlés (eau chaude) | kg |
| Énergie produite du jour | Énergie calculée (kg × PCI × rendement) | kWh |
| Cycles chaudière du jour | Nombre d'allumages | cycles |
| DJU du jour | Degrés-Jours Unifiés | DJU |
| Silo – Pellets restants | Stock estimé dans le silo | kg |
| Silo – Niveau | Pourcentage de remplissage | % |
| Silo – Capacité totale | Capacité max du silo | kg |
| Cendrier – Capacité restante | Capacité avant vidage | kg |
| Cendrier – Niveau de remplissage | Pourcentage de remplissage | % |

### Capteurs binaires (binary_sensor)

| Entité | Description | Classe |
|--------|-------------|--------|
| Cendrier – À vider | `true` quand le cendrier est plein | `problem` |

## Installation via HACS

1. Ouvrez HACS → **Intégrations** → ⋮ → **Dépôts personnalisés**
2. Ajoutez `https://github.com/nicouchot/okovision-ha` (catégorie : **Integration**)
3. Installez **OkoVision** et redémarrez Home Assistant

## Configuration

1. **Paramètres** → **Appareils et services** → **Ajouter une intégration** → **OkoVision**
2. Renseignez :
   - **URL de l'API** : URL complète vers `ha_api.php`
     (ex: `http://192.168.1.100/okovision/ha_api.php`)
   - **Token** : les **12 premiers caractères** de la constante `TOKEN` définie dans `config.php` côté serveur
   - **Intervalle de mise à jour** : en secondes (min 30, défaut 60)

## API – Endpoints utilisés

| Action | Endpoint | Utilisation |
|--------|----------|-------------|
| `today` | `?token=XXXX&action=today` | Polling principal (données live + silo + cendrier) |
| `status` | `?token=XXXX&action=status` | Test de connexion au setup |

### Authentification

Le token est passé en paramètre GET `?token=`. Il correspond aux 12 premiers caractères
de la constante `TOKEN` définie dans `config.php` du serveur OkoVision.

## Contribution

Issues et pull requests bienvenus sur [GitHub](https://github.com/nicouchot/okovision-ha).
