#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -euo pipefail

# Color codes for premium console output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# GCP Artifact Registry Configuration
REGISTRY="europe-west1-docker.pkg.dev/slavayssiere-sandbox-462015/z-gcp-summit-services-dev"
IMAGE_NAME="mcp-claude-memory"
IMAGE_MIGRATIONS_NAME="mcp-claude-memory-db-migrations"
VERSION_FILE="VERSION"
VERSION_LIQUIBASE_FILE="VERSION_LIQUIBASE"

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# --- 0. CHECKING FOR CHANGES ---
FORCE_BUILD=false
for arg in "$@"; do
    if [ "$arg" = "--force" ] || [ "$arg" = "-f" ]; then
        FORCE_BUILD=true
    fi
done

calculate_app_hash() {
    # Find all files in src, tests, specific core files, Dockerfile, requirements.txt, web_ui.py and build.sh
    if command -v md5 &> /dev/null; then
        find src tests Dockerfile requirements.txt web_ui.py build.sh \
            -type f \
            ! -path '*/__pycache__/*' \
            ! -name '*.pyc' \
            ! -name '.app_build_hash' \
            2>/dev/null | sort | xargs md5 | md5
    elif command -v md5sum &> /dev/null; then
        find src tests Dockerfile requirements.txt web_ui.py build.sh \
            -type f \
            ! -path '*/__pycache__/*' \
            ! -name '*.pyc' \
            ! -name '.app_build_hash' \
            2>/dev/null | sort | xargs md5sum | md5sum | awk '{print $1}'
    else
        find src tests Dockerfile requirements.txt web_ui.py build.sh \
            -type f \
            ! -path '*/__pycache__/*' \
            ! -name '*.pyc' \
            ! -name '.app_build_hash' \
            2>/dev/null | sort | xargs stat -f "%m %N" 2>/dev/null | md5 2>/dev/null || stat -c "%Y %n" * 2>/dev/null
    fi
}

calculate_db_hash() {
    # Find all files in database directory (excluding VERSION_LIQUIBASE if inside it)
    if command -v md5 &> /dev/null; then
        find database \
            -type f \
            ! -name 'VERSION' \
            ! -name '.db_build_hash' \
            2>/dev/null | sort | xargs md5 | md5
    elif command -v md5sum &> /dev/null; then
        find database \
            -type f \
            ! -name 'VERSION' \
            ! -name '.db_build_hash' \
            2>/dev/null | sort | xargs md5sum | md5sum | awk '{print $1}'
    else
        find database \
            -type f \
            ! -name 'VERSION' \
            ! -name '.db_build_hash' \
            2>/dev/null | sort | xargs stat -f "%m %N" 2>/dev/null | md5 2>/dev/null || stat -c "%Y %n" * 2>/dev/null
    fi
}

APP_HASH_FILE=".app_build_hash"
DB_HASH_FILE=".db_build_hash"

CURRENT_APP_HASH=$(calculate_app_hash)
CURRENT_DB_HASH=$(calculate_db_hash)

BUILD_APP=false
BUILD_DB=false

log_info "Vérification des modifications dans le code source..."

if [ "$FORCE_BUILD" = "true" ]; then
    BUILD_APP=true
    BUILD_DB=true
    log_info "Build forcé demandé (--force / -f). Build de tous les conteneurs..."
else
    # Vérification des changements pour l'application
    if [ -f "$APP_HASH_FILE" ]; then
        PREVIOUS_APP_HASH=$(cat "$APP_HASH_FILE")
        if [ "$CURRENT_APP_HASH" != "$PREVIOUS_APP_HASH" ]; then
            BUILD_APP=true
            log_info "Modifications détectées dans le code applicatif principal. Build de l'app activé."
        fi
    else
        BUILD_APP=true
        log_info "Aucun build applicatif précédent détecté. Build de l'app activé."
    fi

    # Vérification des changements pour les migrations de base de données
    if [ -f "$DB_HASH_FILE" ]; then
        PREVIOUS_DB_HASH=$(cat "$DB_HASH_FILE")
        if [ "$CURRENT_DB_HASH" != "$PREVIOUS_DB_HASH" ]; then
            BUILD_DB=true
            log_info "Modifications détectées dans les migrations Liquibase (dossier database/). Build des migrations activé."
        fi
    else
        BUILD_DB=true
        log_info "Aucun build de migration précédent détecté. Build des migrations activé."
    fi
