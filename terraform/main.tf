# ============================================================
# NOTE : le bloc `terraform { backend "gcs" { ... } }` est
# AUTO-GÉNÉRÉ par manage_env.py dans backend.tf à chaque deploy.
# Ne pas ajouter de backend ici.
# ============================================================

terraform {
  required_version = ">= 1.9.0, < 2.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">= 6.0.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# ─── Locals ──────────────────────────────────────────────────────────────────
locals {
  # Le user IAM AlloyDB est l'email du SA sans le suffixe .gserviceaccount.com
  alloydb_iam_user = replace(var.service_account_email, ".gserviceaccount.com", "")

  # Extrait dynamiquement le nom de l'environnement (prd, dev, etc.) à partir de la variable service_account_email.
  # Format du SA : sa-<service_name>-<env>@<project>.iam.gserviceaccount.com
  # Comme le workspace Terraform du projet externe reste à "default", nous extrayons le vrai env ici.
  sa_name  = split("@", var.service_account_email)[0]
  env_name = replace(local.sa_name, "sa-${var.service_name}-", "")

  # Image des migrations : si non fournie, dérive du registry de l'image principale
  # ex: europe-west1-docker.pkg.dev/proj/reg/mcp-claude-memory:v1.0.6
  #  → europe-west1-docker.pkg.dev/proj/reg/mcp-claude-memory-db-migrations:v1.0.6
  image_db_migrations_resolved = var.image_db_migrations != "" ? (
    "${var.image_db_migrations}:${var.image_db_migrations_version}"
  ) : (
    "${var.image_uri}-db-migrations:${var.image_db_migrations_version}"
  )
}

# ─── IAM spécifique au projet (roles non couverts par la plateforme) ─────────

# Vertex AI pour les embeddings (text-embedding-004)
resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${var.service_account_email}"
}


# Accès aux secrets IAP OAuth (si IAP activé)
resource "google_secret_manager_secret_iam_member" "iap_client_id_accessor" {
  count     = var.enable_iap && var.iap_oauth_client_id != "" ? 1 : 0
  project   = var.project_id
  secret_id = var.iap_oauth_client_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.service_account_email}"
}

resource "google_secret_manager_secret_iam_member" "iap_client_secret_accessor" {
  count     = var.enable_iap && var.iap_oauth_client_secret != "" ? 1 : 0
  project   = var.project_id
  secret_id = var.iap_oauth_client_secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.service_account_email}"
}

# ─── Lecture des secrets IAP depuis Secret Manager ───────────────────────────

data "google_secret_manager_secret_version" "iap_client_id" {
  count   = var.enable_iap && var.iap_oauth_client_id != "" ? 1 : 0
  secret  = var.iap_oauth_client_id
  version = var.iap_oauth_client_version
  project = var.project_id
}

data "google_secret_manager_secret_version" "iap_client_secret" {
  count   = var.enable_iap && var.iap_oauth_client_secret != "" ? 1 : 0
  secret  = var.iap_oauth_client_secret
  version = var.iap_oauth_client_version
  project = var.project_id
}

# Autorise le Service Account à lire le secret du mot de passe admin AlloyDB de son environnement
resource "google_secret_manager_secret_iam_member" "alloydb_password_access" {
  project   = var.project_id
  secret_id = "alloydb-password-${local.env_name}"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.service_account_email}"
}

# ─── Job Cloud Run : Migrations Liquibase ────────────────────────────────────

