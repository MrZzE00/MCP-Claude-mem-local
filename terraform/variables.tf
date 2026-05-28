# ============================================================
# Variables injectées automatiquement par manage_env.py
# (platform-engineering/manage_env.py — ne pas modifier les
#  valeurs par défaut ici, elles sont surchargées au deploy)
# Dummy change to test TF change-detection bypass
# ============================================================

variable "project_id" {
  type        = string
  description = "GCP Project ID où le service est déployé"
}

variable "region" {
  type        = string
  default     = "europe-west1"
  description = "Région GCP cible (ex: europe-west1)"
}

variable "service_name" {
  type        = string
  description = "Nom kebab-case du service (ex: mcp-claude-memory)"
}

variable "image_version" {
  type        = string
  default     = "latest"
  description = "Version semver de l'image Docker (ex: v1.0.6) — injectée par manage_env.py"
}

variable "image_db_migrations_version" {
  type        = string
  default     = "latest"
  description = "Version semver de l'image Docker de migration (ex: v1.0.6) — injectée par manage_env.py"
}

# image_uri = base URL de l'image Docker SANS le tag de version.
# La plateforme injecte uniquement image_version ; le sous-projet connaît son propre registry.
variable "image_uri" {
  type        = string
  default     = "europe-west1-docker.pkg.dev/slavayssiere-sandbox-462015/z-gcp-summit-services-dev/mcp-claude-memory"
  description = "URL de base de l'image Docker sans le tag (ex: registry/name). Suffixé par :image_version au deploy."
}

variable "lb_path" {
  type        = string
  description = "Préfixe de routage Load Balancer (ex: /mcp-claude-memory)"
}

variable "vpc_network_id" {
  type        = string
  description = "ID complet du VPC principal de la plateforme"
}

variable "vpc_subnet_id" {
  type        = string
  description = "ID complet du sous-réseau principal de la plateforme"
}

variable "alloydb_instance_uri" {
  type        = string
  description = "URI complet de l'instance AlloyDB primaire (requis pour l'auth IAM)"
}

variable "alloydb_ip" {
  type        = string
  description = "Adresse IP privée de l'instance AlloyDB (pour DATABASE_URL)"
}

variable "alloydb_database" {
  type        = string
  default     = "mcp_claude_memory"
  description = "Nom de la base PostgreSQL dédiée à ce service"
}

# SA créé par la plateforme (cr_extra_projects.tf).
# user IAM AlloyDB = replace(service_account_email, ".gserviceaccount.com", "")
variable "service_account_email" {
  type        = string
  description = "Email du Service Account créé par la plateforme pour ce service"
}

# Nom du secret Secret Manager contenant l'IAP OAuth Client ID.
# Convention : iap-oauth-client-id-{env}
variable "iap_oauth_client_id" {
  type        = string
  default     = ""
  description = "Nom du secret Secret Manager pour l'IAP OAuth Client ID (ex: iap-oauth-client-id-dev)"
}

# Nom du secret Secret Manager contenant l'IAP OAuth Client Secret.
# Convention : iap-oauth-client-secret-{env}
variable "iap_oauth_client_secret" {
  type        = string
  default     = ""
  description = "Nom du secret Secret Manager pour l'IAP OAuth Client Secret (ex: iap-oauth-client-secret-dev)"
}

variable "iap_oauth_client_version" {
  type        = string
  default     = "latest"
  description = "Version de secret active pour l'IAP OAuth Client ID/Secret (ex: 2) — injectée par manage_env.py"
}

# ============================================================
# Variables spécifiques à ce projet (non injectées par la plateforme)
# ============================================================

variable "image_db_migrations" {
  type        = string
  default     = ""
  description = "URL base de l'image Docker Liquibase (sans tag). Défaut : même registry que le service, suffixe -db-migrations"
}


variable "enable_iap" {
  type        = bool
  default     = true
  description = "Active Identity-Aware Proxy sur le Backend Service"
}

variable "use_iam_auth" {
  type        = bool
  default     = true
  description = "Utilise l'authentification IAM pour AlloyDB (recommandé)"
}