fi

if [ "$BUILD_APP" = "false" ] && [ "$BUILD_DB" = "false" ]; then
    log_success "Aucune modification détectée depuis le dernier build. Build ignoré. (Utilisez --force pour forcer le build)"
    exit 0
fi

# --- 1. RUNNING UNIT TESTS (ONLY IF APP BUILDS) ---
if [ "$BUILD_APP" = "true" ]; then
    log_info "Démarrage de la phase de validation (Tests Unitaires applicatifs)..."
    if [ -f "./venv/bin/pytest" ]; then
        log_info "Environnement virtuel détecté. Utilisation de ./venv/bin/pytest..."
        ./venv/bin/pytest tests/ -v
    elif command -v pytest &> /dev/null; then
        log_info "Utilisation de pytest global..."
        pytest tests/ -v
    elif command -v python3 &> /dev/null; then
        log_info "Tentative de lancement des tests via python3 -m pytest..."
        python3 -m pytest tests/ -v
    else
        log_error "Aucun outil de test (pytest) n'a été détecté. Installez les dépendances avec: pip install -r requirements-dev.txt"
        exit 1
    fi
    log_success "Tous les tests unitaires ont réussi ! Passage à la phase de versioning."
fi

# --- 2. SEMANTIC VERSIONING INCREMENT ---
log_info "Gestion du versioning sémantique (SemVer)..."

