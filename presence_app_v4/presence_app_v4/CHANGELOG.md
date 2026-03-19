# Changelog — presence_app v2

## Améliorations apportées par rapport à la v1

---

### ✅ 1. Rate Limiting — `auth_service`

**Problème v1 :** La route `/auth/login` acceptait un nombre illimité de tentatives
par IP. Une attaque brute-force pouvait tester des milliers de mots de passe par seconde.

**Solution v2 :**
- Ajout de `flask-limiter==3.5.0` dans `auth_service/requirements.txt`
- Décorateurs `@limiter.limit('5 per minute')` et `@limiter.limit('20 per hour')`
  sur la route `/auth/login`
- Réponse HTTP **429 Too Many Requests** avec message clair si la limite est dépassée
- Gestionnaire `@app.errorhandler(429)` dédié avec log de l'IP

```python
# auth_service/app.py
limiter = Limiter(key_func=get_remote_address, app=app, storage_uri="memory://")

@app.route('/auth/login', methods=['POST'])
@limiter.limit('5 per minute')
@limiter.limit('20 per hour')
def login(): ...
```

---

### ✅ 2. Templates HTML séparés — `frontend`

**Problème v1 :** Tout le HTML (700+ lignes) était écrit dans des f-strings Python
(`render_template_string`). Code illisible, pas de coloration syntaxique HTML,
risque XSS avec `| safe`.

**Solution v2 :**
- Création du dossier `frontend/templates/` avec 6 fichiers `.html` dédiés
- Utilisation de `render_template()` au lieu de `render_template_string()`
- Jinja2 échappe automatiquement les variables → protection XSS native
- `app.py` ne contient plus que la logique Python (routes, appels API)

**Fichiers créés :**
```
frontend/templates/
├── base.html              ← layout commun (navbar, CSS, messages flash)
├── login.html             ← page de connexion
├── sessions.html          ← liste des sessions + pagination
├── session_nouvelle.html  ← formulaire nouvelle session
├── session_detail.html    ← feuille de présence
├── admin_promotions.html  ← gestion classes/promotions
└── admin_etudiants.html   ← gestion étudiants + pagination
```

---

### ✅ 3. Pagination SQL — `emargement_service` + `planning_service` + `frontend`

**Problème v1 :** `Session.query.all()` et `Etudiant.query.all()` chargeaient
l'intégralité des données en mémoire. Avec 10 000 sessions, la réponse JSON
dépasserait 10 Mo.

**Solution v2 :**

**emargement_service** — `GET /emargement/sessions` :
```
?page=1&per_page=20  →  max 100 par page
```
Réponse enrichie : `total`, `pages`, `has_next`, `has_prev`

**planning_service** — `GET /planning/etudiants` :
```
?page=1&per_page=50     →  mode paginé (défaut, max 200)
?all=true               →  mode non paginé pour appels internes inter-services
```

**frontend** — transmet les paramètres de pagination et affiche les contrôles
de navigation (‹ Préc. / 1 / 2 / 3 / Suiv. ›) dans `sessions.html`
et `admin_etudiants.html`.

---

### ✅ 4. Healthcheck PostgreSQL — `docker-compose.yml`

**Problème v1 :** `depends_on: auth_db` démarrait `auth_service` dès que le
*conteneur* PostgreSQL était lancé, pas quand PostgreSQL était *prêt à accepter
des connexions* (délai de 3-10 secondes). Risque de `Connection refused` au boot.

**Solution v2 :**
```yaml
auth_db:
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U ${AUTH_DB_USER} -d ${AUTH_DB_NAME}"]
    interval: 5s
    timeout:  3s
    retries:  5
    start_period: 10s

auth_service:
  depends_on:
    auth_db:
      condition: service_healthy   # ← attend l'état healthy
```

Les trois bases (`auth_db`, `planning_db`, `emarg_db`) ont chacune leur healthcheck.

---

### ✅ 5. Remplacement de `debug=True` par Gunicorn

**Problème v1 :** `app.run(host='0.0.0.0', port=5001, debug=True)` utilisait
le serveur de développement Flask, qui :
- Expose les stack traces complètes en cas d'erreur (fuite d'information)
- N'est pas conçu pour la production (mono-thread, pas de gestion de signaux)
- Affiche un avertissement explicite "Do not use the development server in production"

**Solution v2 :**
- Suppression de `app.run(debug=True)` dans les 4 services
- Ajout de `gunicorn==21.2.0` dans chaque `requirements.txt`
- Nouvelle commande dans chaque `Dockerfile` :

```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "2",
     "--timeout", "60", "--access-logfile", "-", "app:app"]
```

- `--workers 2` : 2 processus parallèles (adapté à un conteneur léger)
- `--access-logfile -` : logs d'accès sur stdout → visibles via `docker compose logs`

---

### Autres améliorations mineures

- **Logging structuré** : `logging.basicConfig()` dans les 4 services avec
  format horodaté et nom du service. Remplace les `print()` dispersés.
- **Gestion d'erreurs JWT explicite** : distinction entre `ExpiredSignatureError`
  et `InvalidTokenError` (messages d'erreur plus précis).
- **`except` nommés** : les `except:` silencieux sont remplacés par
  `except requests.exceptions.RequestException as e: logger.error(...)`.
- **Messages flash catégorisés** : `flash('...', 'danger')` / `flash('...', 'success')`
  pour un affichage cohérent avec les classes CSS `alert-danger` / `alert-success`.

---

## Structure finale v2

```
presence_app_v2/
├── .env                          ← variables d'environnement (ne pas committer)
├── .gitignore
├── docker-compose.yml            ← healthchecks + condition: service_healthy
├── auth_service/
│   ├── app.py                    ← + flask-limiter, + logging, - debug=True
│   ├── Dockerfile                ← CMD gunicorn
│   └── requirements.txt          ← + flask-limiter, + gunicorn
├── planning_service/
│   ├── app.py                    ← + pagination /etudiants, + logging
│   ├── Dockerfile                ← CMD gunicorn
│   └── requirements.txt          ← + gunicorn
├── emargement_service/
│   ├── app.py                    ← + pagination /sessions, + logging
│   ├── Dockerfile                ← CMD gunicorn
│   └── requirements.txt          ← + gunicorn
└── frontend/
    ├── app.py                    ← render_template(), pagination, - HTML inline
    ├── Dockerfile                ← CMD gunicorn
    ├── requirements.txt          ← + gunicorn
    └── templates/
        ├── base.html
        ├── login.html
        ├── sessions.html
        ├── session_nouvelle.html
        ├── session_detail.html
        ├── admin_promotions.html
        └── admin_etudiants.html
```

## Démarrage

```bash
# Première fois ou après modification du code
docker compose up --build

# Relancer sans rebuild
docker compose up

# Voir les logs en temps réel
docker compose logs -f

# Arrêter (conserve les volumes)
docker compose down

# Arrêter ET supprimer les données (irréversible)
docker compose down --volumes
```
