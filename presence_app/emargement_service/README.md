# emargement_service

Service de gestion des feuilles de présence.

## Rôle

Permet aux formateurs d'ouvrir des sessions de cours, de saisir les présences étudiant par étudiant, puis de clôturer la session. À la fermeture, un email de notification est automatiquement envoyé à chaque étudiant absent.

## Port

`5003`

## Base de données

PostgreSQL dédiée (`emarg_db`). Contient deux tables :

```
Session (un cours à un instant donné)
  └── Presence (une ligne par étudiant, statut : présent / absent / retard / excusé)
```

## Dépendance inter-services

Ce service appelle le `planning_service` pour :
- Récupérer le nom de la promotion lors de la création d'une session
- Récupérer la liste des étudiants afin de pré-remplir la feuille de présence
- Récupérer l'email d'un étudiant avant d'envoyer un mail d'absence

Si le `planning_service` est indisponible, la session est quand même créée (les champs concernés seront vides).

## Endpoints

### Sessions

| Méthode | Route | Accès | Description |
|---------|-------|-------|-------------|
| GET | `/health` | Public | Vérification que le service est opérationnel |
| GET | `/emargement/sessions` | Tous | Liste les sessions (filtres : `promotion_id`, `formateur_id`, `date`) |
| POST | `/emargement/sessions` | Tous | Crée une session et génère automatiquement les lignes de présence |
| GET | `/emargement/sessions/<id>` | Tous | Détail d'une session avec toutes les présences |
| POST | `/emargement/sessions/<id>/fermer` | Formateur / Admin | Ferme la session et envoie les mails aux absents |

### Présences

| Méthode | Route | Accès | Description |
|---------|-------|-------|-------------|
| PUT | `/emargement/presences/<id>` | Formateur / Admin | Modifie le statut d'une présence individuelle |
| PUT | `/emargement/sessions/<id>/presences` | Formateur / Admin | Met à jour toutes les présences d'une session en une seule requête |

> Une session fermée ne peut plus être modifiée.

## Envoi d'emails

Les emails d'absence sont envoyés via SMTP (configuration Gmail par défaut). Si `MAIL_USERNAME` ou `MAIL_PASSWORD` ne sont pas renseignés, l'envoi est simulé en console (aucune erreur bloquante).

## Variables d'environnement

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | URL de connexion PostgreSQL |
| `SECRET_KEY` | Clé secrète partagée pour valider les JWT |
| `PLANNING_SERVICE_URL` | URL interne du `planning_service` |
| `MAIL_SERVER` | Serveur SMTP (ex: `smtp.gmail.com`) |
| `MAIL_PORT` | Port SMTP (ex: `587`) |
| `MAIL_USERNAME` | Identifiant du compte email expéditeur |
| `MAIL_PASSWORD` | Mot de passe applicatif du compte email |
| `MAIL_SENDER` | Adresse affichée dans le champ "De" |

## Dépendances

```
flask
flask-sqlalchemy
psycopg2-binary
pyjwt
requests
```
