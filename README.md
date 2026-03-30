# OkoVision – Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![version](https://img.shields.io/github/v/release/nicouchot/okovision-ha)

Intégration Home Assistant pour le système de monitoring chaudière à pellets **OkoVision**.
Se connecte à `ha_api.php` via polling REST local.

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

## Entités exposées

### 🟢 Capteurs live – Silo & Cendrier
> Mis à jour à chaque cycle de polling (intervalle configurable, min 30 s).
> Source : `action=today`

| Entité | Description | Unité | Type |
|--------|-------------|-------|------|
| Silo – Pellets restants | Stock estimé depuis le dernier remplissage | kg | Mesure |
| Silo – Capacité totale | Capacité maximale configurée du silo | kg | Mesure |
| Silo – Niveau | Taux de remplissage en pourcentage | % | Mesure |
| Silo – Dernier remplissage | Date de la dernière livraison de pellets | — | Date |
| Cendrier – Capacité restante | Volume disponible avant saturation | kg | Mesure |
| Cendrier – Capacité totale | Capacité maximale configurée du cendrier | kg | Mesure |
| Cendrier – Niveau de remplissage | Taux de remplissage en pourcentage | % | Mesure |
| Cendrier – Dernier vidage | Date du dernier vidage des cendres | — | Date |
| Dernier ramonage | Date du dernier ramonage (événement SWEEP) | — | Date |
| Dernière maintenance | Date de la dernière maintenance (événement MAINT) | — | Date |

### 🔴 Capteur binaire
| Entité | Description | État |
|--------|-------------|------|
| Cendrier – À vider | Alerte quand la capacité restante est ≤ 0 | `problem` |

---

