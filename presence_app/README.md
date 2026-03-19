# Système de gestion des présences

Application web en microservices pour enregistrer les présences des étudiants.

## Services

| Service | Port | Rôle |
|---|---|---|
| frontend | 5000 | Interface web (HTML) |
| auth_service | 5001 | Connexion, comptes |
| planning_service | 5002 | Classes, promotions, étudiants |
| emargement_service | 5003 | Feuilles de présence |

## Lancer l'application

```bash
docker-compose up --build
```

L'interface est accessible sur : http://localhost:5000

## Compte admin par défaut

- Email : admin@ecole.fr
- Mot de passe : admin123

## Ce que fait l'app

1. L'admin crée des classes (BTS SIO, LP Dev...) et des promotions (groupe A, 2025-2026...)
2. L'admin ajoute les étudiants dans chaque promotion
3. Le formateur crée une session de cours (choisit la promo, la matière, la date)
4. L'app charge automatiquement la liste de tous les étudiants de la promo, tous marqués "absent"
5. Le formateur coche les présents/retards directement dans le tableau
6. Le formateur ferme la session quand c'est terminé

## Structure

```
presence_app/
├── auth_service/        → login, gestion comptes
├── planning_service/    → classes, promos, étudiants
├── emargement_service/  → sessions et presences
├── frontend/            → pages web
└── docker-compose.yml
```
