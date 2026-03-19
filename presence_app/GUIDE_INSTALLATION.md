# Guide d'installation et d'utilisation
# Système de gestion des présences

---

## Architecture du projet

L'application est composée de **4 microservices** Flask + **3 bases PostgreSQL**, orchestrés via Docker Compose :

```
presence_app/
├── auth_service/         → Authentification JWT (port 5001)
├── planning_service/     → Classes, promotions, étudiants (port 5002)
├── emargement_service/   → Sessions de cours et présences (port 5003)
├── frontend/             → Interface web HTML (port 5000)
└── docker-compose.yml    → Orchestration de tous les services
```

---

## Prérequis

| Outil | Version minimale | Téléchargement |
|-------|-----------------|----------------|
| Docker Desktop | 4.x | https://www.docker.com/products/docker-desktop |
| Navigateur web | tout moderne | — |

> Docker Desktop inclut automatiquement Docker Compose. Aucun autre outil n'est nécessaire.

---

## Installation — étape par étape

### Étape 1 — Préparer les fichiers

1. Décompressez l'archive `presence_app.zip`
2. Placez le script `install_presence_app.sh` **dans le dossier décompressé**, au même niveau que `docker-compose.yml`

Structure attendue :
```
presence_app/
├── install_presence_app.sh   ← le script
├── docker-compose.yml
├── auth_service/
├── planning_service/
├── emargement_service/
└── frontend/
```

### Étape 2 — Démarrer Docker Desktop

Ouvrez Docker Desktop et attendez que l'icône de la baleine soit **verte** (prêt).

### Étape 3 — Lancer le script d'installation

Ouvrez un terminal dans le dossier du projet et exécutez :

**Sur macOS / Linux :**
```bash
chmod +x install_presence_app.sh
./install_presence_app.sh
```

**Sur Windows (PowerShell) :**
```powershell
# Utiliser WSL2 ou Git Bash, puis :
bash install_presence_app.sh
```

> Le script va :
> - Vérifier Docker
> - Vous proposer de configurer l'envoi d'email (optionnel)
> - Construire toutes les images Docker (2 à 5 min la première fois)
> - Démarrer tous les services
> - Ouvrir automatiquement le navigateur sur http://localhost:5000

### Étape 4 — Accéder à l'application

Une fois le script terminé, ouvrez : **http://localhost:5000**

Connexion admin par défaut :
- **Email :** `admin@ecole.fr`
- **Mot de passe :** `admin123`

---

## Guide d'utilisation

### Flux de travail typique

```
Admin                          Formateur
  │                                │
  ▼                                │
Créer une classe                   │
(ex: BTS SIO 1ère année)           │
  │                                │
  ▼                                │
Créer une promotion                │
(ex: Groupe A, 2025-2026)          │
  │                                │
  ▼                                │
Ajouter les étudiants              │
(manuellement ou via CSV)          │
  │                                │
  │                       ▼        │
  │              Créer une session de cours
  │              (choisir promo, matière, date)
  │                       │
  │                       ▼
  │              Marquer les présences
  │              (présent / absent / retard)
  │                       │
  │                       ▼
  │              Fermer la session
  │                       │
  │                       ▼
  │              (optionnel) Envoyer la feuille par email
```

### 1. Créer une classe

1. Connectez-vous en tant qu'admin
2. Allez dans **Planning > Classes**
3. Cliquez **Nouvelle classe**
4. Renseignez le nom (ex: `BTS SIO`, `LP Développement`)
5. Sauvegardez

### 2. Créer une promotion

1. Allez dans **Planning > Promotions**
2. Cliquez **Nouvelle promotion**
3. Associez-la à une classe, donnez-lui un nom et une année scolaire
4. Sauvegardez

### 3. Ajouter des étudiants

**Manuellement :**
1. Allez dans **Planning > Étudiants**
2. Cliquez **Ajouter un étudiant**
3. Renseignez nom, prénom, et affectez à une promotion

**Via import CSV :**
1. Préparez un fichier CSV avec les colonnes : `nom,prenom,email,promotion_id`
   (un fichier exemple est fourni : `exemple_etudiants.csv`)
2. Allez dans **Planning > Import CSV**
3. Sélectionnez votre fichier et importez

### 4. Créer une session de cours

1. Connectez-vous en tant que formateur (ou admin)
2. Allez dans **Émargement > Nouvelle session**
3. Choisissez :
   - La promotion concernée
   - La matière
   - La date et l'heure
4. Validez → la liste des étudiants s'affiche automatiquement, tous marqués **Absent**

### 5. Saisir les présences

Dans le tableau de la session :
- Cliquez sur le statut d'un étudiant pour le basculer : **Absent → Présent → Retard**
- Les modifications sont sauvegardées en temps réel

### 6. Fermer la session

Une fois le cours terminé :
1. Cliquez **Fermer la session**
2. La feuille de présence est archivée
3. (si email configuré) Cliquez **Envoyer par email** pour expédier la feuille

---

## Configuration de l'envoi d'email (Gmail)

Si vous souhaitez activer l'envoi des feuilles de présence par email :

1. Activez la **validation en 2 étapes** sur votre compte Google
2. Allez sur : https://myaccount.google.com/apppasswords
3. Créez un **mot de passe d'application** (type : Mail)
4. Copiez le mot de passe généré (16 caractères)
5. Dans `docker-compose.yml`, modifiez ces lignes :
   ```yaml
   MAIL_USERNAME: "votre@gmail.com"
   MAIL_PASSWORD: "votre-mot-de-passe-app"
   ```
6. Relancez : `docker compose restart emargement_service`

---

## Commandes utiles

```bash
# Démarrer l'application
docker compose up -d

# Arrêter l'application (données conservées)
docker compose down

# Voir les logs en direct
docker compose logs -f

# Voir les logs d'un seul service
docker compose logs -f frontend

# Redémarrer un service
docker compose restart emargement_service

# Réinitialisation complète (SUPPRIME toutes les données)
docker compose down -v
docker compose up --build -d

# État des containers
docker compose ps
```

---

## Résolution des problèmes

| Problème | Solution |
|----------|----------|
| "Cannot connect to Docker daemon" | Démarrez Docker Desktop et attendez que l'icône soit verte |
| Page blanche sur localhost:5000 | Attendez 30s de plus, les BDD s'initialisent. Vérifiez `docker compose logs frontend` |
| Erreur de port déjà utilisé | Un autre service utilise le port 5000/5001/5002/5003. Modifiez les ports dans `docker-compose.yml` |
| Données perdues après redémarrage | Normal si `docker compose down -v` a été utilisé. Sinon, `docker compose down` (sans `-v`) conserve les données |
| Email non envoyé | Vérifiez les variables `MAIL_USERNAME` et `MAIL_PASSWORD` dans `docker-compose.yml`. Utilisez un mot de passe d'application, pas votre mot de passe habituel |
