#!/usr/bin/env bash
# =============================================================================
# manage_users.sh
# Script de gestion des utilisateurs — Application de Gestion des Présences
#
# Auteur  : Diarra Salif — DSP DevOps 2025/2026 — CNAM Paris
# Version : 1.1
# Usage   : bash manage_users.sh [commande] [options]
#
# Ce script interagit avec auth_service via l'API REST. Il ne touche jamais
# directement à la base de données — tout passe par les endpoints officiels.
#
# Commandes disponibles :
#   lister                   Liste tous les utilisateurs
#   creer                    Crée un nouvel utilisateur (interactif)
#   modifier <id>            Modifie un utilisateur (rôle, nom, statut)
#   desactiver <id>          Désactive un compte (suppression douce — RGPD)
#   reactiver <id>           Réactive un compte désactivé
#   reset-mdp <id>           Réinitialise le mot de passe
#   import <fichier.csv>     Importe des étudiants en masse depuis un CSV
#   status                   Vérifie l'état de tous les services
#   (aucune commande)        Lance le menu interactif
#
# Prérequis : curl, jq (installé automatiquement si absent)
# =============================================================================

set -euo pipefail
IFS=$'\n\t'

# ─── Configuration ────────────────────────────────────────────────────────────
AUTH_URL="${AUTH_URL:-http://localhost:5001}"
PLANNING_URL="${PLANNING_URL:-http://localhost:5002}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@ecole.fr}"
TOKEN_FILE="/tmp/.presence_token"   # Token JWT en cache pour éviter la reconnexion à chaque commande

# ─── Couleurs ─────────────────────────────────────────────────────────────────
ROUGE='\033[0;31m'; VERT='\033[0;32m'; JAUNE='\033[1;33m'
BLEU='\033[0;34m'; GRAS='\033[1m'; NC='\033[0m'

log()  { echo -e "${VERT}[OK]${NC}  $*"; }
info() { echo -e "${BLEU}[INFO]${NC} $*"; }
warn() { echo -e "${JAUNE}[AVERT]${NC} $*"; }
err()  { echo -e "${ROUGE}[ERR]${NC}  $*" >&2; exit 1; }


# =============================================================================
# Gestion des dépendances
# =============================================================================

verifier_dependances() {
  command -v curl &>/dev/null || err "curl n'est pas installé. Installez-le : apt-get install curl"

  if ! command -v jq &>/dev/null; then
    warn "jq n'est pas installé. Tentative d'installation automatique..."
    if command -v apt-get &>/dev/null; then
      sudo apt-get install -y -qq jq
    elif command -v brew &>/dev/null; then
      brew install jq -q
    elif command -v yum &>/dev/null; then
      sudo yum install -y -q jq
    else
      err "Installez jq manuellement : https://stedolan.github.io/jq/download/"
    fi
    log "jq installé."
  fi
}


# =============================================================================
# Authentification — gestion du token JWT en cache
# =============================================================================

charger_token() {
  # Vérifie si un token valide est en cache
  if [[ -f "$TOKEN_FILE" ]]; then
    local token
    token=$(cat "$TOKEN_FILE")
    local code
    code=$(curl -sf -o /dev/null -w "%{http_code}" \
      -H "Authorization: Bearer $token" \
      "$AUTH_URL/me" 2>/dev/null || echo "000")
    if [[ "$code" == "200" ]]; then
      echo "$token"
      return
    fi
    rm -f "$TOKEN_FILE"
  fi

  # Pas de token valide : demande les credentials
  # IMPORTANT : tous les echo/info/log ici doivent aller sur stderr (>&2)
  # car charger_token() est appelée en substitution $(charger_token) —
  # tout ce qui va sur stdout devient la valeur retournée (le token).
  info "Connexion à auth_service ($AUTH_URL)..." >&2
  echo -n "  Email admin [${ADMIN_EMAIL}] : " >&2
  read -r email_saisi
  local email="${email_saisi:-$ADMIN_EMAIL}"

  echo -n "  Mot de passe : " >&2
  read -rs mdp
  echo "" >&2

  local reponse
  reponse=$(curl -sf -X POST \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${email}\",\"password\":\"${mdp}\"}" \
    "$AUTH_URL/auth/login" 2>/dev/null) \
    || err "Connexion échouée. Vérifiez que auth_service est démarré (docker compose ps)."

  local token
  token=$(echo "$reponse" | jq -r '.token // empty')
  [[ -z "$token" ]] && err "Identifiants incorrects ou compte bloqué (5 tentatives max — attendre 15 min)."

  echo "$token" > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
  log "Connecté. Token mis en cache." >&2
  echo "$token"
}

