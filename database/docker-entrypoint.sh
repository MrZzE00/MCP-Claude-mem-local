#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint script for Liquibase database migrations.
# Dynamically manages Google Cloud IAM Database Authentication for AlloyDB.
# ─────────────────────────────────────────────────────────────────────────────
set -e

# Configuration de base
export USE_IAM_AUTH=${USE_IAM_AUTH:-false}
export PG_HOST=${PG_HOST:-localhost}
export PG_PORT=${PG_PORT:-5432}
export PG_DATABASE=${PG_DATABASE:-claude_memory}

if [ "${USE_IAM_AUTH}" = "true" ] || [ "${USE_IAM_AUTH}" = "True" ]; then
  echo "🔒 [IAM AUTH] Configuration de l'authentification IAM Database pour AlloyDB..."
  
  # 1. Récupération de l'email du compte de service courant depuis le serveur de métadonnées
  SA_EMAIL=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email)
  if [ -n "${SA_EMAIL}" ] && [ "${SA_EMAIL}" != "Metadata-Flavor: Google required" ]; then
    # Formater le nom de l'utilisateur AlloyDB IAM (suppression du suffixe .gserviceaccount.com)
    DB_USER=$(echo "${SA_EMAIL}" | sed 's/\.gserviceaccount\.com//')
    echo "[IAM AUTH] Utilisateur base de données résolu : ${DB_USER}"
  else
    echo "❌ [IAM AUTH] ERREUR: Impossible de récupérer l'email du compte de service depuis le serveur de métadonnées."
    exit 1
  fi
  
  # 2. Récupération du jeton OAuth2 Access Token à runtime
  TOKEN_JSON=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token)
  DB_PASSWORD=$(echo "${TOKEN_JSON}" | grep -o '"access_token":"[^"]*' | grep -o '[^"]*$')
  
  if [ -z "${DB_PASSWORD}" ]; then
    echo "❌ [IAM AUTH] ERREUR: Impossible de récupérer l'access token OAuth2 depuis le serveur de métadonnées."
    exit 1
  fi
  
  echo "[IAM AUTH] Jeton d'accès résolu avec succès."
else
  echo "🔑 [CLASSIC] Utilisation de l'authentification classique (nom d'utilisateur & mot de passe)..."
  DB_USER=${PG_USER:-claude}
  DB_PASSWORD=${PG_PASSWORD}
fi

# Construction de l'URL JDBC PostgreSQL
URL="jdbc:postgresql://${PG_HOST}:${PG_PORT}/${PG_DATABASE}"

echo "🔍 [LIQUIBASE] Vérification de l'état de la base de données..."
liquibase \
  --url="${URL}" \
  --username="${DB_USER}" \
  --password="${DB_PASSWORD}" \
  --changeLogFile="changelog.yaml" \
  --log-level=INFO \
  status

echo "🚀 [LIQUIBASE] Application des migrations..."
liquibase \
  --url="${URL}" \
  --username="${DB_USER}" \
  --password="${DB_PASSWORD}" \
  --changeLogFile="changelog.yaml" \
  --log-level=INFO \
  update

echo "✅ [LIQUIBASE] Migrations terminées avec succès."
