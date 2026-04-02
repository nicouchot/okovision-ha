# Changelog OkoVision HA

## [0.5.28] – 2026-04-02
### Corrigé
- CI : le body des releases GitHub ne contenait que le lien "Full Changelog"
  (généré par `--generate-notes`) sans notes lisibles — HACS affichait un
  écran "Update" vide
### Modifié
- `.github/workflows/release.yml` : remplacement de `--generate-notes` par
  extraction du bloc correspondant à la version dans `CHANGELOG.md` via `awk`
  → le body de chaque release contient désormais les notes du changelog

## [0.5.27] – 2026-04-01
### Corrigé
- `import_history` section 6 : les sensors `tc_ext_max` et `tc_ext_min` affichaient
  un effet "escalier" dans le graphe HA — deux paliers par jour (minuit J+1 + 5h J+1)
  au lieu d'une valeur plate sur toute la journée
### Modifié
- Section 6 (`RECORDER_TEMP_CONFIG`) : suppression de la logique "interpolation douce"
  (2 points par jour : moyenne interpolée à minuit J+1, valeur réelle à 5h J+1)
  → remplacée par un seul `StatisticData(start=minuit_J, mean=valeur_API)`
  identique au pattern des sections 5 et 7 (cumul, snapshot)
- Suppression de `days_by_date` devenu inutilisé
### Tests
- `TestTemperatureImport` (5 cas) : un point par jour, placement à minuit du jour J,
  valeur directe sans interpolation, absence de point à 5h, jour sans valeur ignoré

## [0.5.26] – 2026-03-30
### Corrigé
- `reset_history` : les valeurs enregistrées par le coordinator (polling temps réel)
  persistaient après reset car `async_clear_statistics` ne touche que les tables
  de statistiques, pas la table des états (`states`)
### Modifié
- `async_reset_history` : ajout d'une étape 4 qui appelle `recorder.purge_entities`
  avec `keep_days=0` sur toutes les entités OkoVision du registre
  → vide intégralement la table des états pour repartir d'une base vierge
- Echec de `purge_entities` logué en warning (non bloquant) pour ne pas masquer
  le succès de la suppression des statistiques
### Tests
- `TestResetHistoryIdCollection.test_liste_vide_db_utilise_fallback` (1 cas)

## [0.5.25] – 2026-03-30
### Corrigé
- `reset_history` : suppression incomplète quand des statistiques étaient stockées
  sous un `statistic_id` absent du registre d'entités (entité renommée, ancien import)
### Modifié
- `async_reset_history` : interroge désormais `async_list_statistic_ids(hass)` pour
  récupérer **tous** les IDs réellement présents en base préfixés par `okovision:`,
  `sensor.okovision_` ou `binary_sensor.okovision_`
- Union sans doublon des IDs base + registre (fallback) → garantit exhaustivité
- Log détaillé : nb IDs depuis la base / depuis le registre / total après dédup
### Tests
- `TestResetHistoryIdCollection` (4 cas) : priorité DB, absence de doublons,
  ancien ID inclus, filtre par préfixe de domaine

## [0.5.24] – 2026-03-30
### Ajouté
- Structure de tests unitaires `tests/` (pytest, sans dépendance au runtime HA)
  - `conftest.py` : stubs minimalistes pour tous les modules HA requis
  - `test_coordinator.py` : `_parse_date` (5 cas) + `_merge_with_previous` (5 cas)
  - `test_services.py` : intégrité des configs + reconstruction `cumul_cout` (4 cas)
  - `test_api.py` : gestion erreurs HTTP 401, 404, champ error JSON, connexion (5 cas)
  - `tests/requirements-test.txt` : `pytest`, `pytest-asyncio`, `aiohttp`
- 25 tests passent (`pytest tests/`)
### Règles de travail ajoutées
- Commit messages détaillés (fichiers touchés, comportement avant/après)
- Tests unitaires écrits à chaque demande pertinente

## [0.5.23] – 2026-03-30
### Ajouté
- `import_history` : import de 6 nouvelles séries historiques depuis `action=monthly`
  - Silo : `silo_remains_kg`, `silo_percent`
  - Cendrier : `ashtray_remains_kg`, `ashtray_percent`
  - Prix : `prix_kg`, `prix_kwh`
- Extraction silo/cendrier depuis la structure imbriquée de `action=today` (section 1b)
- `RECORDER_SNAPSHOT_CONFIG` (section E) dans `services.py`
- README : tableau des capteurs alimentés par `import_history` restructuré par catégorie

## [0.5.22] – 2026-03-30
### Corrigé
- `reset_history` : utilise désormais `Recorder.async_clear_statistics()` (@callback, HA 2026.x)
  - Résout "Action recorder.clear_statistics introuvable"
  - `asyncio.Future` + `call_soon_threadsafe` pour attendre la complétion effective

## [0.5.21] – 2026-03-30
### Interne
- Bump version pour déclencher la première release GitHub automatique via CI

## [0.5.20] – 2026-03-30
### Modifié
- Coordinator daily : quand `is_new=false`, les sensors internes sont mis à jour
  avec les valeurs brutes de l'API (zéros inclus) sans appliquer `_merge_with_previous`
- Les statistiques externes (`okovision:*`) ne sont pas modifiées quand `is_new=false`
- `_merge_with_previous` conservé uniquement pour le chemin `is_new=true`

## [0.5.19] – 2026-03-30
### Corrigé
- `import_history` : `cumul_cout_eur` n'était pas importé car `action=monthly`
  ne retourne pas `cumul_cout` par jour
- Section 1c ajoutée : reconstruction de `cumul_cout` par running sum
  `conso_kwh × prix_kwh` avec ancrage sur toute valeur réelle disponible
- Ajout de `cumul_cout` dans le fetch `action=today` (section 1b)
### Modifié
- README : section J-1 (suppression référence aux 5h du matin), ajout `reset_history`,
  fonctionnement interne `import_history` mis à jour, intervalle daily corrigé (1h)

## [0.5.18] – 2026-03-30
### Ajouté
- Coordinator daily : lecture du champ `is_new` dans la réponse de `action=daily`
  - `is_new=false` → conservation du cache, `_last_fetched_date` non mis à jour → retry
  - `is_new=true` → traitement normal + push stats externes
- Supprime la dépendance implicite à l'heure 5h du matin

## [0.5.17] – 2026-03-30
### Ajouté
- `OkovisionDataNotFoundError` dans `api.py` (sous-classe `OkovisionApiError`)
- Gestion HTTP 404 dans `_request` : lit le message d'erreur JSON avant de lever l'exception
- Coordinators live et daily : `OkovisionDataNotFoundError` ne bloque plus le chargement
  de l'intégration — retourne le cache ou `{}`, retry au prochain cycle

## [0.5.16] – 2026-03-30
### Corrigé
- `reset_history` : appel via `hass.services.async_call("recorder", "clear_statistics")`
  pour éviter "Detected unsafe call not in recorder thread" (HA 2026.x)

## [0.5.15] – 2026-03-30
### Ajouté
- `services.yaml` : titre et description de l'action `reset_history` visibles
  dans l'onglet Actions de HA

## [0.5.14] – antérieur
### Modifié
- `reset_history` : gestion robuste des signatures de `clear_statistics` selon version HA
- Log `exc_info=True` pour traceback complet en cas d'erreur
