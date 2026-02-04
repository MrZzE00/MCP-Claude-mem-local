# 🧠 MCP-Claude-mem-local — Documentation Technique

## Table des matières

1. [Architecture](#1-architecture)
2. [Prérequis](#2-prérequis)
3. [Installation](#3-installation)
4. [Configuration](#4-configuration)
5. [Schéma de données](#5-schéma-de-données)
6. [API MCP Server](#6-api-mcp-server)
7. [Plugin & Hooks](#7-plugin--hooks)
8. [Interface Web](#8-interface-web)
9. [Embeddings](#9-embeddings)
10. [Migration depuis claude-mem](#10-migration-depuis-claude-mem)
11. [Maintenance & Opérations](#11-maintenance--opérations)
12. [Dépannage](#12-dépannage)
13. [Sécurité](#13-sécurité)
14. [Contribution](#14-contribution)

---

## 1. Architecture

### 1.1 Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Claude Code                                │
│                               │                                      │
│                         MCP Protocol                                 │
│                               │                                      │
│                    ┌──────────▼──────────┐                          │
│                    │   MCP-Claude-mem-local Server   │                          │
│                    │      (Python)       │                          │
│                    │                     │                          │
│                    │  ┌───────────────┐  │                          │
│                    │  │   5 Tools     │  │                          │
│                    │  │ store_memory  │  │                          │
│                    │  │ retrieve      │  │                          │
│                    │  │ list          │  │                          │
│                    │  │ delete        │  │                          │
│                    │  │ stats         │  │                          │
│                    │  └───────────────┘  │                          │
│                    └──────────┬──────────┘                          │
│                               │                                      │
│              ┌────────────────┼────────────────┐                    │
│              │                │                │                    │
│              ▼                ▼                ▼                    │
│    ┌─────────────────┐ ┌───────────┐ ┌─────────────────┐           │
│    │   PostgreSQL    │ │  Ollama   │ │  Context Hook   │           │
│    │   + pgvector    │ │  (embed)  │ │   (inject)      │           │
│    └────────┬────────┘ └───────────┘ └────────┬────────┘           │
│             │                                  │                    │
│             ▼                                  ▼                    │
│    ┌─────────────────┐                ┌─────────────────┐          │
│    │    memories     │                │   CLAUDE.md     │          │
│    │  user_prompts   │                │   (per project) │          │
│    └─────────────────┘                └─────────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Composants

| Composant | Technologie | Port | Description |
|-----------|-------------|------|-------------|
| **MCP Server** | Python + FastMCP | stdio | Interface avec Claude Code |
| **PostgreSQL** | pgvector/pgvector:pg16 | 5432 | Stockage vectoriel |
| **Ollama** | ollama/ollama | 11434 | Génération d'embeddings |
| **Web UI** | HTML/CSS/JS statique | 8080 | Dashboard de visualisation |
| **Context Hook** | Python script | - | Injection dans CLAUDE.md |

### 1.3 Flux de données

#### Stockage d'une mémoire
```
User Input → Claude Code → MCP store_memory
                              │
                              ▼
                    ┌─────────────────┐
                    │ Ollama API      │
                    │ POST /api/embed │
                    └────────┬────────┘
                             │
                             ▼ embedding[768]
                    ┌─────────────────┐
                    │ PostgreSQL      │
                    │ INSERT memories │
                    └─────────────────┘
```

#### Recherche de mémoires
```
Query → Claude Code → MCP retrieve_memories
                              │
                              ▼
                    ┌─────────────────┐
                    │ Ollama API      │
                    │ embed(query)    │
                    └────────┬────────┘
                             │
                             ▼ query_embedding[768]
                    ┌─────────────────────────────┐
                    │ PostgreSQL                  │
                    │ SELECT ... ORDER BY         │
                    │ embedding <=> query::vector │
                    │ (cosine similarity)         │
                    └─────────────────────────────┘
```

---

## 2. Prérequis

### 2.1 Système

| Requis | Version minimum | Recommandé |
|--------|-----------------|------------|
| **OS** | macOS 12+, Ubuntu 20.04+, Windows 11 | macOS 14+ (Apple Silicon) |
| **RAM** | 8 GB | 16 GB |
| **Disque** | 5 GB | 20 GB |
| **CPU** | 4 cores | 8 cores |

### 2.2 Logiciels

| Logiciel | Version | Installation |
|----------|---------|--------------|
| **Python** | 3.11+ | `brew install python@3.13` |
| **PostgreSQL** | 16+ | `brew install postgresql@17` |
| **pgvector** | 0.7+ | `brew install pgvector` |
| **Ollama** | 0.15+ | https://ollama.com/download |
| **Claude Code** | Latest | Anthropic |

### 2.3 Vérification

```bash
# Python
python3 --version
# Python 3.13.x

# PostgreSQL
pg_isready
# localhost:5432 - accepting connections

# Ollama
ollama --version
# ollama version 0.15.x
```

---

## 3. Installation

### 3.1 Installation rapide (recommandée)

```bash
# Clone le repository
git clone https://github.com/your-org/mcp-claude-mem-local.git
cd mcp-claude-mem-local

# Lancer l'installation
./install.sh
```

### 3.2 Installation manuelle

#### Étape 1 : Créer la structure

```bash
mkdir -p ~/mcp-claude-mem-local/{src,plugin/{hooks,scripts},data}
cd ~/mcp-claude-mem-local
```

#### Étape 2 : Environnement Python

```bash
python3 -m venv venv
source venv/bin/activate
pip install mcp asyncpg httpx python-dotenv
```

#### Étape 3 : PostgreSQL + pgvector

**macOS (Homebrew) :**

```bash
# Installer PostgreSQL 17 avec pgvector
brew install postgresql@17 pgvector

# Démarrer PostgreSQL (auto-start au boot)
brew services start postgresql@17

# Créer l'utilisateur et la base
createuser -s claude
psql -c "ALTER USER claude PASSWORD 'YOUR_SECURE_PASSWORD';"    # Generate with: openssl rand -base64 32
createdb -O claude claude_memory

# Activer pgvector
psql -d claude_memory -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

**Linux (apt) :**

```bash
# Installer PostgreSQL
sudo apt install postgresql-16 postgresql-16-pgvector

# Démarrer PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Créer l'utilisateur et la base
sudo -u postgres createuser -s claude
sudo -u postgres psql -c "ALTER USER claude PASSWORD 'YOUR_SECURE_PASSWORD';"
sudo -u postgres createdb -O claude claude_memory

# Activer pgvector
sudo -u postgres psql -d claude_memory -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

#### Étape 4 : Initialiser le schéma

```bash
# Utiliser le script d'initialisation
psql -U claude -d claude_memory -f ~/mcp-claude-mem-local/scripts/init.sql
```

Le script `scripts/init.sql` crée :
- Table `memories` avec colonnes embedding vector(768)
- Table `user_prompts` pour l'historique des prompts
- Index HNSW pour la recherche vectorielle
- Vues statistiques

#### Étape 5 : Ollama + Modèle d'embeddings

```bash
# Installer Ollama (macOS)
curl -fsSL https://ollama.com/install.sh | sh

# Télécharger le modèle d'embeddings
ollama pull nomic-embed-text
```

#### Étape 6 : Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example ~/mcp-claude-mem-local/.env
# Edit .env with your secure password
```

Or create manually:

```bash
cat > ~/mcp-claude-mem-local/.env << 'EOF'
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=mcp-claude-mem-local
PG_USER=mcp-claude-mem-local
PG_PASSWORD=YOUR_SECURE_PASSWORD    # Generate with: openssl rand -base64 32
OLLAMA_HOST=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768

# Security (optional)
API_KEY=                            # Enable API key authentication
RATE_LIMIT_REQUESTS=60
ALLOWED_ORIGINS=localhost:8080
EOF
```

> ⚠️ **Security**: Never commit `.env` with real credentials.

#### Étape 7 : Configurer Claude Code

```bash
# Ajouter au fichier ~/.claude.json
# Dans la section "mcpServers":
{
  "mcp-claude-mem-local": {
    "type": "stdio",
    "command": "/chemin/vers/mcp-claude-mem-local/venv/bin/python",
    "args": ["/chemin/vers/mcp-claude-mem-local/src/server.py"]
  }
}
```

---

## 4. Configuration

### 4.1 Variables d'environnement

See `.env.example` for all available options.

| Variable | Défaut | Description |
|----------|--------|-------------|
| `PG_HOST` | `localhost` | Hôte PostgreSQL |
| `PG_PORT` | `5432` | Port PostgreSQL |
| `PG_DATABASE` | `claude_memory` | Nom de la base |
| `PG_USER` | `claude` | Utilisateur PostgreSQL |
| `PG_PASSWORD` | - | Mot de passe (requis) |
| `OLLAMA_HOST` | `http://localhost:11434` | URL Ollama |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Modèle d'embeddings |
| `EMBEDDING_DIMENSIONS` | `768` | Dimensions du vecteur |
| `API_KEY` | - | Clé API pour authentification (optionnel) |
| `API_HOST` | `127.0.0.1` | Adresse de bind du serveur |
| `API_PORT` | `8080` | Port du serveur |
| `ALLOWED_ORIGINS` | `localhost:8080` | Origines CORS autorisées |
| `RATE_LIMIT_REQUESTS` | `60` | Requêtes par minute |
| `RATE_LIMIT_WINDOW` | `60` | Fenêtre de rate limiting (secondes) |
| `DISABLE_DOCS` | - | Désactiver l'endpoint /docs |

### 4.2 Configuration MCP (~/.claude.json)

```json
{
  "mcpServers": {
    "mcp-claude-mem-local": {
      "type": "stdio",
      "command": "${HOME}/mcp-claude-mem-local/venv/bin/python",
      "args": ["${HOME}/mcp-claude-mem-local/src/server.py"],
      "env": {
        "PG_HOST": "localhost",
        "PG_PORT": "5432"
      }
    }
  }
}
```

### 4.3 Configuration Plugin (~/.claude/settings.json)

```json
{
  "enabledPlugins": {
    "mcp-claude-mem-local@local": true
  }
}
```

---

## 5. Schéma de données

### 5.1 Table `memories`

```sql
CREATE TABLE memories (
    -- Identifiant unique
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Contenu
    content TEXT NOT NULL,           -- Contenu complet de la mémoire
    summary TEXT,                    -- Résumé court (auto-généré si absent)
    
    -- Classification
    category VARCHAR(50) NOT NULL,   -- bugfix, decision, feature, discovery, refactor, change
    tags TEXT[],                     -- Tags libres
    project_context VARCHAR(255),    -- Nom/chemin du projet
    
    -- Vecteur pour recherche sémantique
    embedding vector(768),           -- nomic-embed-text = 768 dimensions
    
    -- Métadonnées temporelles
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_accessed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Statistiques d'usage
    access_count INTEGER DEFAULT 0,
    importance_score FLOAT DEFAULT 0.5  -- 0.0 à 1.0
);
```

### 5.2 Table `user_prompts`

```sql
CREATE TABLE user_prompts (
    id SERIAL PRIMARY KEY,
    session_id TEXT,                 -- ID de session Claude
    prompt_number INTEGER,           -- Numéro du prompt dans la session
    prompt_text TEXT NOT NULL,       -- Texte du prompt
    embedding vector(768),           -- Vecteur pour recherche
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 5.3 Index

```sql
-- Recherche vectorielle (HNSW = Hierarchical Navigable Small World)
CREATE INDEX idx_memories_embedding 
    ON memories USING hnsw (embedding vector_cosine_ops);

CREATE INDEX idx_prompts_embedding 
    ON user_prompts USING hnsw (embedding vector_cosine_ops);

-- Recherche par catégorie/projet
CREATE INDEX idx_memories_category ON memories(category);
CREATE INDEX idx_memories_project ON memories(project_context);
CREATE INDEX idx_memories_created ON memories(created_at DESC);
```

### 5.4 Catégories

| Catégorie | Code | Icône | Usage |
|-----------|------|-------|-------|
| Bug Fix | `bugfix` | 🔴 | Correction de bug avec cause et solution |
| Decision | `decision` | 🟠 | Décision architecturale avec contexte |
| Feature | `feature` | 🟢 | Nouvelle fonctionnalité implémentée |
| Discovery | `discovery` | 🔵 | Apprentissage, découverte technique |
| Refactor | `refactor` | 🟣 | Refactoring avec motivation |
| Change | `change` | ⚪ | Modification générale |
| Pattern | `pattern` | 🟤 | Pattern réutilisable identifié |
| Preference | `preference` | 🟡 | Préférence utilisateur |
| Learning | `learning` | 📘 | Enseignement, leçon apprise |
| Error Solution | `error_solution` | 🩹 | Solution à une erreur spécifique |

---

## 6. API MCP Server

### 6.1 Vue d'ensemble

Le serveur expose 5 outils via le protocole MCP (Model Context Protocol).

### 6.2 `store_memory`

Stocke une nouvelle mémoire avec génération automatique d'embedding.

**Signature :**
```python
async def store_memory(
    content: str,           # Contenu complet (requis)
    category: str,          # Catégorie (requis)
    summary: str = None,    # Résumé (auto-généré si absent)
    tags: list[str] = None, # Tags optionnels
    importance: float = 0.5,# Score 0.0-1.0
    project: str = None     # Contexte projet
) -> str
```

**Exemple d'utilisation :**
```
store_memory({
  content: "Le bug venait d'une race condition dans le refresh token. 
            La solution: ajouter un mutex sur l'appel API.",
  category: "bugfix",
  summary: "Race condition refresh token",
  tags: ["auth", "async", "token"],
  importance: 0.9,
  project: "my-app"
})
```

**Retour :**
```
Mémoire stockée avec ID: 4c8c96cc-cc11-4df5-85c4-8bd545ded940
```

### 6.3 `retrieve_memories`

Recherche sémantique dans les mémoires.

**Signature :**
```python
async def retrieve_memories(
    query: str,              # Requête de recherche (requis)
    max_results: int = 5,    # Nombre max de résultats
    category: str = None,    # Filtre par catégorie
    min_similarity: float = 0.5  # Similarité minimum (0.0-1.0)
) -> str
```

**Exemple :**
```
retrieve_memories({
  query: "problème d'authentification token",
  max_results: 3,
  category: "bugfix"
})
```

**Retour :**
```markdown
## 3 mémoire(s) trouvée(s):

---
**[bugfix]** (similarité: 0.87, importance: 0.9)
# Race condition refresh token
Le bug venait d'une race condition...
Tags: auth, async, token

---
**[bugfix]** (similarité: 0.72, importance: 0.7)
...
```

### 6.4 `list_memories`

Liste les mémoires récentes.

**Signature :**
```python
async def list_memories(
    limit: int = 20,         # Nombre max
    category: str = None     # Filtre optionnel
) -> str
```

**Exemple :**
```
list_memories({ limit: 10, category: "decision" })
```

### 6.5 `memory_stats`

Retourne les statistiques de la base.

**Signature :**
```python
async def memory_stats() -> str
```

**Retour :**
```markdown
## Statistiques Mémoire

**Total**: 1357 mémoires
**Cette semaine**: 45 nouvelles

### Par catégorie:
- bugfix: 234
- decision: 89
- feature: 456
- discovery: 312
- refactor: 78
- change: 188

### Plus consultées:
- (12x) Race condition refresh token...
- (8x) Architecture microservices...
```

### 6.6 `delete_memory`

Supprime une mémoire par son ID.

**Signature :**
```python
async def delete_memory(memory_id: str) -> str
```

---

## 7. Plugin & Hooks

### 7.1 Structure du plugin

```
plugin/
├── hooks/
│   └── hooks.json         # Configuration des hooks
└── scripts/
    ├── context-hook.py    # Script d'injection CLAUDE.md
    └── capture-prompt.py  # Capture automatique des prompts
```

### 7.2 UserPromptSubmit — Capture automatique des prompts

Le hook `UserPromptSubmit` capture automatiquement chaque prompt utilisateur pour la recherche sémantique.

#### Fonctionnement

1. **Déclenchement** : À chaque prompt soumis par l'utilisateur
2. **Entrée** : JSON via stdin avec `session_id`, `prompt`, `cwd`
3. **Traitement** : Extraction projet, génération embedding, stockage
4. **Sortie** : Exit 0 (ne bloque jamais Claude)

#### Configuration

Dans `~/.claude/settings.json` :

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "type": "command",
        "command": "~/claude-memory-local/venv/bin/python3 ~/claude-memory-local/plugins/scripts/capture-prompt.py",
        "timeout": 10,
        "failOnError": false
      }
    ]
  }
}
```

#### Script capture-prompt.py

| Fonctionnalité | Description |
|----------------|-------------|
| **Extraction projet** | Depuis CLAUDE.md ou nom de dossier |
| **Validation** | Ignore prompts vides ou < 3 caractères |
| **Embedding** | Via Ollama (timeout 5s, fallback sans embedding) |
| **Stockage** | Table `user_prompts` avec numéro de séquence |

#### Flux de données

```
User prompt → Claude Code → UserPromptSubmit hook
                              │
                              ▼ JSON stdin
                    ┌─────────────────┐
                    │capture-prompt.py│
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼                             ▼
       ┌───────────┐               ┌─────────────┐
       │  Ollama   │               │ PostgreSQL  │
       │ embedding │               │user_prompts │
       └───────────┘               └─────────────┘
```

> 📖 Documentation complète : [docs/hooks-prompts-capture.md](./hooks-prompts-capture.md)

### 7.4 hooks.json (autres hooks)

```json
{
  "description": "MCP-Claude-mem-local hooks - Mémoire persistante locale",
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${HOME}/mcp-claude-mem-local/plugin/scripts/context-hook.py\" session-start",
            "timeout": 30
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${HOME}/mcp-claude-mem-local/plugin/scripts/context-hook.py\" post-tool",
            "timeout": 30
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${HOME}/mcp-claude-mem-local/plugin/scripts/context-hook.py\" stop",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

### 7.5 Context Hook

Le script `context-hook.py` :

1. Récupère les mémoires associées au projet courant
2. Génère un bloc markdown formaté
3. Injecte/met à jour le bloc dans `CLAUDE.md`

**Format du bloc injecté :**
```markdown
<mcp-claude-mem-local-context>
# Recent Activity

<!-- Auto-generated by MCP-Claude-mem-local. Edit content outside the tags. -->

### Jan 28, 2026

| ID | Time | T | Title | Read |
|----|------|---|-------|------|
| #a1b2c3d4 | 10:30 PM | 🔴 | Fixed auth token race condition | ~450 |
| #e5f6g7h8 | 10:15 PM | 🟠 | Switched to Server Components | ~820 |

</mcp-claude-mem-local-context>
```

### 7.6 Utilisation manuelle

```bash
# Depuis le dossier du projet
cd /chemin/vers/projet
~/mcp-claude-mem-local/venv/bin/python ~/mcp-claude-mem-local/plugin/scripts/context-hook.py session-start
```

**Alias recommandé (`.zshrc` / `.bashrc`) :**
```bash
alias mcp-claude-mem-local-context="~/mcp-claude-mem-local/venv/bin/python ~/mcp-claude-mem-local/plugin/scripts/context-hook.py session-start"
```

---

## 8. Interface Web

### 8.1 Génération

```bash
cd ~/mcp-claude-mem-local
source venv/bin/activate
python src/web_ui.py
```

Génère `viewer.html` avec les données actuelles.

### 8.2 Lancement

```bash
cd ~/mcp-claude-mem-local && python3 -m http.server 8080
```

Accessible sur : http://localhost:8080/viewer.html

### 8.3 Fonctionnalités

| Fonctionnalité | Description |
|----------------|-------------|
| **Statistiques** | Total, par catégorie, cette semaine |
| **Filtres type** | bugfix, decision, feature, etc. |
| **Filtres projet** | Par projet/contexte |
| **Recherche** | Recherche textuelle temps réel |
| **Onglet Prompts** | Historique des prompts |
| **Expand/Collapse** | Voir le contenu complet |

### 8.4 Régénération

L'interface est statique. Pour mettre à jour avec les nouvelles données :

```bash
python src/web_ui.py
# Refresh du navigateur
```

---

## 9. Embeddings

### 9.1 Modèle par défaut

| Propriété | Valeur |
|-----------|--------|
| **Modèle** | nomic-embed-text |
| **Dimensions** | 768 |
| **Taille** | ~274 MB |
| **Performance** | ~100ms/embedding |

### 9.2 API Ollama

```python
async def get_embedding(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{OLLAMA_HOST}/api/embeddings",
            json={"model": EMBEDDING_MODEL, "prompt": text}
        )
        return response.json()["embedding"]
```

### 9.3 Format pgvector

pgvector attend une string, pas une liste Python :

```python
def format_embedding(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"

# Utilisation dans SQL
await conn.execute(
    "INSERT INTO memories (content, embedding) VALUES ($1, $2::vector)",
    content, format_embedding(embedding)
)
```

### 9.4 Recherche par similarité

```sql
-- Cosine similarity (1 = identique, 0 = orthogonal)
SELECT 
    id, content, summary,
    1 - (embedding <=> $1::vector) as similarity
FROM memories
WHERE 1 - (embedding <=> $1::vector) >= 0.5
ORDER BY similarity DESC
LIMIT 5;
```

### 9.5 Modèles alternatifs

| Modèle | Dimensions | Taille | Notes |
|--------|------------|--------|-------|
| nomic-embed-text | 768 | 274 MB | Recommandé |
| all-minilm | 384 | 45 MB | Plus léger |
| mxbai-embed-large | 1024 | 670 MB | Plus précis |

Pour changer de modèle :
```bash
ollama pull mxbai-embed-large
# Modifier .env: EMBEDDING_MODEL=mxbai-embed-large
# Modifier .env: EMBEDDING_DIMENSIONS=1024
# Recréer la table avec vector(1024)
```

---

## 10. Migration depuis claude-mem

### 10.1 Prérequis

- claude-mem installé avec des données existantes
- Base SQLite : `~/.claude-mem/claude-mem.db`

### 10.2 Script de migration

```bash
python ~/mcp-claude-mem-local/migrate.py
```

### 10.3 Ce qui est migré

| Source (claude-mem) | Destination (MCP-Claude-mem-local) |
|---------------------|------------------------|
| `observations.narrative` | `memories.content` |
| `observations.title` | `memories.summary` |
| `observations.type` | `memories.category` |
| `observations.concepts` | `memories.tags` |
| `observations.project` | `memories.project_context` |
| `user_prompts.prompt_text` | `user_prompts.prompt_text` |

### 10.4 Temps estimé

- ~1 seconde par observation (génération embedding)
- 1000 observations ≈ 15-20 minutes

---

## 11. Maintenance & Opérations

### 11.1 Démarrage des services

```bash
# PostgreSQL (macOS Homebrew - auto-start)
brew services start postgresql@17

# Vérifier PostgreSQL
pg_isready
# localhost:5432 - accepting connections

# Ollama (démarrage manuel requis)
open -a Ollama
# ou: ollama serve &

# Vérifier Ollama
ollama list
```

### 11.2 Sauvegarde

```bash
# Backup complet
pg_dump -U claude claude_memory > \
  ~/mcp-claude-mem-local/backups/backup-$(date +%Y%m%d-%H%M%S).sql

# Backup automatique (crontab)
0 2 * * * pg_dump -U claude claude_memory > ~/mcp-claude-mem-local/backups/backup-$(date +\%Y\%m\%d).sql
```

### 11.3 Restauration

```bash
psql -U claude claude_memory < backup-20260128.sql
```

### 11.4 Nettoyage

```bash
# Supprimer les mémoires de plus de 6 mois non consultées
psql -U claude -d claude_memory -c "
DELETE FROM memories
WHERE last_accessed_at < NOW() - INTERVAL '6 months'
  AND access_count < 2;
"

# Vacuum (récupérer l'espace)
psql -U claude -d claude_memory -c "VACUUM ANALYZE;"
```

### 11.5 Monitoring

```bash
# Taille de la base
psql -U claude -d claude_memory -c "
SELECT pg_size_pretty(pg_database_size('claude_memory'));
"

# Nombre de mémoires par catégorie
psql -U claude -d claude_memory -c "
SELECT category, COUNT(*) FROM memories GROUP BY category ORDER BY COUNT(*) DESC;
"

# Logs PostgreSQL (macOS Homebrew)
tail -50 /opt/homebrew/var/log/postgresql@17.log

# Logs PostgreSQL (Linux)
sudo journalctl -u postgresql --tail 50
```

---

## 12. Dépannage

### 12.1 Le serveur MCP ne se connecte pas

```bash
# 1. Vérifier PostgreSQL
pg_isready
# Si erreur: brew services start postgresql@17

# 2. Vérifier Ollama
ollama list
# Si erreur: ollama serve

# 3. Tester la connexion
cd ~/mcp-claude-mem-local && source venv/bin/activate
python -c "
import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()
async def test():
    conn = await asyncpg.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', 5432)),
        database=os.getenv('PG_DATABASE', 'claude_memory'),
        user=os.getenv('PG_USER', 'claude'),
        password=os.getenv('PG_PASSWORD')
    )
    print('✅ Connexion OK')
    await conn.close()
asyncio.run(test())
"
```

### 12.2 Erreur "role does not exist"

```bash
# Créer l'utilisateur s'il n'existe pas
createuser -s claude
psql -c "ALTER USER claude PASSWORD 'your_secure_password';"

# Vérifier quel PostgreSQL tourne sur le port 5432
lsof -i :5432
```

### 12.3 Erreur "expected str, got list" (embeddings)

Le fix est dans `server.py` :
```python
def format_embedding(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"

# Dans les requêtes: $5::vector au lieu de $5
```

### 12.4 Ollama timeout

```bash
# Augmenter le timeout dans server.py
async with httpx.AsyncClient(timeout=60.0) as client:  # 60s au lieu de 30s

# Ou vérifier la RAM disponible
# nomic-embed-text nécessite ~1GB RAM
```

### 12.5 L'interface web ne se génère pas

```bash
# Vérifier les dépendances
pip install asyncpg python-dotenv

# Vérifier PostgreSQL
docker start mcp-claude-mem-local-postgres

# Régénérer
python src/web_ui.py
```

---

## 13. Sécurité

### 13.1 Données locales

- Toutes les données restent sur votre machine
- Aucune donnée envoyée à des services externes
- Embeddings générés localement via Ollama

### 13.2 Credentials

```bash
# Ne jamais commiter .env
echo ".env" >> .gitignore

# Utiliser des mots de passe forts en production
openssl rand -base64 32  # Générer un mot de passe
```

### 13.3 API Key Authentication (Optionnel)

Définir `API_KEY` dans `.env` pour exiger une authentification sur tous les endpoints API:

```env
API_KEY=your-secret-api-key-here
```

Quand défini, toutes les requêtes doivent inclure le header: `X-API-Key: your-secret-api-key-here`

### 13.4 Rate Limiting

Par défaut: 60 requêtes par minute. Configurable via variables d'environnement:

```env
RATE_LIMIT_REQUESTS=60    # Max requêtes par fenêtre
RATE_LIMIT_WINDOW=60      # Durée de la fenêtre en secondes
```

### 13.5 Security Headers

Toutes les réponses HTTP incluent des headers de sécurité:
- `Content-Security-Policy` (CSP)
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `X-XSS-Protection: 1; mode=block`

### 13.6 CORS

Par défaut, CORS est restreint à localhost. Configurer les origines autorisées:

```env
ALLOWED_ORIGINS=localhost:8080,localhost:3000
```

### 13.7 Protection SSRF

La variable `OLLAMA_HOST` est validée pour prévenir les attaques Server-Side Request Forgery.

### 13.8 Réseau

```bash
# PostgreSQL écoute uniquement sur localhost par défaut
# Pour une utilisation en équipe, configurer SSL/TLS dans postgresql.conf

# Vérifier les ports utilisés
lsof -i :5432
```

### 13.9 Backup chiffré

```bash
# Backup chiffré avec GPG
pg_dump -U claude claude_memory | \
  gpg --symmetric --cipher-algo AES256 > backup.sql.gpg
```

---

## 14. Contribution

### 14.1 Structure du repo

```
mcp-claude-mem-local/
├── src/
│   ├── server.py          # MCP Server
│   ├── web_ui.py          # Générateur UI
│   └── embeddings.py      # Abstraction embeddings
├── plugins/
│   ├── hooks/
│   │   └── hooks.json
│   └── scripts/
│       ├── context-hook.py
│       └── capture-prompt.py
├── scripts/
│   ├── init.sql           # Schéma de base de données
│   └── security-check.sh  # Script de vérification sécurité
├── tests/
│   ├── test_server.py
│   ├── test_embeddings.py
│   └── test_hooks.py
├── docs/
│   ├── MCP-Claude-mem-local-Documentation-Technique.md
│   └── hooks-prompts-capture.md
├── .env.example
├── requirements.txt
├── README.md
└── LICENSE
```

### 14.2 Setup développement

```bash
git clone https://github.com/your-org/mcp-claude-mem-local.git
cd mcp-claude-mem-local
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # pytest, black, mypy
```

### 14.3 Tests

```bash
# Unit tests
pytest tests/ -v

# Avec couverture
pytest tests/ --cov=src --cov-report=html
```

### 14.4 Style de code

```bash
# Formatting
black src/ tests/

# Type checking
mypy src/

# Linting
ruff check src/
```

### 14.5 Pull Request

1. Fork le repo
2. Créer une branche (`git checkout -b feature/ma-feature`)
3. Commiter (`git commit -m 'Add ma feature'`)
4. Pusher (`git push origin feature/ma-feature`)
5. Ouvrir une Pull Request

---

## Changelog

### v1.0.0 (2026-01-28)
- Initial release
- 5 outils MCP (store, retrieve, list, delete, stats)
- PostgreSQL + pgvector storage
- Ollama embeddings (nomic-embed-text)
- Web UI dashboard
- Context injection in CLAUDE.md
- Migration from claude-mem

---

<p align="center">
  <b>🧠 MCP-Claude-mem-local</b><br>
  <i>Documentation Technique v1.0</i>
</p>