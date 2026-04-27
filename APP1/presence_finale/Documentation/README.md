# Application de Gestion des Presences
## Architecture Micro-Services et Docker
**Diarra Salif - DSP DevOps 2025-2026 - CNAM Paris**

---

## Demarrage rapide

```bash
# Cloner ou extraire le projet
cd presence_finale

# Copier et adapter le fichier d'environnement
cp .env .env.local   # ajuster les variables SMTP si besoin

# Demarrer les 7 conteneurs
docker compose up --build

# L'application est disponible sur http://localhost:5000
# Comptes par defaut : admin@ecole.fr / admin123 | martin@ecole.fr / formateur123
```

---

## Services et ports

| Service              | Port | Role                                          |
|----------------------|------|-----------------------------------------------|
| frontend_service     | 5000 | Interface web Jinja2 (point d entree)         |
| auth_service         | 5001 | Authentification JWT, gestion des comptes     |
| planning_service     | 5002 | Cours, promotions, etudiants, import CSV/Excel|
| emargement_service   | 5003 | Presences, cloture de session, emails         |

Chaque service applicatif a sa propre base PostgreSQL (auth_db, planning_db, emarg_db).

---

## Architecture du projet

```
presence_finale/
  auth_service/          # JWT, RBAC, rate-limiting
    app.py
    Dockerfile
    requirements.txt
  planning_service/      # Classes, promotions, etudiants, import
    app.py
    Dockerfile
    requirements.txt
  emargement_service/    # Sessions, presences, SMTP asynchrone
    app.py
    Dockerfile
    requirements.txt
  frontend_service/      # BFF - templates Jinja2
    app.py
    Dockerfile
    requirements.txt
  docker-compose.yml
  .env
  exemple_etudiants.csv
```

---

## Fonctionnalites implementees

### auth_service (port 5001)
- POST /auth/login - connexion, generation token JWT HS256 (24h)
- POST /auth/verify - validation token pour les autres services
- GET  /me - profil depuis le token (sans requete BDD)
- POST /auth/users - creation de compte (admin)
- GET  /auth/users - liste des comptes (admin)
- PUT  /auth/users/:id - modification compte
- GET  /health - sonde Docker
- Rate-limiting : 5 tentatives / 15 min par IP
- CORS corrige : les requetes OPTIONS ne declenchent plus de 401

### planning_service (port 5002)
- CRUD complet Classes et Promotions
- CRUD Etudiants avec is_active (desactivation douce RGPD)
- Import CSV : detection automatique du separateur via csv.Sniffer()
- Import Excel : via openpyxl, meme logique
- Mapping flexible des noms de colonnes (alias : nom/lastname/name...)
- Rapport JSON detaille : inseres, doublons_fichier, doublons_base, erreurs
- Limite anti-DoS : 5000 lignes maximum par import

### emargement_service (port 5003)
- Creation de session + initialisation automatique des presences (absent par defaut)
- PATCH /emargement/presences/:id - mise a jour statut (present, absent, retard, excuse)
- POST /emargement/sessions/:id/bulk - action groupee (tous presents / tous absents)
- POST /emargement/sessions/:id/fermer - cloture + emails asynchrones
- GET  /emargement/sessions/:id/notifications - journal des emails
- GET  /emargement/stats - KPIs globaux (taux, sessions, emails)
- GET  /emargement/stats/promotion/:id - stats par promotion
- ThreadPoolExecutor(max_workers=5) pour l envoi SMTP
- Retry exponentiel : 3 tentatives, backoff 1s / 2s / 4s
- NotificationLog : trace chaque envoi (statut, tentatives, erreur)

### frontend_service (port 5000)
- JWT stocke en cookie HttpOnly (protection XSS)
- Feuille d appel avec selecteur statut AJAX (pas de rechargement)
- Compteurs mis a jour en temps reel apres chaque modification
- BulkActionBar : "Tous presents" / "Tous absents" en un clic
- Modale de confirmation avant cloture de session
- Page statistiques admin (KPIs globaux)
- Rollback AJAX en cas d erreur reseau

---

## Variables d'environnement

Voir le fichier `.env`. Les variables SMTP sont optionnelles :
sans elles, les emails sont simules (print dans les logs Docker).

```env
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=votre@gmail.com
MAIL_PASSWORD=mot_de_passe_app
MAIL_SENDER=noreply@ecole.fr
```

---

## Test avec Mailhog (developpement)

Pour tester les emails sans polluer de vraies boites mail :

```bash
# Ajouter dans docker-compose.yml :
  mailhog:
    image: mailhog/mailhog
    ports:
      - "1025:1025"   # SMTP
      - "8025:8025"   # Interface web

# Dans .env :
MAIL_SERVER=mailhog
MAIL_PORT=1025
MAIL_USERNAME=
MAIL_PASSWORD=
```

L interface Mailhog est visible sur http://localhost:8025.
