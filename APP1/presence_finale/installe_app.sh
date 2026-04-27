#!/usr/bin/env bash
# =============================================================================
# install_presence_app.sh
# Script d'installation automatisée — Application de Gestion des Présences
# Architecture Micro-Services & Docker
#
# Auteur  : Diarra Salif — DSP DevOps 2025/2026 — CNAM Paris
# Version : 1.1
# Usage   : sudo bash install_presence_app.sh [--dev | --prod] [--skip-docker]
#
# Ce script part du principe que tu démarres sur une machine propre (Ubuntu 22+
# ou Debian 12). Il installe Docker, clone ou copie le projet, configure
# l'environnement et démarre les conteneurs. Une seule commande, tout le reste
# est automatique.
#
# Étapes :
#   1. Vérifications préliminaires (root, architecture, espace disque)
#   2. Installation de Docker Engine + Compose v2
#   3. Récupération du projet (git clone ou copie locale)
#   4. Génération du fichier .env avec secrets aléatoires
#   5. Build et démarrage des conteneurs Docker
#   6. Attente des healthchecks (bases de données)
#   7. Vérification finale des endpoints /health
#   8. Résumé avec identifiants par défaut et commandes utiles
# =============================================================================

set -euo pipefail   # Arrêt au moindre problème — pas de surprises silencieuses
IFS=$'\n\t'

# ─── Couleurs pour les messages console ──────────────────────────────────────
ROUGE='\033[0;31m'
VERT='\033[0;32m'
JAUNE='\033[1;33m'
BLEU='\033[0;34m'
GRAS='\033[1m'
NC='\033[0m'   # Reset couleur

# ─── Variables configurables ─────────────────────────────────────────────────
APP_DIR="${APP_DIR:-/opt/presence_app}"
REPO_URL="${REPO_URL:-https://github.com/ton-compte/presence_finale.git}"
MODE="${1:-}"          # --dev ou --prod
SKIP_DOCKER="${2:-}"   # --skip-docker si Docker est déjà installé

# Durée max d'attente pour que les conteneurs démarrent (en secondes)
TIMEOUT_DEMARRAGE=120

# Identifiants par défaut injectés à l'initialisation
DEFAULT_ADMIN_EMAIL="admin@ecole.fr"
DEFAULT_ADMIN_PASSWORD="admin123"
DEFAULT_FORMATEUR_EMAIL="martin@ecole.fr"
DEFAULT_FORMATEUR_PASSWORD="formateur123"


# =============================================================================
# Fonctions utilitaires
# =============================================================================

log()  { echo -e "${VERT}[OK]${NC}  $*"; }
info() { echo -e "${BLEU}[INFO]${NC} $*"; }
warn() { echo -e "${JAUNE}[AVERT]${NC} $*"; }
err()  { echo -e "${ROUGE}[ERR]${NC}  $*" >&2; exit 1; }

banniere() {
  echo -e "${BLEU}"
  echo "  ╔══════════════════════════════════════════════════════╗"
  echo "  ║   Gestion des Présences — Installation automatisée  ║"
  echo "  ║   CNAM Paris · DSP DevOps 2025/2026                 ║"
  echo "  ╚══════════════════════════════════════════════════════╝"
  echo -e "${NC}"
}

commande_existe() {
  command -v "$1" &>/dev/null
}

# Attend qu'un conteneur soit healthy avant de continuer
attendre_healthy() {
  local service="$1"
  local max_secondes="${2:-$TIMEOUT_DEMARRAGE}"
  local compteur=0

  info "Attente du démarrage de $service..."
  until docker inspect --format='{{.State.Health.Status}}' "$service" 2>/dev/null | grep -q "healthy"; do
    if [[ $compteur -ge $max_secondes ]]; then
      err "Timeout : $service n'est pas healthy après ${max_secondes}s. Lancez 'docker compose logs $service' pour investiguer."
    fi
    sleep 2
    (( compteur += 2 ))
    echo -n "."
  done
  echo ""
  log "$service est prêt."
}

# Génère une chaîne aléatoire sécurisée
generer_secret() {
  local longueur="${1:-32}"
  tr -dc 'A-Za-z0-9!@#$%^&*' < /dev/urandom | head -c "$longueur" 2>/dev/null || true
}


# =============================================================================
# Étape 1 — Vérifications préliminaires
# =============================================================================

