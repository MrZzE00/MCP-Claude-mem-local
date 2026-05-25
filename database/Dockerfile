# ─────────────────────────────────────────────────────────────────────────────
# DB Migrations — Cloud Run Job Image
# Exécute les migrations de schéma de base de données AlloyDB avec Liquibase.
# ─────────────────────────────────────────────────────────────────────────────

FROM liquibase/liquibase:4.29.0

# Passer sous root pour installer curl (nécessaire pour requêter le Metadata Server GCP)
USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copier les fichiers de configuration de la base de données
COPY changelog.yaml /liquibase/changelog.yaml
COPY db-init.sql /liquibase/db-init.sql
COPY docker-entrypoint.sh /liquibase/docker-entrypoint.sh

# Donner les droits d'exécution et ré-attribuer les dossiers à l'utilisateur liquibase
RUN chmod +x /liquibase/docker-entrypoint.sh && \
    chown -R liquibase:liquibase /liquibase

# Repasser sous l'utilisateur non-root par défaut de l'image
USER liquibase

# Script de démarrage qui gère l'authentification IAM AlloyDB
ENTRYPOINT ["/liquibase/docker-entrypoint.sh"]
