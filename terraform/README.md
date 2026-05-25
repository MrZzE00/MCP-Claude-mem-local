# Infrastructure as Code (Terraform) - MCP Memory Plugin

Ce répertoire contient la configuration Terraform nécessaire pour déployer le plugin de mémoire sémantique sur Google Cloud Run en mode **strictement sans mot de passe via l'authentification IAM Database Authentication**.

> [!WARNING]
> **POLITIQUE DE SÉCURITÉ POUR LES AGENTS IA :**
> L'agent IA **n'a en aucun cas le droit de lancer les commandes de déploiement Terraform** (`terraform apply` ou `terraform destroy`). L'agent doit se limiter à la modification des fichiers `.tf`, à l'initialisation (`terraform init`) et à la validation de la syntaxe (`terraform validate`). L'application réelle de l'infrastructure est exclusivement réservée à l'utilisateur humain.

---

## 1. Description des Ressources Provisionnées

La configuration déploie une brique applicative ("plugin") isolée qui s'intègre avec votre projet parent GCP :
1. **Compte de Service Applicatif (`google_service_account`)** : Compte de service dédié disposant des privilèges minimaux requis.
2. **Permissions IAM** :
   - `roles/aiplatform.user` : Pour appeler l'API Vertex AI pour les embeddings (`text-embedding-004`).
   - `roles/secretmanager.secretAccessor` : Pour lire la clé d'API sécurisée (`API_KEY`).
   - `roles/alloydb.client` et `roles/alloydb.databaseUser` : Pour se connecter et s'authentifier de manière sécurisée sans mot de passe auprès d'AlloyDB.
3. **Cloud Run Service (v2)** : Le conteneur exécutant FastAPI & FastMCP configuré pour utiliser la connexion IAM.
4. **Serverless NEG & Backend Service** : Permet de connecter proprement ce plugin au Load Balancer HTTPS de votre projet parent, avec support de l'**Identity-Aware Proxy (IAP)**.

---

## 2. Variables d'Entrées (`variables.tf`)

| Variable | Type | Description | Défaut |
|----------|------|-------------|---------|
| `project_id` | `string` | L'identifiant du projet GCP de déploiement | *(Requis)* |
| `region` | `string` | La région GCP pour Cloud Run | `"europe-west9"` |
| `service_name` | `string` | Le nom du service Cloud Run | `"mcp-memory-service"` |
| `image_uri` | `string` | URI de base de l'image (sans tag de version) | `"europe-west1-docker.pkg.dev/.../mcp-memory-service"` |
| `image_version` | `string` | Tag de version de l'image Docker | `"latest"` |
| `vpc_network_id` | `string` | ID qualifié de votre réseau VPC existant | *(Requis)* |
| `vpc_subnet_id` | `string` | ID qualifié de votre sous-réseau VPC | *(Requis)* |
| `alloydb_ip` | `string` | IP privée de l'instance primaire AlloyDB | *(Requis)* |
| `alloydb_user` | `string` | Nom de l'utilisateur base de données IAM | `"claude"` |
| `alloydb_database` | `string` | Nom de la base de données AlloyDB | `"claude_memory"` |
| `alloydb_instance_uri` | `string` | URI complète de la ressource instance primaire AlloyDB | *(Requis)* |
| `use_iam_auth` | `bool` | Détermine si la connexion s'effectue via IAM | `true` |
| `secret_manager_api_key_id` | `string` | ID du secret stockant la clé d'API | *(Requis)* |
| `enable_iap` | `bool` | Activer IAP sur le Backend Service | `true` |
| `iap_oauth_client_id` | `string` | Client ID OAuth2 pour IAP | `""` |
| `iap_oauth_client_secret` | `string` | Client Secret OAuth2 pour IAP | `""` |

---

## 3. Guide de Déploiement Humain

1. **Initialiser Terraform** :
   ```bash
   terraform init
   ```
2. **Valider la Syntaxe** :
   ```bash
   terraform validate
   ```
3. **Appliquer les Modifications** (Réservé à l'humain) :
   ```bash
   terraform apply
   ```
