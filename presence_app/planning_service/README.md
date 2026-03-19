# planning_service

Service de gestion du référentiel pédagogique : classes, promotions et étudiants.

## Rôle

Stocke et expose la structure pédagogique de l'établissement. C'est la source de vérité pour la liste des étudiants, consultée par l'`emargement_service` lors de la création d'une session de cours.

## Port

`5002`

## Base de données

PostgreSQL dédiée (`planning_db`). Contient trois tables liées :

```
Classe (ex: BTS SIO)
  └── Promotion (ex: BTS SIO Groupe A — 2025-2026)
        └── Etudiant
```

## Endpoints

### Classes

| Méthode | Route | Accès | Description |
|---------|-------|-------|-------------|
| GET | `/planning/classes` | Tous | Liste toutes les classes |
| POST | `/planning/classes` | Admin | Crée une nouvelle classe |

### Promotions

| Méthode | Route | Accès | Description |
|---------|-------|-------|-------------|
| GET | `/planning/promotions` | Tous | Liste les promotions (filtre optionnel : `?classe_id=`) |
| GET | `/planning/promotions/<id>` | Tous | Détail d'une promotion avec la liste de ses étudiants |
| POST | `/planning/promotions` | Admin | Crée une nouvelle promotion |

### Étudiants

| Méthode | Route | Accès | Description |
|---------|-------|-------|-------------|
| GET | `/planning/etudiants` | Tous | Liste les étudiants actifs (filtre optionnel : `?promotion_id=`) |
| GET | `/planning/etudiants/<id>` | Tous | Détail d'un étudiant |
| POST | `/planning/etudiants` | Admin | Ajoute un étudiant manuellement |
| PUT | `/planning/etudiants/<id>` | Admin | Modifie un étudiant |
| POST | `/planning/etudiants/import-csv` | Admin | Import en masse depuis un fichier CSV ou Excel |

## Import CSV / Excel

Le fichier doit contenir une ligne par étudiant avec les colonnes dans cet ordre :

```
nom, prenom, email, numero_etudiant (optionnel)
```

- Séparateurs acceptés : `,` ou `;`
- La ligne d'en-tête est automatiquement ignorée
- Les formats `.csv`, `.txt` et `.xlsx` sont supportés
- Les doublons d'email sont ignorés sans erreur bloquante

## Variables d'environnement

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | URL de connexion PostgreSQL |
| `SECRET_KEY` | Clé secrète partagée pour valider les JWT |

## Dépendances

```
flask
flask-sqlalchemy
psycopg2-binary
pyjwt
openpyxl
```
