#!/bin/bash
# =============================================================
#  Script d'installation - Système de gestion des présences
# =============================================================

set -e  # Arrêt immédiat en cas d'erreur

# ---- Couleurs pour l'affichage ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
log_success() { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warning() { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error()   { echo -e "${RED}[ERREUR]${NC} $1"; exit 1; }

echo ""
echo "============================================="
echo "   Système de Gestion des Présences"
echo "   Installation automatisée"
echo "============================================="
echo ""

# =============================================================
# ÉTAPE 1 — Vérification des prérequis
# =============================================================
log_info "Vérification des prérequis..."

# Docker
if ! command -v docker &> /dev/null; then
    log_error "Docker n'est pas installé. Installez Docker Desktop : https://www.docker.com/products/docker-desktop"
fi
log_success "Docker trouvé : $(docker --version)"

# Docker Compose
if ! command -v docker compose &> /dev/null && ! command -v docker-compose &> /dev/null; then
    log_error "Docker Compose n'est pas disponible. Il est inclus dans Docker Desktop."
fi
log_success "Docker Compose disponible"

# Vérifier que Docker est démarré
if ! docker info &> /dev/null; then
    log_error "Docker n'est pas démarré. Lancez Docker Desktop puis relancez ce script."
fi
log_success "Docker est en cours d'exécution"

# =============================================================
# ÉTAPE 2 — Localisation du projet
# =============================================================
log_info "Recherche du dossier presence_app..."

# Chercher le dossier contenant docker-compose.yml
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
    APP_DIR="$SCRIPT_DIR"
elif [ -f "$SCRIPT_DIR/presence_app/docker-compose.yml" ]; then
    APP_DIR="$SCRIPT_DIR/presence_app"
else
    log_error "Impossible de trouver docker-compose.yml. Placez ce script dans le même dossier que le projet presence_app."
fi

log_success "Projet trouvé dans : $APP_DIR"
cd "$APP_DIR"

# =============================================================
# ÉTAPE 3 — Configuration optionnelle de l'envoi d'email
# =============================================================
echo ""
echo -e "${YELLOW}--- Configuration email (optionnel) ---${NC}"
echo "L'application peut envoyer des feuilles de présence par email."
echo "Vous aurez besoin d'un compte Gmail avec un 'mot de passe d'application'."
echo ""
read -p "Voulez-vous configurer l'envoi d'email maintenant ? (o/N) : " CONFIGURE_MAIL

if [[ "$CONFIGURE_MAIL" =~ ^[Oo]$ ]]; then
    read -p "Adresse Gmail : " MAIL_USER
    read -s -p "Mot de passe d'application Gmail : " MAIL_PASS
    echo ""

    # Modifier le docker-compose.yml avec les identifiants fournis
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s|MAIL_USERNAME: \"\"|MAIL_USERNAME: \"$MAIL_USER\"|" docker-compose.yml
        sed -i '' "s|MAIL_PASSWORD: \"\"|MAIL_PASSWORD: \"$MAIL_PASS\"|" docker-compose.yml
    else
        # Linux
        sed -i "s|MAIL_USERNAME: \"\"|MAIL_USERNAME: \"$MAIL_USER\"|" docker-compose.yml
        sed -i "s|MAIL_PASSWORD: \"\"|MAIL_PASSWORD: \"$MAIL_PASS\"|" docker-compose.yml
    fi
    log_success "Configuration email enregistrée"
else
    log_warning "Email non configuré — la fonctionnalité d'envoi sera désactivée"
fi

# =============================================================
# ÉTAPE 4 — Construction et démarrage des containers
# =============================================================
echo ""
log_info "Construction des images Docker (peut prendre 2-5 minutes)..."

# Utiliser docker compose (v2) ou docker-compose (v1)
if command -v docker compose &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

# Arrêter d'éventuels containers existants
log_info "Arrêt des anciens containers s'ils existent..."
$COMPOSE_CMD down --remove-orphans 2>/dev/null || true

# Build + démarrage en arrière-plan
$COMPOSE_CMD up -d --build


log_success "Containers démarrés"

# =============================================================
# ÉTAPE 5 — Attente que les services soient prêts
# =============================================================
log_info "Attente du démarrage des services..."

MAX_WAIT=90
ELAPSED=0

check_service() {
    local url=$1
    curl -s --max-time 2 "$url" > /dev/null 2>&1
    return $?
}

while [ $ELAPSED -lt $MAX_WAIT ]; do
    if check_service "http://localhost:5000"; then
        break
    fi
    echo -n "."
    sleep 3
    ELAPSED=$((ELAPSED + 3))
done
echo ""

if [ $ELAPSED -ge $MAX_WAIT ]; then
    log_warning "Les services tardent à démarrer. Vérifiez les logs : $COMPOSE_CMD logs"
else
    log_success "Services prêts après ${ELAPSED}s"
fi

# =============================================================
# ÉTAPE 6 — Vérification de l'état des services
# =============================================================
echo ""
log_info "État des containers :"
$COMPOSE_CMD ps

# =============================================================
# RÉSUMÉ FINAL
# =============================================================
echo ""
echo "============================================="
echo -e "${GREEN}  Installation terminée avec succès !${NC}"
echo "============================================="
echo ""
echo "  🌐 Interface web     : http://localhost:5000"
echo "  🔐 Auth service      : http://localhost:5001"
echo "  📅 Planning service  : http://localhost:5002"
echo "  📋 Émargement service: http://localhost:5003"
echo ""
echo "  Compte administrateur par défaut :"
echo "  - Email    : admin@ecole.fr"
echo "  - Mot de passe : admin123"
echo ""
echo "  Commandes utiles :"
echo "  - Voir les logs     : $COMPOSE_CMD logs -f"
echo "  - Arrêter           : $COMPOSE_CMD down"
echo "  - Redémarrer        : $COMPOSE_CMD restart"
echo "  - Réinstaller tout  : $COMPOSE_CMD down -v && $COMPOSE_CMD up --build -d"
echo ""

# Ouvrir le navigateur automatiquement si possible
if command -v xdg-open &> /dev/null; then
    xdg-open "http://localhost:5000" &
elif command -v open &> /dev/null; then
    open "http://localhost:5000"
fi