# Raccourcis pour les appels API authentifiés
api_get()  { curl -sf -H "Authorization: Bearer $(charger_token)" "$AUTH_URL$1"; }
api_post() { curl -sf -X POST  -H "Authorization: Bearer $(charger_token)" -H "Content-Type: application/json" -d "$2" "$AUTH_URL$1"; }
api_put()  { curl -sf -X PUT   -H "Authorization: Bearer $(charger_token)" -H "Content-Type: application/json" -d "$2" "$AUTH_URL$1"; }
api_del()  { curl -sf -X DELETE -H "Authorization: Bearer $(charger_token)" "$AUTH_URL$1"; }


# =============================================================================
# Commande : lister les utilisateurs
# =============================================================================

cmd_lister() {
  info "Récupération de la liste des utilisateurs..."

  local reponse
  reponse=$(api_get "/auth/users") \
    || err "Impossible de récupérer les utilisateurs. Vérifiez vos droits admin."

  local nb
  nb=$(echo "$reponse" | jq '.users | length')

  echo ""
  echo -e "${GRAS}  Utilisateurs enregistrés (${nb}) :${NC}"
  echo "  ──────────────────────────────────────────────────────────────────────"
  printf "  %-5s %-32s %-20s %-12s %-8s\n" "ID" "EMAIL" "NOM PRÉNOM" "RÔLE" "ACTIF"
  echo "  ──────────────────────────────────────────────────────────────────────"

  echo "$reponse" | jq -r '.users[] | [.id, .email, (.prenom + " " + .nom), .role, (if .is_active then "oui" else "NON" end)] | @tsv' \
    | while IFS=$'\t' read -r id email nom role actif; do
        local couleur_role=""
        [[ "$role" == "admin" ]] && couleur_role="$JAUNE" || couleur_role="$BLEU"
        local couleur_actif=""
        [[ "$actif" == "oui" ]] && couleur_actif="$VERT" || couleur_actif="$ROUGE"
        printf "  %-5s %-32s %-20s ${couleur_role}%-12s${NC} ${couleur_actif}%-8s${NC}\n" \
          "$id" "$email" "$nom" "$role" "$actif"
      done

  echo "  ──────────────────────────────────────────────────────────────────────"
  echo ""
}


# =============================================================================
# Commande : créer un utilisateur
# =============================================================================

