---
name: OkoVision HA Integration
description: Projet Home Assistant custom component pour monitoring chaudière à pellets OkoVision
type: project
---

Intégration Home Assistant (HACS) pour le système de monitoring chaudière à pellets **OkoVision**.

**Dépôt :** `nicouchot/okovision-ha`
**Domaine HA :** `okovision`
**Version courante :** 0.5.28

## Règles de travail (à respecter pour chaque demande)
1. Demander des précisions si la spécification n'est pas claire
2. Réaliser un commit et un push à chaque demande (avec confirmation avant commit)
3. Documenter les modifications dans le README (mise à jour) ET dans CHANGELOG.md
4. Détailler les modifications dans le message de commit (fichiers touchés, comportement avant/après)
5. Écrire des tests unitaires dans `tests/` lorsque c'est pertinent (logique métier, parsing, edge cases)

Les règles 1–4 sont également enregistrées dans `~/.claude/CLAUDE.md` (global, tous projets).

## Tests
- Dossier : `tests/`
- Framework : `pytest` + `pytest-asyncio`
- Lancer : `pytest tests/`

## Architecture
- `custom_components/okovision/` : composant principal
  - `coordinator.py` : DataUpdateCoordinator, live (N sec) + daily (1h, champ `is_new`)
  - `api.py` : client REST vers `ha_api.php` — `OkovisionDataNotFoundError` pour 404
  - `sensor.py` : capteurs live + J-1 + cumulatifs
  - `binary_sensor.py` : alerte cendrier
  - `services.py` : `import_history`, `reset_history`
  - `config_flow.py` : configuration UI (URL, token, intervalle)
  - `services.yaml` : titres/descriptions des actions HA
  - `.github/workflows/release.yml` : release GitHub auto sur bump manifest.json

## Sources API
- `action=today` → silo + cendrier (nested) + données jour en cours
- `action=daily&date=YYYY-MM-DD` → résumé J-1 confirmé, champ `is_new` (true/false)
- `action=monthly&month=MM&year=YYYY` → données mensuelles avec silo/cendrier/prix
- `action=status` → test connexion

## Points techniques importants
- HA 2026.x : `clear_statistics` → utiliser `Recorder.async_clear_statistics()` + asyncio.Future
- `is_new=false` : sensors internes mis à jour (valeurs brutes, zéros inclus), stats externes ignorées
- 404 → `OkovisionDataNotFoundError` → cache conservé, retry au prochain cycle
- `cumul_cout` absent du monthly → reconstruction par running sum `conso_kwh × prix_kwh`
- HACS 2.x : icône store → cherche `icon.png` à la racine du dépôt (en plus de `custom_components/okovision/icon.png`)
- HACS 2.x : release GitHub obligatoire pour afficher la version (CI automatique sur bump manifest.json)
- CI release : body injecté depuis `CHANGELOG.md` via `awk` (section `## [VERSION]`) — ne pas utiliser `--generate-notes` (ne produit qu'un lien vide)

## Sections import_history (services.py)
- 1 : collecte mensuelle
- 1b : fetch action=today (silo/cendrier nested + clés plates)
- 1c : reconstruction cumul_cout
- 2 : stats externes (okovision:cumul_kwh, okovision:cumul_cout_eur)
- 3 : résolution entity_id via entity registry
- 4 : sensors journaliers crénelage (conso_*, nb_cycle, dju)
- 5 : sensors cumulatifs courbe progressive (cumul_*)
- 6 : températures — 1 point par jour à minuit du jour J (valeur directe, pas d'interpolation)
- 7 : snapshot quotidien silo/cendrier/prix (RECORDER_SNAPSHOT_CONFIG)