resource "google_cloud_run_v2_job" "db_migrations" {
  name                = "${var.service_name}-migrations"
  location            = var.region
  project             = var.project_id
  deletion_protection = false

  template {
    template {
      service_account = var.service_account_email

      vpc_access {
        network_interfaces {
          network    = var.vpc_network_id
          subnetwork = var.vpc_subnet_id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image = local.image_db_migrations_resolved

        env {
          name  = "USE_IAM_AUTH"
          value = "false"
        }
        env {
          name  = "PG_HOST"
          value = var.alloydb_ip
        }
        env {
          name  = "PG_PORT"
          value = "5432"
        }
        env {
          name  = "PG_DATABASE"
          value = var.alloydb_database
        }
        env {
          name  = "PG_USER"
          value = "postgres"
        }
        env {
          name = "PG_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = "alloydb-password-${local.env_name}"
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [
    google_project_iam_member.vertex_ai_user,
    google_secret_manager_secret_iam_member.alloydb_password_access,
  ]
}

# Exécute le job de migrations lors du terraform apply
resource "null_resource" "run_db_migrations_job" {
  triggers = {
    image = local.image_db_migrations_resolved
  }

  provisioner "local-exec" {
    command = "gcloud run jobs execute ${google_cloud_run_v2_job.db_migrations.name} --region ${var.region} --project ${var.project_id} --wait"
  }

  depends_on = [google_cloud_run_v2_job.db_migrations]
}

# ─── Service Cloud Run V2 ────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "mcp_service" {
  name                = var.service_name
  location            = var.region
  project             = var.project_id
  deletion_protection = false

  ingress = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = var.service_account_email

    containers {
      # image_uri:image_version — le registry est défini par défaut dans variables.tf
      image = "${var.image_uri}:${var.image_version}"

      ports {
        container_port = 8080
      }

      startup_probe {
        initial_delay_seconds = 10
        timeout_seconds       = 3
        period_seconds        = 5
        failure_threshold     = 24
        http_get {
          path = "/health"
          port = 8080
        }
      }

      liveness_probe {
        initial_delay_seconds = 15
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 3
        http_get {
          path = "/ready"
          port = 8080
        }
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
        startup_cpu_boost = true
      }

      env {
        name  = "PG_HOST"
        value = var.alloydb_ip
      }
      env {
        name  = "PG_PORT"
        value = "5432"
      }
      env {
        name  = "PG_USER"
        value = local.alloydb_iam_user
      }
      env {
        name  = "PG_DATABASE"
        value = var.alloydb_database
      }
      env {
        name  = "EMBEDDING_PROVIDER"
        value = "vertexai"
      }
      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "USE_IAM_AUTH"
        value = var.use_iam_auth ? "true" : "false"
      }
      env {
        name  = "ALLOYDB_INSTANCE_URI"
        value = var.alloydb_instance_uri
      }

      env {
        name  = "REQUIRE_AUTH"
        value = "false"
      }
    }

    vpc_access {
      network_interfaces {
        network    = var.vpc_network_id
        subnetwork = var.vpc_subnet_id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }
  }

  depends_on = [
    google_project_iam_member.vertex_ai_user,
    null_resource.run_db_migrations_job,
  ]
}

# ─── IAM Invoker : Autorisation d'invocation depuis le LB ou en interne ──────

resource "google_cloud_run_v2_service_iam_member" "mcp_service_invoker" {
  project  = google_cloud_run_v2_service.mcp_service.project
  location = google_cloud_run_v2_service.mcp_service.location
  name     = google_cloud_run_v2_service.mcp_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Récupère les métadonnées du projet courant (dont le Project Number pour l'IAP)
data "google_project" "project" {}

# Provisionne et récupère l'identité (Service Agent) d'IAP pour le projet
resource "google_project_service_identity" "iap_sa" {
  provider = google-beta
  project  = var.project_id
  service  = "iap.googleapis.com"
}

# Autorise le Service Agent IAP à invoquer le service Cloud Run (Requis pour l'intégration IAP + Cloud Run)
resource "google_cloud_run_v2_service_iam_member" "iap_service_invoker" {
  project  = google_cloud_run_v2_service.mcp_service.project
  location = google_cloud_run_v2_service.mcp_service.location
  name     = google_cloud_run_v2_service.mcp_service.name
  role     = "roles/run.invoker"
  member   = google_project_service_identity.iap_sa.member
}


# ─── NEG Serverless ──────────────────────────────────────────────────────────

resource "google_compute_region_network_endpoint_group" "serverless_neg" {
  name                  = "${var.service_name}-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  project               = var.project_id

  cloud_run {
    service = google_cloud_run_v2_service.mcp_service.name
  }
}

# ─── Backend Service (avec IAP conditionnel) ──────────────────────────────────

resource "google_compute_backend_service" "mcp_backend" {
  name                  = "${var.service_name}-backend"
  protocol              = "HTTP"
  port_name             = "http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  project               = var.project_id

  backend {
    group = google_compute_region_network_endpoint_group.serverless_neg.id
  }

  dynamic "iap" {
    for_each = (
      var.enable_iap
      && var.iap_oauth_client_id != ""
      && length(data.google_secret_manager_secret_version.iap_client_id) > 0
    ) ? [1] : []
    content {
      enabled              = true
      oauth2_client_id     = data.google_secret_manager_secret_version.iap_client_id[0].secret_data
      oauth2_client_secret = data.google_secret_manager_secret_version.iap_client_secret[0].secret_data
    }
  }

  enable_cdn = false
}

# Autorise le Service Account dédié à franchir l'IAP pour les sanity checks automatiques
resource "google_iap_web_backend_service_iam_member" "mcp_iap_sa_accessor" {
  count               = var.enable_iap && var.iap_oauth_client_id != "" ? 1 : 0
  project             = var.project_id
  web_backend_service = google_compute_backend_service.mcp_backend.name
  role                = "roles/iap.httpsResourceAccessor"
  member              = "serviceAccount:${var.service_account_email}"
}