increment_version() {
    local file=$1
    local default_v=$2
    local current_v
    if [ -f "$file" ]; then
        current_v=$(cat "$file" | tr -d '[:space:]')
    else
        current_v="$default_v"
        log_warn "Fichier $file introuvable. Initialisation à $current_v"
    fi

    # Parse SemVer format (Major.Minor.Patch)
    if [[ $current_v =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
        local major="${BASH_REMATCH[1]}"
        local minor="${BASH_REMATCH[2]}"
        local patch="${BASH_REMATCH[3]}"
        local new_patch=$((patch + 1))
        local new_v="${major}.${minor}.${new_patch}"
    else
        log_warn "Format de version invalide dans $file ('$current_v'). Réinitialisation à 1.0.1"
        local new_v="1.0.1"
    fi
    echo "$new_v" > "$file"
    echo "$new_v"
}

# --- 3. CHECK DOCKER ---
log_info "Vérification de la disponibilité du démon Docker..."
if ! command -v docker &> /dev/null; then
    log_error "Le client Docker n'est pas installé ou n'est pas dans le PATH."
    exit 1
fi

if ! docker info &> /dev/null; then
    log_error "Le démon Docker ne semble pas démarré. Lancez Docker et réessayez."
    exit 1
fi

export DOCKER_BUILDKIT=1

# --- 4. DOCKER BUILD & PUSH ---
if [ "$BUILD_APP" = "true" ]; then
    NEW_APP_VERSION=$(increment_version "$VERSION_FILE" "1.0.0")
    log_success "SemVer applicatif incrémenté avec succès : $NEW_APP_VERSION"
    
    TAG_VERSION="${NEW_APP_VERSION}"
    TAG_V_VERSION="v${NEW_APP_VERSION}"
    TAG_LATEST="latest"

    FULL_TAG_VERSION="${REGISTRY}/${IMAGE_NAME}:${TAG_VERSION}"
    FULL_TAG_V_VERSION="${REGISTRY}/${IMAGE_NAME}:${TAG_V_VERSION}"
    FULL_TAG_LATEST="${REGISTRY}/${IMAGE_NAME}:${TAG_LATEST}"

    log_info "Construction de l'image applicative principale (version: $NEW_APP_VERSION / $TAG_V_VERSION)..."
    if docker build \
        --platform linux/amd64 \
        -t "${FULL_TAG_VERSION}" \
        -t "${FULL_TAG_V_VERSION}" \
        -t "${FULL_TAG_LATEST}" \
        -f Dockerfile .; then
        log_success "Image applicative construite avec succès sous les tags $TAG_VERSION, $TAG_V_VERSION et $TAG_LATEST !"
    else
        log_error "Échec de la construction de l'image applicative."
        exit 1
    fi

    log_info "Poussée de l'image applicative principale..."
    if docker push "${FULL_TAG_VERSION}" && docker push "${FULL_TAG_V_VERSION}" && docker push "${FULL_TAG_LATEST}"; then
        log_success "Image applicative poussée avec succès !"
        # Enregistrer la signature pour la détection de changements ultérieure
        echo "$CURRENT_APP_HASH" > "$APP_HASH_FILE"
    else
        log_error "Échec lors de la poussée de l'image applicative."
        exit 1
    fi
fi

if [ "$BUILD_DB" = "true" ]; then
    NEW_DB_VERSION=$(increment_version "$VERSION_LIQUIBASE_FILE" "1.0.21")
    log_success "SemVer de migration incrémenté avec succès : $NEW_DB_VERSION"

    TAG_VERSION="${NEW_DB_VERSION}"
    TAG_V_VERSION="v${NEW_DB_VERSION}"
    TAG_LATEST="latest"

    FULL_MIG_TAG_VERSION="${REGISTRY}/${IMAGE_MIGRATIONS_NAME}:${TAG_VERSION}"
    FULL_MIG_TAG_V_VERSION="${REGISTRY}/${IMAGE_MIGRATIONS_NAME}:${TAG_V_VERSION}"
    FULL_MIG_TAG_LATEST="${REGISTRY}/${IMAGE_MIGRATIONS_NAME}:${TAG_LATEST}"

    log_info "Construction de l'image de migration Liquibase (version: $NEW_DB_VERSION / $TAG_V_VERSION)..."
    if docker build \
        --platform linux/amd64 \
        -t "${FULL_MIG_TAG_VERSION}" \
        -t "${FULL_MIG_TAG_V_VERSION}" \
        -t "${FULL_MIG_TAG_LATEST}" \
        -f database/Dockerfile database; then
        log_success "Image de migration construite avec succès sous les tags $TAG_VERSION, $TAG_V_VERSION et $TAG_LATEST !"
    else
        log_error "Échec de la construction de l'image de migration."
        exit 1
    fi

    log_info "Poussée de l'image de migration Liquibase..."
    if docker push "${FULL_MIG_TAG_VERSION}" && docker push "${FULL_MIG_TAG_V_VERSION}" && docker push "${FULL_MIG_TAG_LATEST}"; then
        log_success "Image de migration poussée avec succès !"
        # Enregistrer la signature pour la détection de changements ultérieure
        echo "$CURRENT_DB_HASH" > "$DB_HASH_FILE"
    else
        log_error "Échec lors de la poussée de l'image de migration."
        exit 1
    fi
fi

echo -e "\n${GREEN}========================================================================${NC}"
echo -e "🚀 Déploiement du Plugin Prêt sur GCP !"
if [ "$BUILD_APP" = "true" ]; then
    echo -e "Image App Version  : ${FULL_TAG_V_VERSION}"
    echo -e "Image App SemVer   : ${FULL_TAG_VERSION}"
    echo -e "Image App Latest   : ${FULL_TAG_LATEST}"
else
    APP_VER=$(cat "$VERSION_FILE")
    echo -e "Image App (Skipped): ${REGISTRY}/${IMAGE_NAME}:v${APP_VER}"
fi
if [ "$BUILD_DB" = "true" ]; then
    echo -e "Image Mig Version  : ${FULL_MIG_TAG_V_VERSION}"
    echo -e "Image Mig SemVer   : ${FULL_MIG_TAG_VERSION}"
    echo -e "Image Mig Latest   : ${FULL_MIG_TAG_LATEST}"
else
    DB_VER=$(cat "$VERSION_LIQUIBASE_FILE")
    echo -e "Image Mig (Skipped): ${REGISTRY}/${IMAGE_MIGRATIONS_NAME}:v${DB_VER}"
fi
echo -e "${GREEN}========================================================================${NC}\n"