### 📅 Capteurs journaliers J-1 – Données confirmées
> Mis à jour toutes les heures. L'API retourne `is_new: true` dès que les données
> de la veille sont disponibles. Tant que `is_new: false`, le coordinator conserve
> le cache et retente au prochain cycle (pas d'attente fixe).
> Source : `action=daily&date=hier`

#### Consommation journalière

| Entité | Description | Unité | State class |
|--------|-------------|-------|-------------|
| Consommation pellets (J-1) | Pellets brûlés pour le chauffage | kg | `total` |
| Consommation pellets ECS (J-1) | Pellets brûlés pour l'eau chaude sanitaire | kg | `total` |
| Énergie produite (J-1) | Énergie calculée : kg × PCI × rendement | kWh | `total` |
| Cycles chaudière (J-1) | Nombre d'allumages dans la journée | cycles | `total` |
| DJU (J-1) | Degrés-Jours Unifiés de la veille | DJU | Mesure |

#### Températures

| Entité | Description | Unité | State class |
|--------|-------------|-------|-------------|
| Température extérieure max (J-1) | Température maximale relevée la veille | °C | Mesure |
| Température extérieure min (J-1) | Température minimale relevée la veille | °C | Mesure |

#### Cumulatifs (depuis le premier enregistrement)

| Entité | Description | Unité | State class |
|--------|-------------|-------|-------------|
| Consommation cumulée pellets | Total pellets brûlés depuis l'origine | kg | `total_increasing` |
| Énergie cumulée | Total kWh produits depuis l'origine | kWh | `total_increasing` |
| Cycles cumulés | Total allumages depuis l'origine | cycles | `total_increasing` |
| Coût cumulé chauffage | Coût total calculé : ∑(kWh/j × €/kWh/j) | EUR | `total_increasing` |

#### Prix

| Entité | Description | Unité | State class |
|--------|-------------|-------|-------------|
| Prix pellets (€/kg) | Prix au kg issu de la dernière livraison (FIFO) | EUR/kg | Mesure |
| Prix énergie (€/kWh) | Prix par kWh calculé depuis le prix pellets | EUR/kWh | Mesure |

> Les capteurs `total` utilisent `last_reset = minuit de J-1` pour que le
> **tableau de bord Énergie** attribue les valeurs au bon jour.

---

## 🗑️ Réinitialisation de l'historique (`okovision.reset_history`)

Supprime toutes les statistiques OkoVision du recorder HA (statistiques externes
`okovision:*` et historique des entités). N'efface pas les états actuels.

À utiliser avant un ré-import complet ou pour repartir de zéro.

1. **Outils de développement** → onglet **Actions**
2. Rechercher `okovision.reset_history` et exécuter (aucun paramètre)

---

## 📊 Import de l'historique (`okovision.import_history`)

L'intégration propose un service permettant de **remplir rétroactivement** les statistiques
Home Assistant avec jusqu'à 4 ans de données OkoVision.

### Pourquoi ce service ?

Par défaut, HA ne connaît que les données depuis l'installation de l'intégration.
Ce service injecte l'historique complet dans le **recorder** de HA, ce qui permet de :
- Visualiser des courbes de consommation sur plusieurs années
- Alimenter le tableau de bord **Énergie** avec les données historiques
- Calculer des bilans annuels / saisonniers

### Capteurs alimentés par l'import

#### Consommation & énergie

| Capteur | Contenu importé | Méthode |
|---------|----------------|---------|
| Hier – Consommation pellets | Conso journalière kg | `conso_kg` mensuel |
| Hier – Consommation pellets ECS | Conso journalière kg ECS | `conso_ecs_kg` mensuel |
| Hier – Énergie produite | Énergie journalière kWh | `conso_kwh` mensuel |
| Hier – Cycles chaudière | Allumages du jour | `nb_cycle` mensuel |
| Hier – DJU | Degrés-Jours Unifiés | `dju` mensuel |
| Cumul – Énergie | Cumul kWh depuis l'origine | `cumul_kwh` mensuel |
| Cumul – Consommation pellets | Cumul kg depuis l'origine | `cumul_kg` mensuel |
| Cumul – Cycles | Cumul allumages depuis l'origine | `cumul_cycle` mensuel |
| Cumul – Coût chauffage | Coût total | `cumul_cout` ou ∑(kWh×€/kWh) |

#### Silo & Cendrier

| Capteur | Contenu importé | Méthode |
|---------|----------------|---------|
| Silo – Pellets restants | Stock estimé en fin de journée (kg) | `silo_pellets_restants` mensuel |
| Silo – Niveau | Taux de remplissage en fin de journée (%) | `silo_niveau` mensuel |
| Cendrier – Capacité restante | Capacité restante en fin de journée (kg) | `cendrier_capacite_restante` mensuel |
| Cendrier – Niveau de remplissage | Taux de remplissage en fin de journée (%) | `cendrier_niveau_de_remplissage` mensuel |

#### Prix

| Capteur | Contenu importé | Méthode |
|---------|----------------|---------|
| Prix pellets (€/kg) | Évolution historique du prix | `prix_kg` mensuel |
| Prix énergie (€/kWh) | Évolution historique du prix | `prix_kwh` mensuel |

#### Températures

| Capteur | Contenu importé | Méthode |
|---------|----------------|---------|
| Hier – Température extérieure max | Température max (°C) | `tc_ext_max` mensuel, interpolation |
| Hier – Température extérieure min | Température min (°C) | `tc_ext_min` mensuel, interpolation |

### Comment lancer l'import

1. **Outils de développement** (`</>` dans la barre latérale) → onglet **Actions**
2. Rechercher `okovision.import_history`
3. Paramétrer et exécuter :

```yaml
years: 4   # nombre d'années à importer (1 à 4, défaut : 4)
```

### Fonctionnement interne

```
┌─────────────────────────────────────────────────────────────┐
│  Pour chaque mois sur la période (max 48 requêtes)           │
│    → action=monthly&month=MM&year=YYYY                       │
│    → collecte des valeurs journalières (cumul_*, prix_*)     │
│                                                              │
│  + action=today → données du jour en cours                   │
│                                                              │
│  Reconstruction de cumul_cout si absent du monthly :         │
│    cumul_cout[j] = cumul_cout[j-1] + conso_kwh[j] × prix_kwh[j]│
│    (ancrage sur toute valeur réelle disponible)              │
│                                                              │
│  → Injection via recorder.import_statistics                  │
│     source="recorder", statistic_id = entity_id HA          │
└─────────────────────────────────────────────────────────────┘
```

**Durée estimée** : 2 à 5 minutes pour 4 ans (48 requêtes HTTP avec délai anti-saturation).

**Idempotent** : relancer le service ne crée pas de doublons — HA fusionne les
statistiques existantes.

**Suivi de la progression** : **Paramètres → Système → Journaux** → filtrer `okovision`

```
OkoVision import_history : démarrage 2022-03-01 → 2026-03-26 (4 an(s))
OkoVision import_history : 01/2022 ✓ (1/48 – 31 jours cumulés)
...
OkoVision import_history : ✓ cumul_kwh       → 1461 pts | dernier=18432.50 kWh
OkoVision import_history : ✓ cumul_kg        →  1461 pts | dernier=3521.20 kg
OkoVision import_history : ✓ cumul_cycle     →  1461 pts | dernier=12840 cycles
OkoVision import_history : ✓ cumul_cout_eur  →  1461 pts | dernier=4218.60 EUR
OkoVision import_history : terminé – 5/5 métriques injectées
```

### Configuration du tableau Énergie après import

Dans **Paramètres → Énergie**, sur la source **Énergie cumulée** :
- **Suivre les coûts** → *Utiliser une entité de suivi des coûts totaux*
- Sélectionner : **Coût cumulé chauffage** (EUR)

---

## API utilisée

| Action | Utilisation | Fréquence |
|--------|-------------|-----------|
| `action=today` | Silo + cendrier live + données du jour | Toutes les N secondes |
| `action=daily&date=YYYY-MM-DD` | Résumé J-1 confirmé (`is_new` indique si les données sont prêtes) | Toutes les heures |
| `action=monthly&month=MM&year=YYYY` | Données mensuelles (import historique) | 1× par mois lors de l'import |
| `action=status` | Test de connexion au setup | 1× au démarrage |
