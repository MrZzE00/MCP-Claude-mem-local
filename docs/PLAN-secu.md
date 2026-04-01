# Plan de Securite Complet — MCP-Claude-mem-local

> Ce document consolide les deux audits de securite (31 mars + 1er avril 2026)
> et fournit toutes les instructions pour securiser une nouvelle machine apres `git pull`.

---

## Table des matieres

1. [Audit 1 — Remediation initiale (31 mars 2026)](#audit-1--remediation-initiale)
2. [Audit 2 — Remediation complementaire (1er avril 2026)](#audit-2--remediation-complementaire)
3. [Checklist Machine 2 — Commandes locales post git pull](#checklist-machine-2)

---

## Audit 1 — Remediation initiale

**Scope** : 38 findings (9 critiques, 4 eleves, 17 moyens, 8 faibles)
**Commit** : `77399a9` + `f9046b4`

### Changements de code realises

#### Phase 1 — Auth, CI, Privileges

| Finding | Fichier | Changement |
|---------|---------|------------|
| API_KEY obligatoire | `src/api_server.py` | Ajout `REQUIRE_AUTH` env var, RuntimeError si absent |
| MCP stdio trust doc | `src/server.py` | Commentaire documentant le modele de confiance |
| CI hardcoded password | `.github/workflows/ci.yml` | `synaptic123` → `${{ secrets.PG_TEST_PASSWORD }}` |
| Actions pinees SHA | `.github/workflows/ci.yml` | Toutes les actions epinglees par commit SHA |
| CI permissions | `.github/workflows/ci.yml` | `permissions: contents: read` + `write` pour release |
| SUPERUSER supprime | `install.sh` | `createuser -s` → `createuser` + GRANT minimaux |
| curl\|sh Ollama | `install.sh` | Download + validation shebang + execution |
| Password SQL escape | `install.sh` | Echappement quotes simples dans ALTER USER |
| Password non affiche | `install.sh` | Redirige vers `.env` au lieu d'afficher |
| .env chmod 600 | `install.sh` | `chmod 600` apres creation |
| GRANT dans init.sql | `scripts/init.sql` | Decommente + user `claude` au lieu de `synaptic` |
| Checksum migrations | `scripts/migrate.py` | Verification SHA-256 + `checksums.json` |

#### Phase 2 — Validation des entrees

| Finding | Fichier | Changement |
|---------|---------|------------|
| ACT-R env bounds | `src/actr_scoring.py` | `_float()` et `_int()` avec clamping |
| Category whitelist | `src/server.py` | `VALID_CATEGORIES` frozenset |
| Importance clamping | `src/server.py` | `max(0.0, min(1.0, importance))` |
| Limit cap | `src/server.py` | `max(1, min(100, limit))` |
| max_results/min_similarity | `src/server.py` | Bornes dans `retrieve_memories` |
| UUID validation | `src/server.py` | `UUID(memory_id)` avec ValueError |
| OLLAMA_HOST validation | `src/server.py` | urlparse + whitelist localhost |
| host.docker.internal retire | `src/api_server.py` | Retire de `ALLOWED_OLLAMA_HOSTS` |
| ALLOWED_ORIGINS validation | `src/api_server.py` | Validation URL format |
| Bypass /static retire | `src/api_server.py` | Seul "/" bypass l'auth |

#### Phase 3 — Isolation, RLS, Concurrence

| Finding | Fichier | Changement |
|---------|---------|------------|
| USER_ID env var | `src/server.py` | Filtre `user_id` dans toutes les requetes MCP |
| user_id dans hybrid_search | `src/hybrid_search.py` | Parametre `user_id` dans `build_search_queries` |
| RLS policies | `scripts/migrations/003_row_level_security.sql` | ALTER TABLE + ENABLE RLS + policies |
| TOCTOU fix | `src/forgetting.py` | `pg_advisory_xact_lock(42)` + `FOR UPDATE` |
| Ring buffer timestamps | `src/server.py`, `src/forgetting.py` | Cap 1000 avec `access_timestamps[2:]` |

#### Phase 4 — Securite web

| Finding | Fichier | Changement |
|---------|---------|------------|
| CSP meta tags | `viewer.html`, `web_ui.py` | Ajout CSP meta tag |
| CSP all paths | `src/api_server.py` | CSP appliquee a tous les paths |
| escapeHtml apostrophe | `src/api_server.py` | Ajout `.replace(/'/g, '&#39;')` |
| Secret scrubbing | `plugins/scripts/capture-prompt.py` | Regex patterns pour API keys, tokens, PEM |
| CLAUDE_MEMORY_HOME valid. | `install.sh` | Validation chemin sous `$HOME` ou `/opt` |

#### Phase 5 — Dependances, docs

| Finding | Fichier | Changement |
|---------|---------|------------|
| Versions alignees | `pyproject.toml` | Upper bounds alignes avec requirements.txt |
| .gitignore crypto | `.gitignore` | `*.pem`, `*.key`, `*.p12`, etc. |
| SECURITY.md | `SECURITY.md` | Nouveau fichier documentant le modele de securite |

---

## Audit 2 — Remediation complementaire

**Scope** : 22 findings (5 high, 9 medium, 8 low)
**Commit** : (apres ce plan)

### Changements de code realises

#### Phase A — Findings HIGH

| Finding | Fichier | Changement |
|---------|---------|------------|
| user_id dans api_server | `src/api_server.py` | `USER_ID` + filtre dans /api/stats, /api/memories, /api/search, /api/prompts |
| RLS fail-open | `scripts/migrations/004_harden_rls.sql` | DROP + recreate policies sans clause NULL bypass |
| SET app.current_user_id | `src/server.py`, `src/api_server.py` | `init=_init_connection` dans create_pool |
| SSRF capture-prompt | `plugins/scripts/capture-prompt.py` | Validation OLLAMA_HOST hostname |
| X-Forwarded-For | `src/api_server.py` | `TRUST_PROXY` env var, ignore XFF par defaut |

#### Phase B — Findings MEDIUM

| Finding | Fichier | Changement |
|---------|---------|------------|
| Rate limiter cap | `src/api_server.py` | `_MAX_TRACKED_IPS = 10000`, clear si depasse |
| Category dans list_memories | `src/server.py` | Validation contre `VALID_CATEGORIES` |
| Content max length | `src/server.py` | Limite 50000 caracteres |
| web_ui.py escape | `web_ui.py` | `html.escape()` au lieu de replace manuel |
| Deps dev bornes | `requirements-dev.txt` | Upper bounds sur toutes les deps |
| pyproject fastapi | `pyproject.toml` | Section `[project.optional-dependencies] api` |
| CREATE EXTENSION | `install.sh` | Execute par postgres avant le schema |
| Path is_relative_to | `plugins/scripts/context-hook.py` | `is_relative_to()` remplace `startswith()` |
| .env.example | `.env.example` | `REQUIRE_AUTH=true` + `TRUST_PROXY=false` ajoutes |

#### Phase C — Findings LOW

| Finding | Fichier | Changement |
|---------|---------|------------|
| command_timeout | `src/server.py`, `src/api_server.py` | `command_timeout=30` dans create_pool |
| escapeHtml stats | `src/api_server.py` | `escapeHtml(c.category)` dans template |
| viewer.html gitignore | `.gitignore` | Ajoute viewer.html (fichier genere) |
| hooks.json paths | `plugins/hooks/hooks.json` | `plugin/` → `plugins/` |
| user_id DEFAULT | `scripts/migrations/004_harden_rls.sql` | `ALTER TABLE ... SET DEFAULT 'default'` |
| SECURITY.md update | `SECURITY.md` | Mise a jour RLS, TRUST_PROXY, audit 2 |

---

## Checklist Machine 2

> Suivre ces etapes dans l'ordre apres un `git pull` sur la seconde machine.

### Prerequis

```bash
cd ~/Documents/_CODE/36_claude-memory-local  # ou votre repertoire
git pull origin main
```

### Etape 1 — Privileges PostgreSQL

```bash
# Identifier l'utilisateur admin PostgreSQL (souvent votre username macOS)
# Remplacer "nnadir" par votre username si different
ADMIN_USER=$(whoami)

# Revoquer les privileges eleves de l'utilisateur claude
psql -U $ADMIN_USER -d postgres -c "ALTER USER claude NOSUPERUSER NOCREATEROLE NOCREATEDB;"

# Verifier
psql -U $ADMIN_USER -d postgres -c "\du claude"
# Attendu : aucun attribut (Superuser, Create role, Create DB doivent etre absents)

# Accorder les permissions minimales
psql -U $ADMIN_USER -d claude_memory -c "GRANT USAGE ON SCHEMA public TO claude;"
psql -U $ADMIN_USER -d claude_memory -c "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO claude;"
psql -U $ADMIN_USER -d claude_memory -c "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO claude;"
psql -U $ADMIN_USER -d claude_memory -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO claude;"
```

### Etape 2 — Migrations

```bash
# Activer le venv
source venv/bin/activate  # ou ~/claude-memory-local/venv/bin/activate

# Executer les migrations (003 + 004)
# Migration 003 : Ajoute user_id, active RLS, cree policies
# Migration 004 : Durcit les policies RLS, ajoute DEFAULT 'default'
ADMIN_USER=$(whoami)
psql -U $ADMIN_USER -d claude_memory -f scripts/migrations/003_row_level_security.sql
psql -U $ADMIN_USER -d claude_memory -f scripts/migrations/004_harden_rls.sql

# Verifier que les migrations sont appliquees
psql -U $ADMIN_USER -d claude_memory -c "SELECT version, name FROM schema_migrations ORDER BY version;"
# Attendu : versions 1, 2, 3, 4

# Verifier RLS active
psql -U $ADMIN_USER -d claude_memory -c "SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public' AND tablename IN ('memories', 'user_prompts');"
# Attendu : rowsecurity = true pour les deux tables

# Verifier les policies
psql -U $ADMIN_USER -d claude_memory -c "SELECT polname FROM pg_policy;"
# Attendu : memories_user_isolation, prompts_user_isolation
```

### Etape 3 — Si table user_prompts_backup existe

```bash
# Verifier si la table existe
psql -U $ADMIN_USER -d claude_memory -c "SELECT tablename FROM pg_tables WHERE tablename='user_prompts_backup';"

# Si elle existe, activer RLS dessus
psql -U $ADMIN_USER -d claude_memory -c "ALTER TABLE user_prompts_backup ENABLE ROW LEVEL SECURITY;"
psql -U $ADMIN_USER -d claude_memory -c "CREATE POLICY backup_user_isolation ON user_prompts_backup USING (user_id = current_setting('app.current_user_id', true) OR user_id IS NULL);"
```

### Etape 4 — Fichier .env

```bash
ENV_FILE=~/claude-memory-local/.env

# Generer et ajouter API_KEY si absente
if ! grep -q "^API_KEY=" "$ENV_FILE" 2>/dev/null; then
    API_KEY=$(openssl rand -hex 32)
    echo "" >> "$ENV_FILE"
    echo "# Security (audit 2026-04-01)" >> "$ENV_FILE"
    echo "REQUIRE_AUTH=true" >> "$ENV_FILE"
    echo "API_KEY=$API_KEY" >> "$ENV_FILE"
    echo "TRUST_PROXY=false" >> "$ENV_FILE"
    echo "API_KEY generee (prefixe: ${API_KEY:0:8}...)"
fi

# Securiser les permissions
chmod 600 "$ENV_FILE"

# Verifier
stat -f "%Sp" "$ENV_FILE"  # macOS
# ou: stat -c "%a" "$ENV_FILE"  # Linux
# Attendu : -rw------- ou 600
```

### Etape 5 — Verification reseau

```bash
# Verifier que rien n'ecoute sur 0.0.0.0
lsof -i -P 2>/dev/null | grep -E "(postgres|ollama|python)" | grep -v "127.0.0.1\|localhost\|\[::1\]"
# Attendu : aucune sortie (tout sur localhost)
```

### Etape 6 — Verification des donnees

```bash
# Verifier le backfill user_id
psql -U $ADMIN_USER -d claude_memory -c "SELECT COUNT(*) FILTER (WHERE user_id IS NULL) as null_count FROM memories;"
# Attendu : 0

# Verifier le cap des timestamps
psql -U $ADMIN_USER -d claude_memory -c "SELECT MAX(array_length(access_timestamps, 1)) FROM memories;"
# Attendu : <= 1000

# Verifier les extensions
psql -U $ADMIN_USER -d claude_memory -c "SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm');"
# Attendu : vector et pg_trgm
```

### Etape 7 — Test fonctionnel

```bash
# Redemarrer le serveur MCP (redemarrer Claude Code)
# Tester store_memory et retrieve_memories via Claude Code

# Tester l'API server (optionnel)
source ~/claude-memory-local/venv/bin/activate
python3 src/api_server.py &
sleep 2

# Sans API key → 401
curl -s http://127.0.0.1:8080/api/stats | head -20
# Attendu : {"detail":"API key required"}

# Avec API key → 200
API_KEY=$(grep "^API_KEY=" ~/claude-memory-local/.env | cut -d= -f2)
curl -s -H "X-API-Key: $API_KEY" http://127.0.0.1:8080/api/stats | head -20
# Attendu : {"total_memories":...}

kill %1  # arreter le serveur de test
```

---

## Resume des audits

| Metrique | Audit 1 (31 mars) | Audit 2 (1er avril) | Apres remediation |
|----------|-------------------|---------------------|-------------------|
| Critique | 9 | 0 | 0 |
| Haute | 4 | 5 | 0 |
| Moyenne | 17 | 9 | 0 |
| Faible | 8 | 8 | 0 |
| **Total** | **38** | **22** | **0** |
| Positifs confirmes | — | 28 | — |
