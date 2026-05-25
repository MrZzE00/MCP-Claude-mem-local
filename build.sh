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

calculate_hash() {
    # Find all files in src, database, tests and specific core files, sort them, and compute their md5 hash.
    # We explicitly EXCLUDE terraform changes from triggering an application build (per user request).
    # We also exclude VERSION so that consecutive runs correctly skip the build.
    if command -v md5 &> /dev/null; then
        find src database tests Dockerfile requirements.txt web_ui.py build.sh \
            -type f \
            ! -path '*/__pycache__/*' \
            ! -name '*.pyc' \
            ! -name '.build_hash' \
            2>/dev/null | sort | xargs md5 | md5
    elif command -v md5sum &> /dev/null; then
        find src database tests Dockerfile requirements.txt web_ui.py build.sh \
            -type f \
            ! -path '*/__pycache__/*' \
            ! -name '*.pyc' \
            ! -name '.build_hash' \
            2>/dev/null | sort | xargs md5sum | md5sum | awk '{print $1}'
    else
        # Fallback using stat for file modifications
        find src database tests Dockerfile requirements.txt web_ui.py build.sh \
            -type f \
            ! -path '*/__pycache__/*' \
            ! -name '*.pyc' \
            ! -name '.build_hash' \
            2>/dev/null | sort | xargs stat -f "%m %N" 2>/dev/null | md5 2>/dev/null || stat -c "%Y %n" * 2>/dev/null
    fi
}

HASH_FILE=".build_hash"
CURRENT_HASH=$(calculate_hash)

log_info "Vérification des modifications dans le code source..."
if [ "$FORCE_BUILD" = "false" ] && [ -f "$HASH_FILE" ]; then
    PREVIOUS_HASH=$(cat "$HASH_FILE")
    if [ "$CURRENT_HASH" = "$PREVIOUS_HASH" ]; then
        log_success "Aucune modification détectée dans le code source depuis le dernier build. Build ignoré. (Utilisez --force pour forcer le build)"
        exit 0
    fi
fi

# --- 1. RUNNING UNIT TESTS (MUST PASS TO BUILD) ---
log_info "Démarrage de la phase de validation (Tests Unitaires)..."

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

# --- 2. SEMANTIC VERSIONING INCREMENT ---
log_info "Gestion du versioning sémantique (SemVer)..."

if [ -f "$VERSION_FILE" ]; then
    CURRENT_VERSION=$(cat "$VERSION_FILE" | tr -d '[:space:]')
else
    CURRENT_VERSION="1.0.0"
    log_warn "Fichier $VERSION_FILE introuvable. Initialisation à $CURRENT_VERSION"
fi

# Parse SemVer format (Major.Minor.Patch)
if [[ $CURRENT_VERSION =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    MAJOR="${BASH_REMATCH[1]}"
    MINOR="${BASH_REMATCH[2]}"
    PATCH="${BASH_REMATCH[3]}"
    # Increment patch version
    NEW_PATCH=$((PATCH + 1))
    NEW_VERSION="${MAJOR}.${MINOR}.${NEW_PATCH}"
else
    log_warn "Format de version invalide dans $VERSION_FILE ('$CURRENT_VERSION'). Réinitialisation à 1.0.1"
    NEW_VERSION="1.0.1"
fi

# Save the incremented version to the VERSION file in the project
echo "$NEW_VERSION" > "$VERSION_FILE"
log_success "SemVer patch incrémenté avec succès : $CURRENT_VERSION -> $NEW_VERSION"

# Setup full image tags
TAG_VERSION="${NEW_VERSION}"
TAG_V_VERSION="v${NEW_VERSION}"
TAG_LATEST="latest"

FULL_TAG_VERSION="${REGISTRY}/${IMAGE_NAME}:${TAG_VERSION}"
FULL_TAG_V_VERSION="${REGISTRY}/${IMAGE_NAME}:${TAG_V_VERSION}"
FULL_TAG_LATEST="${REGISTRY}/${IMAGE_NAME}:${TAG_LATEST}"

FULL_MIG_TAG_VERSION="${REGISTRY}/${IMAGE_MIGRATIONS_NAME}:${TAG_VERSION}"
FULL_MIG_TAG_V_VERSION="${REGISTRY}/${IMAGE_MIGRATIONS_NAME}:${TAG_V_VERSION}"
FULL_MIG_TAG_LATEST="${REGISTRY}/${IMAGE_MIGRATIONS_NAME}:${TAG_LATEST}"

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

# --- 4. DOCKER BUILD WITH MULTIPLE TAGS ---
# Build using buildkit for faster caching and build times
export DOCKER_BUILDKIT=1

log_info "Construction de l'image applicative principale (version: $NEW_VERSION / $TAG_V_VERSION)..."
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

log_info "Construction de l'image de migration Liquibase (version: $NEW_VERSION / $TAG_V_VERSION)..."
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

# --- 5. DOCKER PUSH ---
log_info "Poussée des images vers Artifact Registry..."

log_info "1. Poussée de l'image applicative principale..."
if docker push "${FULL_TAG_VERSION}" && docker push "${FULL_TAG_V_VERSION}" && docker push "${FULL_TAG_LATEST}"; then
    log_success "Image applicative poussée avec succès !"
else
    log_error "Échec lors de la poussée de l'image applicative."
    log_warn "Vérifiez que vous êtes connecté à GCP et configuré dans docker: gcloud auth configure-docker europe-west1-docker.pkg.dev"
    exit 1
fi

log_info "2. Poussée de l'image de migration Liquibase..."
if docker push "${FULL_MIG_TAG_VERSION}" && docker push "${FULL_MIG_TAG_V_VERSION}" && docker push "${FULL_MIG_TAG_LATEST}"; then
    log_success "Image de migration poussée avec succès !"
    # Enregistrer la signature pour la détection de changements ultérieure
    echo "$CURRENT_HASH" > "$HASH_FILE"
    echo -e "\n${GREEN}========================================================================${NC}"
    echo -e "🚀 Déploiement du Plugin Prêt sur GCP !"
    echo -e "Image App Version  : ${FULL_TAG_V_VERSION}"
    echo -e "Image App SemVer   : ${FULL_TAG_VERSION}"
    echo -e "Image App Latest   : ${FULL_TAG_LATEST}"
    echo -e "Image Mig Version  : ${FULL_MIG_TAG_V_VERSION}"
    echo -e "Image Mig SemVer   : ${FULL_MIG_TAG_VERSION}"
    echo -e "Image Mig Latest   : ${FULL_MIG_TAG_LATEST}"
    echo -e "${GREEN}========================================================================${NC}\n"
else
    log_error "Échec lors de la poussée de l'image de migration."
    exit 1
fi