cmd_creer() {
  echo ""
  echo -e "${GRAS}  Création d'un nouvel utilisateur${NC}"
  echo "  ───────────────────────────────"

  echo -n "  Email        : "; read -r email
  echo -n "  Prénom       : "; read -r prenom
  echo -n "  Nom          : "; read -r nom
  echo -n "  Rôle [formateur/admin] (défaut: formateur) : "; read -r role
  role="${role:-formateur}"

  # Validation
  [[ -z "$email" || -z "$prenom" || -z "$nom" ]] && err "Email, prénom et nom sont obligatoires."
  [[ "$email" != *"@"* ]] && err "Format d'email invalide."
  [[ "$role" != "formateur" && "$role" != "admin" ]] && err "Rôle invalide. Choisissez 'formateur' ou 'admin'."

  echo -n "  Mot de passe (8 car. min.) : "; read -rs mdp; echo ""
  echo -n "  Confirmation              : "; read -rs mdp2; echo ""
  [[ "$mdp" != "$mdp2" ]] && err "Les mots de passe ne correspondent pas."
  [[ ${#mdp} -lt 8 ]] && err "Le mot de passe doit faire au moins 8 caractères."

  local payload
  payload=$(jq -n \
    --arg email   "$email" \
    --arg prenom  "$prenom" \
    --arg nom     "$nom" \
    --arg role    "$role" \
    --arg password "$mdp" \
    '{email: $email, prenom: $prenom, nom: $nom, role: $role, password: $password}')

  local reponse
  reponse=$(api_post "/auth/users" "$payload") \
    || err "Création échouée. L'email est peut-être déjà utilisé (HTTP 409)."

  local user_id
  user_id=$(echo "$reponse" | jq -r '.user.id // "?"')
  log "Utilisateur créé avec succès (ID: $user_id)."
  echo ""
  echo "$reponse" | jq -r '"  → " + .user.prenom + " " + .user.nom + " <" + .user.email + "> — rôle : " + .user.role'
  echo ""
}


# =============================================================================
# Commande : modifier un utilisateur
# =============================================================================

cmd_modifier() {
  local user_id="${1:-}"
  [[ -z "$user_id" ]] && { echo -n "  ID de l'utilisateur à modifier : "; read -r user_id; }

  echo ""
  echo -e "${GRAS}  Modification de l'utilisateur #${user_id}${NC}"
  echo "  (Laissez vide pour conserver la valeur actuelle)"
  echo "  ─────────────────────────────────────────────────"

  echo -n "  Nouveau prénom              : "; read -r nouveau_prenom
  echo -n "  Nouveau nom                 : "; read -r nouveau_nom
  echo -n "  Nouveau rôle [formateur/admin] : "; read -r nouveau_role
  echo -n "  Nouveau mot de passe (vide = inchangé) : "; read -rs nouveau_mdp; echo ""
  echo -n "  Activer/désactiver [oui/non] (vide = inchangé) : "; read -r nouveau_actif

  # Construction du payload JSON avec uniquement les champs renseignés
  local payload="{}"
  [[ -n "$nouveau_prenom" ]] && payload=$(echo "$payload" | jq --arg v "$nouveau_prenom" '. + {prenom: $v}')
  [[ -n "$nouveau_nom"    ]] && payload=$(echo "$payload" | jq --arg v "$nouveau_nom"    '. + {nom: $v}')
  [[ -n "$nouveau_role"   ]] && {
    [[ "$nouveau_role" != "formateur" && "$nouveau_role" != "admin" ]] && err "Rôle invalide."
    payload=$(echo "$payload" | jq --arg v "$nouveau_role" '. + {role: $v}')
  }
  [[ -n "$nouveau_mdp" ]] && {
    [[ ${#nouveau_mdp} -lt 8 ]] && err "Le mot de passe doit faire au moins 8 caractères."
    payload=$(echo "$payload" | jq --arg v "$nouveau_mdp" '. + {password: $v}')
  }
  if   [[ "$nouveau_actif" == "oui" ]]; then payload=$(echo "$payload" | jq '. + {is_active: true}')
  elif [[ "$nouveau_actif" == "non" ]]; then payload=$(echo "$payload" | jq '. + {is_active: false}')
  fi

  if [[ "$payload" == "{}" ]]; then
    info "Aucune modification saisie. Opération annulée."; return
  fi

  local reponse
  reponse=$(api_put "/auth/users/${user_id}" "$payload") \
    || err "Modification échouée. Vérifiez l'ID utilisateur."

  log "Utilisateur #${user_id} mis à jour."
  echo "$reponse" | jq -r '"  → " + .user.prenom + " " + .user.nom + " — rôle : " + .user.role + (if .user.is_active then " — actif" else " — DÉSACTIVÉ" end)'
  echo ""
}


# =============================================================================
# Commande : désactiver un utilisateur (suppression douce — RGPD)
# =============================================================================

cmd_desactiver() {
  local user_id="${1:-}"
  [[ -z "$user_id" ]] && { echo -n "  ID de l'utilisateur à désactiver : "; read -r user_id; }

  # Vérification que ce n'est pas le dernier admin
  local nb_admins
  nb_admins=$(api_get "/auth/users" | jq '[.users[] | select(.role == "admin" and .is_active == true)] | length')
  if [[ "$nb_admins" -le 1 ]]; then
    local role_cible
    role_cible=$(api_get "/auth/users" | jq -r ".users[] | select(.id == ${user_id}) | .role")
    if [[ "$role_cible" == "admin" ]]; then
      err "Impossible de désactiver le dernier administrateur actif. Créez d'abord un autre admin."
    fi
  fi

  warn "Désactivation de l'utilisateur #${user_id}. L'utilisateur ne pourra plus se connecter."
  warn "Les données sont conservées conformément au RGPD (désactivation douce)."
  echo -n "  Confirmer ? [oui/N] : "
  read -r confirmation
  [[ "$confirmation" != "oui" ]] && { info "Opération annulée."; return; }

  local reponse
  reponse=$(api_put "/auth/users/${user_id}" '{"is_active": false}') \
    || err "Désactivation échouée. Vérifiez l'ID utilisateur."

  log "Utilisateur #${user_id} désactivé."
  echo ""
}


# =============================================================================
# Commande : réactiver un utilisateur
# =============================================================================

cmd_reactiver() {
  local user_id="${1:-}"
  [[ -z "$user_id" ]] && { echo -n "  ID de l'utilisateur à réactiver : "; read -r user_id; }

  local reponse
  reponse=$(api_put "/auth/users/${user_id}" '{"is_active": true}') \
    || err "Réactivation échouée. Vérifiez l'ID utilisateur."

  log "Utilisateur #${user_id} réactivé. Il peut de nouveau se connecter."
  echo ""
}


# =============================================================================
# Commande : réinitialiser le mot de passe
# =============================================================================

cmd_reset_mdp() {
  local user_id="${1:-}"
  [[ -z "$user_id" ]] && { echo -n "  ID de l'utilisateur : "; read -r user_id; }

  echo -n "  Nouveau mot de passe (8 car. min.) : "; read -rs mdp; echo ""
  echo -n "  Confirmation                       : "; read -rs mdp2; echo ""

  [[ "$mdp" != "$mdp2" ]] && err "Les mots de passe ne correspondent pas."
  [[ ${#mdp} -lt 8 ]] && err "Le mot de passe doit faire au moins 8 caractères."

  local payload
  payload=$(jq -n --arg p "$mdp" '{password: $p}')

  local reponse
  reponse=$(api_put "/auth/users/${user_id}" "$payload") \
    || err "Réinitialisation échouée. Vérifiez l'ID utilisateur."

  log "Mot de passe de l'utilisateur #${user_id} mis à jour."
  echo ""
}


# =============================================================================
# Commande : import en masse d'étudiants depuis un CSV
# =============================================================================

cmd_import_csv() {
  local fichier_csv="${1:-}"

  if [[ -z "$fichier_csv" ]]; then
    echo -n "  Chemin vers le fichier CSV : "; read -r fichier_csv
  fi

  [[ ! -f "$fichier_csv" ]] && err "Fichier introuvable : $fichier_csv"

  # Vérification de l'extension
  local ext="${fichier_csv##*.}"
  [[ "$ext" != "csv" && "$ext" != "xlsx" && "$ext" != "xls" ]] \
    && warn "Extension non reconnue ($ext). Formats supportés : csv, xlsx. On tente quand même."

  local token
  token=$(charger_token)

  echo -n "  ID de la promotion cible : "; read -r promo_id
  [[ -z "$promo_id" ]] && err "L'ID de promotion est obligatoire."

  # Vérification que la promotion existe
  local promo_check
  promo_check=$(curl -sf -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer ${token}" \
    "${PLANNING_URL}/planning/promotions/${promo_id}" 2>/dev/null || echo "000")
  [[ "$promo_check" != "200" ]] && err "Promotion #${promo_id} introuvable (HTTP $promo_check)."

  info "Import de '$fichier_csv' dans la promotion #${promo_id}..."

  local reponse
  reponse=$(curl -sf \
    -H "Authorization: Bearer ${token}" \
    -F "promotion_id=${promo_id}" \
    -F "fichier=@${fichier_csv}" \
    "${PLANNING_URL}/planning/etudiants/import-csv") \
    || err "Import échoué. Vérifiez que planning_service est démarré."

  local inseres doublons_fichier doublons_base erreurs
  inseres=$(echo         "$reponse" | jq -r '.inseres // 0')
  doublons_fichier=$(echo "$reponse" | jq -r '.doublons_fichier // 0')
  doublons_base=$(echo    "$reponse" | jq -r '.doublons_base // 0')
  erreurs=$(echo          "$reponse" | jq -r '.erreurs | length')

  echo ""
  log "Import terminé."
  echo -e "  Étudiants insérés          : ${VERT}${inseres}${NC}"
  echo -e "  Doublons dans le fichier   : ${JAUNE}${doublons_fichier}${NC}"
  echo -e "  Doublons déjà en base      : ${JAUNE}${doublons_base}${NC}"
  echo -e "  Lignes en erreur           : ${ROUGE}${erreurs}${NC}"

  if [[ $erreurs -gt 0 ]]; then
    echo ""
    warn "Détail des erreurs :"
    echo "$reponse" | jq -r '.erreurs[]' | while IFS= read -r ligne_err; do
      echo "  → $ligne_err"
    done
  fi
  echo ""
}


# =============================================================================
# Commande : vérifier l'état des services
# =============================================================================

cmd_status() {
  echo ""
  echo -e "${GRAS}  État des services${NC}"
  echo "  ─────────────────────────────────────────────────────"

  local services=(
    "frontend_service:5000"
    "auth_service:5001"
    "planning_service:5002"
    "emargement_service:5003"
    "mailhog:8025"
  )

  for svc_port in "${services[@]}"; do
    local svc="${svc_port%%:*}"
    local port="${svc_port##*:}"
    local url="http://localhost:${port}/health"
    # Mailhog n'a pas de /health — on teste juste le port
    [[ "$svc" == "mailhog" ]] && url="http://localhost:${port}"

    local code statut_txt couleur
    code=$(curl -sf -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")

    if [[ "$code" == "200" ]]; then
      statut_txt="OK  (port $port)"
      couleur="$VERT"
    else
      statut_txt="HORS LIGNE (HTTP $code)"
      couleur="$ROUGE"
    fi

    printf "  %-25s ${couleur}%s${NC}\n" "$svc" "$statut_txt"
  done

  echo "  ─────────────────────────────────────────────────────"

  if command -v docker &>/dev/null; then
    echo ""
    echo -e "  ${GRAS}Conteneurs Docker :${NC}"
    docker compose -f /opt/presence_app/docker-compose.yml ps 2>/dev/null \
      | tail -n +2 \
      | while IFS= read -r ligne; do echo "  $ligne"; done \
      || warn "docker compose ps indisponible (projet non trouvé dans /opt/presence_app)."
  fi
  echo ""
}


# =============================================================================
# Menu interactif
# =============================================================================

menu_interactif() {
  while true; do
    echo ""
    echo -e "${GRAS}  Gestion des utilisateurs — Application Présences${NC}"
    echo "  ────────────────────────────────────────────────"
    echo "  1. Lister tous les utilisateurs"
    echo "  2. Créer un nouvel utilisateur"
    echo "  3. Modifier un utilisateur"
    echo "  4. Désactiver un compte"
    echo "  5. Réactiver un compte"
    echo "  6. Réinitialiser un mot de passe"
    echo "  7. Importer des étudiants depuis un CSV"
    echo "  8. Vérifier l'état des services"
    echo "  9. Déconnexion (effacer le token en cache)"
    echo "  0. Quitter"
    echo ""
    echo -n "  Votre choix : "
    read -r choix

    case "$choix" in
      1) cmd_lister ;;
      2) cmd_creer ;;
      3) cmd_modifier ;;
      4) cmd_desactiver ;;
      5) cmd_reactiver ;;
      6) cmd_reset_mdp ;;
      7) cmd_import_csv ;;
      8) cmd_status ;;
      9) rm -f "$TOKEN_FILE"; log "Token supprimé. Reconnexion à la prochaine opération." ;;
      0) info "À bientôt."; exit 0 ;;
      *) warn "Choix invalide (0–9)." ;;
    esac
  done
}