verifier_systeme() {
  info "Vérification du système..."

  # Droits root requis pour l'installation de Docker
  if [[ $EUID -ne 0 ]]; then
    err "Ce script doit être lancé avec sudo ou en tant que root."
  fi

  # Vérification architecture (x86_64 ou arm64)
  local arch
  arch=$(uname -m)
  if [[ "$arch" != "x86_64" && "$arch" != "aarch64" ]]; then
    warn "Architecture non testée : $arch. L'installation peut fonctionner quand même."
  fi

  # Espace disque minimum : 2 Go
  local espace_libre
  espace_libre=$(df / --output=avail -k | tail -1)
  if [[ $espace_libre -lt 2097152 ]]; then
    warn "Moins de 2 Go d'espace disque disponible. Des problèmes peuvent survenir."
  fi

  # Vérification OS (Ubuntu/Debian attendu pour le script d'install Docker)
  if ! commande_existe apt-get; then
    warn "apt-get non trouvé. Ce script est conçu pour Ubuntu 22+ / Debian 12+."
    warn "Sur d'autres distributions, installez Docker manuellement et relancez avec --skip-docker."
  fi

  log "Vérifications système OK (arch: $arch, espace: ${espace_libre}K)."
}


# =============================================================================
# Étape 2 — Installation de Docker Engine
# =============================================================================

installer_docker() {
  if [[ "$SKIP_DOCKER" == "--skip-docker" ]]; then
    info "Installation Docker ignorée (--skip-docker)."
    commande_existe docker || err "Docker non trouvé. Installez-le manuellement ou retirez --skip-docker."
    return
  fi

  if commande_existe docker; then
    local version
    version=$(docker --version | awk '{print $3}' | tr -d ',')
    log "Docker déjà installé (version $version). On passe."
    return
  fi

  info "Installation de Docker Engine depuis le dépôt officiel..."

  apt-get update -qq
  apt-get install -y -qq \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

  mkdir -p /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg

  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list

  apt-get update -qq
  apt-get install -y -qq \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

  systemctl enable docker --quiet
  systemctl start docker

  log "Docker installé et démarré."

  # Ajouter l'utilisateur courant au groupe docker
  local utilisateur_reel="${SUDO_USER:-$USER}"
  if [[ -n "$utilisateur_reel" && "$utilisateur_reel" != "root" ]]; then
    usermod -aG docker "$utilisateur_reel"
    info "Utilisateur '$utilisateur_reel' ajouté au groupe docker. Reconnectez-vous pour que ça prenne effet."
  fi
}


# =============================================================================
# Étape 3 — Récupération ou copie du projet
# =============================================================================

installer_projet() {
  info "Installation du projet dans $APP_DIR..."

  if [[ -d "$APP_DIR" ]]; then
    warn "Le répertoire $APP_DIR existe déjà."
    if [[ -f "$APP_DIR/.env" ]]; then
      cp "$APP_DIR/.env" "/tmp/.env_backup_$(date +%s)"
      info "Sauvegarde du .env existant dans /tmp."
    fi
  else
    mkdir -p "$APP_DIR"
  fi

  if commande_existe git && [[ "$REPO_URL" != "LOCAL" ]]; then
    info "Clonage depuis $REPO_URL..."
    git clone --depth 1 "$REPO_URL" "$APP_DIR" 2>/dev/null \
      || git -C "$APP_DIR" pull --ff-only 2>/dev/null \
      || warn "Clonage échoué — vérifiez l'URL et vos accès réseau. Tentative de copie locale."
  fi

  # Si le clone a échoué ou si on est en mode LOCAL, copier les fichiers locaux
  if [[ ! -f "$APP_DIR/docker-compose.yml" ]]; then
    info "Copie des fichiers locaux vers $APP_DIR..."
    cp -r . "$APP_DIR/"
  fi

  [[ -f "$APP_DIR/docker-compose.yml" ]] || err "docker-compose.yml introuvable dans $APP_DIR. Vérifiez la source du projet."
  log "Projet installé dans $APP_DIR."
}


# =============================================================================
# Étape 4 — Configuration du fichier .env
# =============================================================================

