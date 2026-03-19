# auth_service

Service d'authentification de l'application de gestion des présences.

## Rôle

Gère les comptes utilisateurs (admins et formateurs) et l'émission de tokens JWT utilisés par tous les autres services pour vérifier l'identité des utilisateurs.

## Port

`5001`

## Base de données

PostgreSQL dédiée (`auth_db`). Contient une seule table `users`.

## Endpoints

| Méthode | Route | Accès | Description |
|---------|-------|-------|-------------|
| GET | `/health` | Public | Vérification que le service est opérationnel |
| POST | `/auth/login` | Public | Connexion — renvoie un token JWT (valide 24h) |
| GET | `/auth/verify` | Public | Vérifie la validité d'un token JWT |
| POST | `/auth/users` | Admin | Crée un nouveau compte utilisateur |
| GET | `/auth/users` | Admin | Liste tous les utilisateurs |

## Rôles utilisateurs

- **admin** : peut créer des comptes et accéder à toutes les fonctionnalités
- **formateur** : peut uniquement se connecter et gérer ses sessions de cours

## Compte par défaut

Au premier démarrage, un compte admin est automatiquement créé :

```
Email    : admin@ecole.fr
Password : admin123
```

> ⚠️ Changer ce mot de passe en production.

## Variables d'environnement

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | URL de connexion PostgreSQL |
| `SECRET_KEY` | Clé secrète partagée pour signer les JWT |

## Dépendances

```
flask
flask-sqlalchemy
psycopg2-binary
pyjwt
werkzeug
```
