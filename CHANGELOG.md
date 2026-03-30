# Changelog OkoVision HA

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