configurer_env() {
  local env_file="$APP_DIR/.env"

  if [[ -f "$env_file" ]]; then
    info "Un fichier .env existe déjà. On conserve les valeurs actuelles."
    if ! grep -q "SECRET_KEY" "$env_file"; then
      warn ".env incomplet — ajout des variables manquantes."
      completer_env "$env_file"
    fi
    return
  fi

  info "Génération du fichier .env avec des secrets aléatoires..."

  local secret_key auth_pass planning_pass emarg_pass

  if [[ "$MODE" == "--dev" ]]; then
    secret_key="dev_secret_change_en_prod_absolument"
    auth_pass="auth_pass_dev"
    planning_pass="planning_pass_dev"
    emarg_pass="emarg_pass_dev"
    warn "Mode DEV : mots de passe simplifiés. Ne JAMAIS utiliser en production."
  else
    secret_key=$(generer_secret 48)
    auth_pass=$(generer_secret 24)
    planning_pass=$(generer_secret 24)
    emarg_pass=$(generer_secret 24)
  fi

  cat > "$env_file" <<EOF
# ──────────────────────────────────────────────────────────────────────────────
# Fichier de configuration — Application de Gestion des Présences
# Généré automatiquement le $(date '+%Y-%m-%d à %H:%M:%S')
# Mode : ${MODE:-prod}
#
# IMPORTANT : ne jamais committer ce fichier dans un dépôt Git public.
# Le fichier .gitignore doit contenir ".env" sur une ligne dédiée.
# ──────────────────────────────────────────────────────────────────────────────

# ── Clé secrète JWT — CHANGER ABSOLUMENT en production ───────────────────────
SECRET_KEY=${secret_key}

# ── Durée de vie des tokens JWT (en heures) ──────────────────────────────────
JWT_DUREE_HEURES=24

# ── Base de données auth_service ──────────────────────────────────────────────
AUTH_DB_NAME=auth_db
AUTH_DB_USER=auth_user
AUTH_DB_PASS=${auth_pass}

# ── Base de données planning_service ─────────────────────────────────────────
PLANNING_DB_NAME=planning_db
PLANNING_DB_USER=planning_user
PLANNING_DB_PASS=${planning_pass}

# ── Base de données emargement_service ───────────────────────────────────────
EMARG_DB_NAME=emarg_db
EMARG_DB_USER=emarg_user
EMARG_DB_PASS=${emarg_pass}

# ── Configuration SMTP ───────────────────────────────────────────────────────
# Laisser MAIL_USERNAME et MAIL_PASSWORD vides pour utiliser Mailhog (dev)
MAIL_SERVER=mailhog
MAIL_PORT=1025
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_SENDER=noreply@ecole.fr

# ── Identifiants par défaut (à changer après première connexion) ──────────────
DEFAULT_ADMIN_EMAIL=${DEFAULT_ADMIN_EMAIL}
DEFAULT_ADMIN_PASSWORD=${DEFAULT_ADMIN_PASSWORD}
DEFAULT_FORMATEUR_EMAIL=${DEFAULT_FORMATEUR_EMAIL}
DEFAULT_FORMATEUR_PASSWORD=${DEFAULT_FORMATEUR_PASSWORD}
EOF

  chmod 600 "$env_file"
  log "Fichier .env généré et sécurisé (chmod 600)."
}

completer_env() {
  local env_file="$1"
  local secret_key
  secret_key=$(generer_secret 48)
  {
    echo ""
    echo "# Variables ajoutées automatiquement le $(date '+%Y-%m-%d')"
    grep -q "SECRET_KEY"       "$env_file" || echo "SECRET_KEY=${secret_key}"
    grep -q "AUTH_DB_NAME"     "$env_file" || echo "AUTH_DB_NAME=auth_db"
    grep -q "AUTH_DB_USER"     "$env_file" || echo "AUTH_DB_USER=auth_user"
    grep -q "AUTH_DB_PASS"     "$env_file" || echo "AUTH_DB_PASS=$(generer_secret 24)"
    grep -q "PLANNING_DB_NAME" "$env_file" || echo "PLANNING_DB_NAME=planning_db"
    grep -q "PLANNING_DB_USER" "$env_file" || echo "PLANNING_DB_USER=planning_user"
    grep -q "PLANNING_DB_PASS" "$env_file" || echo "PLANNING_DB_PASS=$(generer_secret 24)"
    grep -q "EMARG_DB_NAME"    "$env_file" || echo "EMARG_DB_NAME=emarg_db"
    grep -q "EMARG_DB_USER"    "$env_file" || echo "EMARG_DB_USER=emarg_user"
    grep -q "EMARG_DB_PASS"    "$env_file" || echo "EMARG_DB_PASS=$(generer_secret 24)"
    grep -q "MAIL_SERVER"      "$env_file" || echo "MAIL_SERVER=mailhog"
    grep -q "MAIL_PORT"        "$env_file" || echo "MAIL_PORT=1025"
    grep -q "MAIL_USERNAME"    "$env_file" || echo "MAIL_USERNAME="
    grep -q "MAIL_PASSWORD"    "$env_file" || echo "MAIL_PASSWORD="
    grep -q "MAIL_SENDER"      "$env_file" || echo "MAIL_SENDER=noreply@ecole.fr"
  } >> "$env_file"
}


