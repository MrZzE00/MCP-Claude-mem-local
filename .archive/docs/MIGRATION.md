# Migration Guide

## Upgrading to ACT-R Cognitive Scoring

This guide covers upgrading an existing claude-memory-local installation to include ACT-R cognitive scoring.

### Prerequisites

- Existing installation with PostgreSQL + pgvector running
- Python 3.11+ with asyncpg installed
- Backup of your database (recommended)

### Step 1: Backup Your Database

```bash
pg_dump -U claude claude_memory > ~/backup_pre_actr_$(date +%Y%m%d).sql
```

### Step 2: Run the Migration

#### Option A: Using the migration runner (recommended)

```bash
cd ~/claude-memory-local
source venv/bin/activate
python scripts/migrate.py
```

To preview changes without applying:

```bash
python scripts/migrate.py --dry-run
```

#### Option B: Manual SQL execution

```bash
psql -U claude -d claude_memory < scripts/migrations/001_actr_schema.sql
```

### Step 3: Verify Migration

```bash
psql -U claude -d claude_memory -c "SELECT COUNT(*) FROM memories;"
# Should return your existing count (e.g., 1554+)

psql -U claude -d claude_memory -c "SELECT COUNT(*) FROM memories WHERE access_timestamps != '{}';"
# Should be > 0 (memories with access_count > 0 got synthetic timestamps)

psql -U claude -d claude_memory -c "SELECT DISTINCT memory_status FROM memories;"
# Should return: active
```

### Step 4: Copy New Source Files

```bash
cp src/actr_scoring.py ~/claude-memory-local/src/
cp src/forgetting.py ~/claude-memory-local/src/
cp src/server.py ~/claude-memory-local/src/
cp scripts/migrate.py ~/claude-memory-local/scripts/
mkdir -p ~/claude-memory-local/scripts/migrations
cp scripts/migrations/001_actr_schema.sql ~/claude-memory-local/scripts/migrations/
```

### Step 5: Update Environment Variables

Add ACT-R variables to `~/claude-memory-local/.env`:

```env
# ACT-R Cognitive Scoring
USE_ACTR_SCORING=true
ACTR_DECAY_D=0.5
ACTR_WEIGHT_W=11.0
ACTR_NOISE_SIGMA=1.2
ACTR_THRESHOLD_TAU=-2.0
ACTR_SPREADING_S=2.0
ACTR_USE_SPREADING=true
ACTR_USE_NOISE=true
ACTR_PREFETCH_LIMIT=50
ACTR_FORGETTING_SCHEDULE=manual
```

### Step 6: Restart MCP Server

If using launchd:
```bash
launchctl kickstart -k gui/$(id -u)/com.claude-memory-local.server
```

Or restart Claude Code / your IDE.

### Step 7: Test

In Claude Code, run:
```
retrieve_memories("test ACT-R scoring")
```

The results should include `activation:` scores alongside similarity scores.

### Rollback

To disable ACT-R scoring without removing the schema:

```env
USE_ACTR_SCORING=false
```

To fully rollback the schema (not recommended):

```sql
ALTER TABLE memories DROP COLUMN IF EXISTS access_timestamps;
ALTER TABLE memories DROP COLUMN IF EXISTS memory_status;
ALTER TABLE memories DROP COLUMN IF EXISTS actr_activation;
ALTER TABLE memories DROP COLUMN IF EXISTS activation_updated_at;
ALTER TABLE memories DROP CONSTRAINT IF EXISTS check_memory_status;
DELETE FROM schema_migrations WHERE version = 1;
```

---

## What Changed

### New Columns on `memories` Table

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `access_timestamps` | `TIMESTAMP[]` | `'{}'` | Individual access timestamps for power-law decay |
| `memory_status` | `VARCHAR(10)` | `'active'` | Cognitive status: active/dormant/forgotten |
| `actr_activation` | `FLOAT` | `NULL` | Cached activation score from last computation |
| `activation_updated_at` | `TIMESTAMP` | `NULL` | When the cached score was last computed |

### New Files

| File | Purpose |
|------|---------|
| `src/actr_scoring.py` | ACT-R scoring engine (B(m), S(m), noise, activation) |
| `src/forgetting.py` | Strategic forgetting engine (status transitions) |
| `scripts/migrate.py` | Versioned migration runner |
| `scripts/migrations/001_actr_schema.sql` | Schema migration for ACT-R columns |

### New MCP Tool

- `memory_forgetting_cycle()` — Triggers a forgetting cycle that recalculates all memory activations and transitions statuses.

### Modified MCP Tools

- `retrieve_memories()` — Now supports ACT-R re-ranking and `include_forgotten` parameter.
- `memory_stats()` — Now shows memory status distribution and ACT-R scoring mode.
