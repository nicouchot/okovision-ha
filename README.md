# OkoVision – Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Intégration Home Assistant pour le système de monitoring chaudière à pellets **OkoVision**.
Se connecte à `ha_api.php` via polling REST.

---

## Entités exposées

### Capteurs live – Silo & Cendrier
> Mis à jour toutes les N secondes (configurable)

| Entité | Description | Unité |
|--------|-------------|-------|
| Silo – Pellets restants | Stock estimé | kg |
| Silo – Niveau | % de remplissage | % |
| Silo – Capacité totale | Capacité max du silo | kg |
| Silo – Dernier remplissage | Date du dernier remplissage | date |
| Cendrier – Capacité restante | Avant saturation | kg |
| Cendrier – Niveau de remplissage | % de remplissage | % |
| Cendrier – Capacité totale | Capacité max du cendrier | kg |
| Cendrier – Dernier vidage | Date du dernier vidage | date |
| Dernier ramonage | Date du dernier ramonage (SWEEP) | date |
| Dernière maintenance | Date de la dernière maintenance (MAINT) | date |

### Capteurs journaliers J-1 – Données confirmées
> Mis à jour toutes les 30 min – données disponibles après ~5h du matin pour la veille

| Entité | Description | Unité |
|--------|-------------|-------|
| Température extérieure max (J-1) | Temp. max de la veille | °C |
| Température extérieure min (J-1) | Temp. min de la veille | °C |
| Consommation pellets (J-1) | Pellets brûlés (chauffage) | kg |
| Consommation pellets ECS (J-1) | Pellets brûlés (eau chaude) | kg |
| Énergie produite (J-1) | kWh calculés (kg × PCI × rendement) | kWh |
| Cycles chaudière (J-1) | Nombre d'allumages | cycles |
| DJU (J-1) | Degrés-Jours Unifiés | DJU |

> Les capteurs journaliers utilisent `last_reset = minuit de J-1` afin que le
> **tableau de bord Énergie** de HA attribue les valeurs au bon jour.

### Capteur binaire

| Entité | Description | Classe |
|--------|-------------|--------|
| Cendrier – À vider | `true` quand le cendrier est plein | `problem` |

---

## Installation via HACS

1. HACS → **Intégrations** → ⋮ → **Dépôts personnalisés**
2. Ajoutez `https://github.com/nicouchot/okovision-ha` (catégorie : **Integration**)
3. Installez **OkoVision** et redémarrez Home Assistant

## Configuration

**Paramètres** → **Appareils et services** → **Ajouter une intégration** → **OkoVision**

| Champ | Description | Exemple |
|-------|-------------|---------|
| URL de l'API | URL complète vers `ha_api.php` | `http://192.168.1.100/ha_api.php` |
| Token | 12 premiers caractères du TOKEN serveur | `a1b2c3d4e5f6` |
| Intervalle de mise à jour | Polling live en secondes (min 30) | `60` |

---

## API utilisée

| Action | Utilisation | Fréquence |
|--------|-------------|-----------|
| `action=today` | Silo + cendrier live | Toutes les N secondes |
| `action=daily&date=hier` | Résumé J-1 confirmé | Toutes les 30 min |
| `action=status` | Test de connexion au setup | 1× au démarrage |