# =============================================================================
# Étape 5 — Construction et démarrage des conteneurs
# =============================================================================

demarrer_application() {
  info "Construction et démarrage des conteneurs..."

  cd "$APP_DIR"

  docker compose build --quiet 2>&1 | while IFS= read -r ligne; do
    echo "  $ligne"
  done

  docker compose up -d

  log "Conteneurs lancés. Attente des healthchecks..."

  # On attend que les bases de données soient prêtes
  attendre_healthy "presence_finale-auth_db-1"     60
  attendre_healthy "presence_finale-planning_db-1" 60
  attendre_healthy "presence_finale-emarg_db-1"    60

  log "Toutes les bases de données sont prêtes."
}


# =============================================================================
# Étape 6 — Injection des données de démo (seed)
# =============================================================================

seeder_donnees() {
  info "Injection des données initiales (seed)..."

  # On laisse Flask-Migrate initialiser les schémas
  sleep 8

  local token
  local auth_url="http://localhost:5001"
  local planning_url="http://localhost:5002"
  local emarg_url="http://localhost:5003"

  # Création du compte administrateur par défaut
  local reponse_admin
  reponse_admin=$(curl -sf -X POST \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${DEFAULT_ADMIN_EMAIL}\",\"password\":\"${DEFAULT_ADMIN_PASSWORD}\",\"prenom\":\"Admin\",\"nom\":\"CNAM\",\"role\":\"admin\"}" \
    "$auth_url/auth/register" 2>/dev/null) \
    || warn "Compte admin déjà existant ou auth_service non prêt — on continue."
  [[ -n "$reponse_admin" ]] && log "Compte administrateur créé : $DEFAULT_ADMIN_EMAIL"

  # Création du compte formateur par défaut
  local reponse_form
  reponse_form=$(curl -sf -X POST \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${DEFAULT_FORMATEUR_EMAIL}\",\"password\":\"${DEFAULT_FORMATEUR_PASSWORD}\",\"prenom\":\"Jean\",\"nom\":\"Martin\",\"role\":\"formateur\"}" \
    "$auth_url/auth/register" 2>/dev/null) \
    || warn "Compte formateur déjà existant — on continue."
  [[ -n "$reponse_form" ]] && log "Compte formateur créé : $DEFAULT_FORMATEUR_EMAIL"

  # Récupération du token admin pour les appels suivants
  local login_reponse
  login_reponse=$(curl -sf -X POST \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${DEFAULT_ADMIN_EMAIL}\",\"password\":\"${DEFAULT_ADMIN_PASSWORD}\"}" \
    "$auth_url/auth/login" 2>/dev/null) || { warn "Connexion admin échouée — seed partiel."; return; }

  token=$(echo "$login_reponse" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
  [[ -z "$token" ]] && { warn "Token non récupéré — seed partiel."; return; }

  # Création d'une classe de démonstration
  local classe_id
  local classe_resp
  classe_resp=$(curl -sf -X POST \
    -H "Authorization: Bearer $token" \
    -H "Content-Type: application/json" \
    -d '{"nom":"DevOps","code":"DEVOPS","description":"Parcours DevOps CNAM Paris"}' \
    "$planning_url/planning/classes" 2>/dev/null) || { warn "Création classe échouée."; return; }
  classe_id=$(echo "$classe_resp" | grep -o '"id":[0-9]*' | head -1 | cut -d: -f2)
  [[ -n "$classe_id" ]] && log "Classe 'DevOps' créée (ID: $classe_id)."

  # Création d'une promotion de démonstration
  if [[ -n "${classe_id:-}" ]]; then
    local promo_id
    local promo_resp
    promo_resp=$(curl -sf -X POST \
      -H "Authorization: Bearer $token" \
      -H "Content-Type: application/json" \
      -d "{\"nom\":\"Groupe A\",\"annee\":\"2025-2026\",\"classe_id\":${classe_id}}" \
      "$planning_url/planning/promotions" 2>/dev/null) || warn "Création promotion échouée."
    promo_id=$(echo "$promo_resp" | grep -o '"id":[0-9]*' | head -1 | cut -d: -f2)
    [[ -n "$promo_id" ]] && log "Promotion 'Groupe A 2025-2026' créée (ID: $promo_id)."
  fi

  log "Seed terminé."
}


# =============================================================================
# Étape 7 — Vérification finale des endpoints /health
# =============================================================================

verifier_demarrage() {
  info "Vérification de l'état des services..."
  local tous_ok=true

  local services=(
    "auth_service:5001"
    "planning_service:5002"
    "emargement_service:5003"
    "frontend_service:5000"
  )

  sleep 5

  for service_port in "${services[@]}"; do
    local service="${service_port%%:*}"
    local port="${service_port##*:}"
    local url="http://localhost:${port}/health"

    if curl -sf "$url" &>/dev/null; then
      log "$service répond sur le port $port."
    else
      warn "$service ne répond pas encore sur $port."
      tous_ok=false
    fi
  done

  if [[ "$tous_ok" == true ]]; then
    log "Tous les services sont opérationnels."
  else
    warn "Certains services ne répondent pas encore. Attendez 30 secondes et vérifiez avec :"
    echo "     docker compose logs -f"
  fi
}


# =============================================================================
# Étape 8 — Résumé final
# =============================================================================

afficher_resume() {
  echo ""
  echo -e "${GRAS}${VERT}═══════════════════════════════════════════════════════════${NC}"
  echo -e "${GRAS}${VERT}   Installation terminée avec succès !${NC}"
  echo -e "${GRAS}${VERT}═══════════════════════════════════════════════════════════${NC}"
  echo ""
  echo -e "  ${GRAS}Accès à l'application :${NC}"
  echo -e "    Interface web     :  ${BLEU}http://localhost:5000${NC}"
  echo -e "    Mailhog (emails)  :  ${BLEU}http://localhost:8025${NC}"
  echo -e "    auth_service      :  http://localhost:5001/health"
  echo -e "    planning_service  :  http://localhost:5002/health"
  echo -e "    emargement        :  http://localhost:5003/health"
  echo ""
  echo -e "  ${GRAS}Identifiants par défaut :${NC}"
  echo -e "    Admin     : ${JAUNE}${DEFAULT_ADMIN_EMAIL}${NC}  /  ${JAUNE}${DEFAULT_ADMIN_PASSWORD}${NC}"
  echo -e "    Formateur : ${JAUNE}${DEFAULT_FORMATEUR_EMAIL}${NC}  /  ${JAUNE}${DEFAULT_FORMATEUR_PASSWORD}${NC}"
  echo -e "    ${ROUGE}⚠  Changez ces mots de passe avant toute utilisation réelle.${NC}"
  echo ""
  echo -e "  ${GRAS}Commandes utiles :${NC}"
  echo -e "    Voir les logs     :  cd $APP_DIR && docker compose logs -f"
  echo -e "    Arrêter           :  cd $APP_DIR && docker compose down"
  echo -e "    Redémarrer        :  cd $APP_DIR && docker compose up -d"
  echo -e "    Rebuild complet   :  cd $APP_DIR && docker compose up --build"
  echo ""
  echo -e "  ${GRAS}Gestion des utilisateurs :${NC}"
  echo -e "    bash manage_users.sh --help"
  echo ""
  echo -e "  ${GRAS}Sauvegarde des données :${NC}"
  echo -e "    bash backup_db.sh"
  echo ""
}


# =============================================================================
# Point d'entrée principal
# =============================================================================

main() {
  banniere

  verifier_systeme
  installer_docker
  installer_projet
  configurer_env
  demarrer_application
  seeder_donnees
  verifier_demarrage
  afficher_resume
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
