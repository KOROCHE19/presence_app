# frontend

Interface web de l'application de gestion des présences.

## Rôle

Fournit l'interface utilisateur complète via un serveur Flask. Toutes les pages HTML sont générées côté serveur. Le frontend ne possède pas sa propre base de données : il consomme les trois autres services via leurs APIs REST.

## Port

`5000`

## Services consommés

| Service | Usage |
|---------|-------|
| `auth_service` | Connexion / déconnexion |
| `planning_service` | Affichage et gestion des promotions et étudiants |
| `emargement_service` | Affichage et gestion des sessions et présences |

## Pages disponibles

| Route | Rôle | Description |
|-------|------|-------------|
| `/login` | Tous | Page de connexion |
| `/logout` | Tous | Déconnexion |
| `/sessions` | Tous | Liste de toutes les sessions de cours |
| `/sessions/nouvelle` | Tous | Formulaire de création d'une session |
| `/sessions/<id>` | Tous | Feuille de présence d'une session (saisie en temps réel) |
| `/admin/promotions` | Admin | Gestion des classes et promotions |
| `/admin/etudiants` | Admin | Gestion et import des étudiants par promotion |

## Fonctionnement technique

- Le token JWT est stocké dans la session Flask côté serveur.
- La modification d'une présence sur la feuille d'appel est envoyée en **AJAX** (sans rechargement de page) via l'endpoint proxy `/api/presences/<id>`.
- Les templates HTML sont intégralement définis dans `app.py` sous forme de chaînes Python (pas de dossier `templates`).

## Variables d'environnement

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Clé secrète Flask pour les sessions navigateur |
| `AUTH_SERVICE_URL` | URL interne de l'`auth_service` |
| `PLANNING_SERVICE_URL` | URL interne du `planning_service` |
| `EMARG_SERVICE_URL` | URL interne de l'`emargement_service` |

## Dépendances

```
flask
requests
```