# =============================================================================
# Aide
# =============================================================================

afficher_aide() {
  cat <<EOF

${GRAS}manage_users.sh${NC} — Gestion des utilisateurs · Application Présences
${BLEU}CNAM Paris · DSP DevOps 2025/2026${NC}

${GRAS}Usage :${NC}
  bash manage_users.sh [commande] [options]

${GRAS}Commandes :${NC}
  lister                   Affiche tous les utilisateurs avec leur rôle et statut
  creer                    Crée un nouvel utilisateur (mode interactif)
  modifier <id>            Modifie prénom, nom, rôle, mot de passe ou statut
  desactiver <id>          Désactive un compte (données conservées — RGPD)
  reactiver <id>           Réactive un compte désactivé
  reset-mdp <id>           Réinitialise le mot de passe
  import <fichier>         Importe des étudiants depuis un CSV ou Excel
  status                   Vérifie l'état de tous les services

  (aucune commande)        Lance le menu interactif

${GRAS}Variables d'environnement :${NC}
  AUTH_URL      URL de auth_service  (défaut: http://localhost:5001)
  PLANNING_URL  URL de planning_service (défaut: http://localhost:5002)
  ADMIN_EMAIL   Email admin pré-rempli  (défaut: admin@ecole.fr)

${GRAS}Exemples :${NC}
  bash manage_users.sh lister
  bash manage_users.sh creer
  bash manage_users.sh modifier 3
  bash manage_users.sh desactiver 5
  bash manage_users.sh reset-mdp 2
  bash manage_users.sh import etudiants_promo_A.csv
  AUTH_URL=http://mon-serveur:5001 bash manage_users.sh lister

${GRAS}Format CSV pour import d'étudiants :${NC}
  Colonnes : nom, prenom, email, numero_etudiant (optionnel)
  Séparateur : virgule ou point-virgule (détection automatique)
  Encodage   : UTF-8 recommandé
  Limite     : 5 000 lignes par import

EOF
}


# =============================================================================
# Point d'entrée principal
# =============================================================================

main() {
  verifier_dependances

  local commande="${1:-}"

  case "$commande" in
    lister)         cmd_lister ;;
    creer)          cmd_creer ;;
    modifier)       cmd_modifier "${2:-}" ;;
    desactiver)     cmd_desactiver "${2:-}" ;;
    reactiver)      cmd_reactiver "${2:-}" ;;
    reset-mdp)      cmd_reset_mdp "${2:-}" ;;
    import)         cmd_import_csv "${2:-}" ;;
    status)         cmd_status ;;
    -h|--help|help) afficher_aide ;;
    "")             menu_interactif ;;
    *)
      err "Commande inconnue : '$commande'. Lancez 'bash manage_users.sh --help' pour la liste."
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
