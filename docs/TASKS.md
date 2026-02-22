# ACT-R Cognitive Scoring -- Task Backlog

> **Project**: MCP-Claude-mem-local
> **Scope**: Integration of ACT-R cognitive memory model into the existing retrieval and ranking pipeline
> **Reference**: [docs/ACT-R.md](./ACT-R.md) -- Architecture Memoire Cognitive ACT-R x LLM
> **Last updated**: 2026-02-22

---

## Overview

This backlog tracks the 10 tasks required to replace the current naive scoring formula
(`cosine_similarity * importance_score`) with a composite cognitive scoring model based on
ACT-R (Adaptive Control of Thought -- Rational). The work is organized in 5 phases,
from documentation through deployment.

**Phase summary**:

| Phase | Name | Tasks | Priority |
|-------|------|-------|----------|
| 0 | Documentation & Structuration | ACT-R-00 | critical |
| 1 | Foundation | ACT-R-01, ACT-R-05 | critical, high |
| 2 | Scoring Engine | ACT-R-02, ACT-R-03 | critical |
| 2-3 | Quality | ACT-R-07 | high |
| 3 | Forgetting Engine | ACT-R-04, ACT-R-08 | high, medium |
| 4 | Adaptive Scoring | ACT-R-06 | medium |
| 5 | Deployment | ACT-R-09 | critical |

---

## Tasks

### ACT-R-00: Documentation strategique & mise a jour TASKS.md
```yaml
id: ACT-R-00
title: "Documentation strategique & mise a jour TASKS.md"
phase: "Phase 0 — Documentation & Structuration"
priority: critical
status: pending
completion: 0
last_update: "2026-02-22"

description: |
  Produce the two strategic documentation files that frame the entire ACT-R
  integration effort. First, replace the template-only content in docs/TASKS.md
  with the complete ACT-R task backlog (ACT-R-00 through ACT-R-09), providing
  structured YAML definitions for every task including dependencies, success
  criteria, and file references. Second, create docs/Act-r impacts.md as a
  standalone strategic document that explains the limitations of the current
  scoring model, the scientific justification for ACT-R, the technical
  architecture of the migration, the differentiation it provides, and the
  measurable impact on recall quality. Both documents serve as the source of
  truth for planning, review, and contributor onboarding throughout the project.

dependencies: []

success_criteria:
  - description: "docs/TASKS.md contains all 10 ACT-R tasks in valid YAML format"
    validated: false
  - description: "docs/Act-r impacts.md covers the 5 required sections (limits, justification, architecture, differentiation, impact)"
    validated: false
  - description: "Both documents reference docs/ACT-R.md for formulas and competitive landscape"
    validated: false

files:
  create:
    - "docs/Act-r impacts.md"
  modify:
    - "docs/TASKS.md"
  reference:
    - "docs/ACT-R.md"
```

---

### ACT-R-01: Schema PostgreSQL & systeme de migration
```yaml
id: ACT-R-01
title: "Schema PostgreSQL & systeme de migration"
phase: "Phase 1 — Foundation"
priority: critical
status: pending
completion: 0
last_update: "2026-02-22"

description: |
  Create a versioned migration system for the PostgreSQL database and apply the
  first migration that introduces the columns required by the ACT-R scoring
  model. The migration must:

  1. Add an access_timestamps column (TIMESTAMP[] DEFAULT '{}') to record every
     retrieval event as an individual timestamp, replacing the scalar access_count
     for base-level activation computation.
  2. Add a memory_status column (VARCHAR(10) DEFAULT 'active') with a CHECK
     constraint limiting values to 'active', 'dormant', and 'forgotten'.
  3. Add an actr_activation column (FLOAT) to cache the last computed activation
     score for each memory.
  4. Add an activation_updated_at column (TIMESTAMP) to track when the cached
     activation was last recalculated.
  5. Migrate existing access_count values into synthetic timestamps. For a memory
     with access_count = N, generate N evenly spaced timestamps between
     created_at and last_accessed_at.
  6. Create a GIN index on access_timestamps for array query performance.
  7. Provide a Python migration runner (scripts/migrate.py) that applies numbered
     SQL files in order and records applied migrations in a schema_migrations
     table.

  The migration must be idempotent and safe to run against a production database
  containing 1,554+ existing memories.

dependencies: []

success_criteria:
  - description: "Migration SQL adds all 4 new columns with correct types and defaults"
    validated: false
  - description: "Existing access_count values are converted to synthetic timestamps"
    validated: false
  - description: "GIN index on access_timestamps is created"
    validated: false
  - description: "scripts/migrate.py applies migrations idempotently"
    validated: false
  - description: "Migration is safe to run against production data without data loss"
    validated: false

files:
  create:
    - "scripts/migrations/001_actr_schema.sql"
    - "scripts/migrate.py"
  modify:
    - "scripts/init.sql"
  reference:
    - "docs/ACT-R.md"
```

---

### ACT-R-02: Module de scoring ACT-R (src/actr_scoring.py)
```yaml
id: ACT-R-02
title: "Module de scoring ACT-R (src/actr_scoring.py)"
phase: "Phase 2 — Scoring Engine"
priority: critical
status: pending
completion: 0
last_update: "2026-02-22"

description: |
  Implement the standalone ACT-R scoring module as a pure-Python file with no
  side effects, making it independently testable. The module must contain:

  1. ACTRConfig dataclass -- holds all tunable parameters (decay d=0.5,
     noise sigma=1.2, semantic weight w=11.0, spreading base S, retrieval
     threshold tau) with a from_env() class method that reads overrides from
     environment variables.
  2. compute_base_level(access_timestamps, current_time, d) -- implements the
     ACT-R base-level learning equation: B(m) = ln(sum((t - ti)^-d)) where ti
     are past access times and d is the decay parameter. Returns -inf when
     access_timestamps is empty.
  3. compute_spreading_activation(memory_tags, query_tags, S, fan_counts) --
     implements tag-based spreading: S(m) = sum_j(Wj * (S - ln(fan_j))) where
     fan_j is the number of memories sharing tag j.
  4. compute_noise(sigma) -- returns a sample from N(0, sigma) for probabilistic
     variability.
  5. compute_activation(memory, query_tags, cosine_sim, config) -- combines all
     components: A(m) = B(m) + w * cosine_sim + S(m) + epsilon.
  6. score_and_rank_memories(memories, query_tags, cosine_sims, config) --
     computes activation for a list of memories and returns them sorted by
     descending activation score.

  All functions must use standard library math plus numpy only where necessary.
  No database or network dependencies.

dependencies:
  - "ACT-R-01"

success_criteria:
  - description: "All 5 scoring functions are implemented and callable"
    validated: false
  - description: "ACTRConfig.from_env() reads and validates environment variables"
    validated: false
  - description: "compute_base_level returns -inf for empty timestamp lists"
    validated: false
  - description: "score_and_rank_memories returns memories sorted by activation descending"
    validated: false
  - description: "Module has no database or network imports"
    validated: false

files:
  create:
    - "src/actr_scoring.py"
  modify: []
  reference:
    - "docs/ACT-R.md"
```

---

### ACT-R-03: Integration ACT-R dans retrieve_memories()
```yaml
id: ACT-R-03
title: "Integration ACT-R dans retrieve_memories()"
phase: "Phase 2 — Scoring Engine"
priority: critical
status: pending
completion: 0
last_update: "2026-02-22"

description: |
  Modify the existing retrieve_memories MCP tool in src/server.py to support
  two-stage retrieval with ACT-R re-ranking:

  Stage 1 -- SQL pre-filter: The existing pgvector cosine similarity query
  fetches the top 50 candidate memories (up from the current final limit).
  This stage runs entirely in PostgreSQL and benefits from the HNSW index.

  Stage 2 -- Python ACT-R re-ranking: The 50 candidates are passed to
  score_and_rank_memories() from src/actr_scoring.py. The function computes
  composite activation scores incorporating base-level activation (frequency
  and recency), semantic similarity (weighted cosine), spreading activation
  (tag overlap), and noise. The top max_results memories are returned to the
  caller.

  Additional requirements:
  - After retrieval, append the current timestamp to the access_timestamps
    array for each returned memory (recording the access event for future
    base-level computation).
  - Maintain full backward compatibility via the USE_ACTR_SCORING environment
    variable (default: false). When false, the existing cosine * importance
    ranking is preserved unchanged.
  - The response format must not change: callers receive the same fields in
    the same structure.

dependencies:
  - "ACT-R-01"
  - "ACT-R-02"

success_criteria:
  - description: "Two-stage retrieval (SQL top 50 + Python re-ranking) is implemented"
    validated: false
  - description: "access_timestamps is updated on each retrieval"
    validated: false
  - description: "USE_ACTR_SCORING=false preserves original behavior exactly"
    validated: false
  - description: "Response format is backward compatible"
    validated: false

files:
  create: []
  modify:
    - "src/server.py"
  reference:
    - "src/actr_scoring.py"
    - "docs/ACT-R.md"
```

---

### ACT-R-04: Engine d'oubli strategique (src/forgetting.py)
```yaml
id: ACT-R-04
title: "Engine d'oubli strategique (src/forgetting.py)"
phase: "Phase 3 — Forgetting Engine"
priority: high
status: pending
completion: 0
last_update: "2026-02-22"

description: |
  Implement the strategic forgetting engine as a standalone module that
  transitions memories between three states based on their ACT-R activation
  scores:

  1. compute_all_activations(pool, config) -- fetches all memories with their
     access_timestamps, tags, and current status, then computes A(m) for each
     using compute_activation from actr_scoring.py (with cosine_sim=0 since
     there is no query context during a forgetting cycle). Updates the
     actr_activation and activation_updated_at columns in the database.

  2. update_memory_statuses(pool, config) -- reads cached actr_activation
     values and applies status transitions:
     - A > 0: status = 'active' (memory is readily retrievable)
     - -2 < A <= 0: status = 'dormant' (memory is deprioritized but preserved)
     - A <= -2: status = 'forgotten' (memory is excluded from default results)
     The threshold values (-2, 0) must be configurable via ACTRConfig.

  3. run_forgetting_cycle(pool, config) -- orchestrates the full cycle:
     compute all activations, update statuses, and return a summary report
     (counts of active, dormant, and forgotten memories plus any transitions
     since the last cycle).

  Critical design constraint: 'forgotten' never means 'deleted'. Forgotten
  memories remain in the database and can be retrieved with explicit filters.
  The forgetting engine only changes the memory_status column.

  The module must also integrate with src/server.py to exclude 'forgotten'
  memories from the default retrieve_memories SQL pre-filter (WHERE
  memory_status != 'forgotten').

dependencies:
  - "ACT-R-01"
  - "ACT-R-02"

success_criteria:
  - description: "compute_all_activations updates actr_activation for all memories"
    validated: false
  - description: "Status transitions follow the threshold rules (active > 0, dormant -2..0, forgotten <= -2)"
    validated: false
  - description: "Forgotten memories are never deleted from the database"
    validated: false
  - description: "run_forgetting_cycle returns a summary with transition counts"
    validated: false
  - description: "retrieve_memories excludes forgotten memories by default"
    validated: false

files:
  create:
    - "src/forgetting.py"
  modify:
    - "src/server.py"
  reference:
    - "src/actr_scoring.py"
    - "docs/ACT-R.md"
```

---

### ACT-R-05: Configuration ACT-R (.env et dataclass)
```yaml
id: ACT-R-05
title: "Configuration ACT-R (.env et dataclass)"
phase: "Phase 1 — Foundation"
priority: high
status: pending
completion: 0
last_update: "2026-02-22"

description: |
  Extend the project configuration to expose all ACT-R tunable parameters
  through environment variables, maintaining the existing .env convention.

  Add the following variables to .env.example with documented defaults:

  - USE_ACTR_SCORING=false           (feature flag, enables ACT-R re-ranking)
  - ACTR_DECAY=0.5                   (d parameter for power-law decay)
  - ACTR_NOISE_SIGMA=1.2             (sigma for Gaussian noise)
  - ACTR_SEMANTIC_WEIGHT=11.0        (w parameter for cosine similarity weight)
  - ACTR_SPREADING_BASE=1.5          (S parameter for spreading activation)
  - ACTR_THRESHOLD_ACTIVE=0.0        (activation above which memory is active)
  - ACTR_THRESHOLD_FORGOTTEN=-2.0    (activation at or below which memory is forgotten)
  - ACTR_PREFILTER_LIMIT=50          (number of candidates in SQL pre-filter stage)

  The ACTRConfig dataclass in src/actr_scoring.py must read these values via
  its from_env() class method, falling back to the defaults listed above when
  variables are not set. All numeric values must be validated (d > 0, sigma > 0,
  w > 0, prefilter_limit > 0).

dependencies: []

success_criteria:
  - description: ".env.example contains all ACT-R variables with documentation"
    validated: false
  - description: "ACTRConfig.from_env() reads all variables with correct defaults"
    validated: false
  - description: "Invalid values raise clear error messages"
    validated: false

files:
  create: []
  modify:
    - ".env.example"
  reference:
    - "src/actr_scoring.py"
    - "docs/ACT-R.md"
```

---

### ACT-R-06: w adaptatif par contexte
```yaml
id: ACT-R-06
title: "w adaptatif par contexte"
phase: "Phase 4 — Adaptive Scoring"
priority: medium
status: pending
completion: 0
last_update: "2026-02-22"

description: |
  Extend the ACT-R scoring module to dynamically adjust the semantic weight
  parameter w based on the type of query being processed. Different query
  contexts benefit from different balances between semantic similarity and
  temporal/frequency signals.

  Implement two functions in src/actr_scoring.py:

  1. classify_query_type(query_text, tags, category) -- analyzes the query
     and returns a classification string. Heuristic rules:
     - 'debugging': query contains error-related keywords (error, bug, fix,
       traceback, exception) or category is 'bugfix' or 'error_solution'
     - 'architecture': query references structural concepts (architecture,
       design, pattern, schema, migration) or category is 'decision'
     - 'recurrent': query matches high-frequency access patterns or category
       is 'preference' or 'pattern'
     - 'general': default fallback

  2. get_adaptive_w(query_type, base_w) -- returns the adjusted w value:
     - debugging: w = base_w * 1.5 (range 15-20, favor exact semantic match)
     - architecture: w = base_w * 1.0 (range 10-12, balanced)
     - recurrent: w = base_w * 0.6 (range 5-8, favor frequency over semantics)
     - general: w = base_w (unchanged)

  The adaptive w must be opt-in via a USE_ADAPTIVE_W environment variable
  (default: false) so the standard fixed w remains the default behavior.

dependencies:
  - "ACT-R-02"

success_criteria:
  - description: "classify_query_type correctly categorizes debugging, architecture, and recurrent queries"
    validated: false
  - description: "get_adaptive_w returns appropriate weight multipliers for each query type"
    validated: false
  - description: "Adaptive w is disabled by default (USE_ADAPTIVE_W=false)"
    validated: false

files:
  create: []
  modify:
    - "src/actr_scoring.py"
  reference:
    - "docs/ACT-R.md"
```

---

### ACT-R-07: Tests unitaires
```yaml
id: ACT-R-07
title: "Tests unitaires"
phase: "Phase 2-3 — Quality"
priority: high
status: pending
completion: 0
last_update: "2026-02-22"

description: |
  Write comprehensive unit tests for the ACT-R scoring module and the
  forgetting engine. Tests must cover normal operation, edge cases, and
  boundary conditions.

  tests/test_actr_scoring.py (10 tests minimum):
  - test_base_level_single_access: one timestamp produces correct B(m)
  - test_base_level_multiple_accesses: multiple timestamps aggregate correctly
  - test_base_level_empty: empty list returns -inf
  - test_base_level_recent_vs_old: recent access produces higher B(m) than old
  - test_spreading_no_overlap: zero score when no tags overlap
  - test_spreading_shared_tags: positive score for overlapping tags
  - test_noise_distribution: noise samples are within expected sigma range
  - test_activation_combines_components: composite A(m) equals sum of parts
  - test_rank_ordering: score_and_rank_memories returns descending order
  - test_config_from_env: ACTRConfig.from_env() reads environment correctly

  tests/test_forgetting.py (6 tests minimum):
  - test_active_status: A > 0 produces 'active' status
  - test_dormant_status: -2 < A <= 0 produces 'dormant' status
  - test_forgotten_status: A <= -2 produces 'forgotten' status
  - test_forgotten_not_deleted: forgotten memories remain in the database
  - test_cycle_summary: run_forgetting_cycle returns correct transition counts
  - test_threshold_boundary: exact boundary values produce correct transitions

dependencies:
  - "ACT-R-02"
  - "ACT-R-04"

success_criteria:
  - description: "tests/test_actr_scoring.py contains 10+ passing tests"
    validated: false
  - description: "tests/test_forgetting.py contains 6+ passing tests"
    validated: false
  - description: "Edge cases (empty timestamps, zero tags, boundary thresholds) are covered"
    validated: false
  - description: "All tests run without database or network dependencies (mocked where needed)"
    validated: false

files:
  create:
    - "tests/test_actr_scoring.py"
    - "tests/test_forgetting.py"
  modify: []
  reference:
    - "src/actr_scoring.py"
    - "src/forgetting.py"
```

---

### ACT-R-08: Outil MCP memory_forgetting_cycle
```yaml
id: ACT-R-08
title: "Outil MCP memory_forgetting_cycle"
phase: "Phase 3 — Forgetting Engine"
priority: medium
status: pending
completion: 0
last_update: "2026-02-22"

description: |
  Expose the forgetting engine as a new MCP tool that Claude can invoke on
  demand, and extend the existing memory_stats tool to surface ACT-R indicators.

  New tool -- memory_forgetting_cycle:
  - No required parameters.
  - Calls run_forgetting_cycle() from src/forgetting.py.
  - Returns a structured report containing:
    - Total memories processed
    - Count by status (active, dormant, forgotten)
    - Transitions since last cycle (e.g., "12 active -> dormant, 3 dormant -> forgotten")
    - Timestamp of cycle execution
  - Must be guarded by USE_ACTR_SCORING flag: returns an informative error
    message when ACT-R scoring is disabled.

  Updated tool -- memory_stats:
  - When USE_ACTR_SCORING is enabled, add the following indicators to the
    existing stats output:
    - actr_enabled: true
    - memories_active: count of status='active'
    - memories_dormant: count of status='dormant'
    - memories_forgotten: count of status='forgotten'
    - avg_activation: average actr_activation across all memories
    - last_forgetting_cycle: timestamp of most recent cycle
  - When USE_ACTR_SCORING is disabled, add only: actr_enabled: false

dependencies:
  - "ACT-R-04"

success_criteria:
  - description: "memory_forgetting_cycle tool is registered and callable via MCP"
    validated: false
  - description: "Tool returns structured report with status counts and transitions"
    validated: false
  - description: "memory_stats includes ACT-R indicators when scoring is enabled"
    validated: false
  - description: "Both tools degrade gracefully when USE_ACTR_SCORING=false"
    validated: false

files:
  create: []
  modify:
    - "src/server.py"
  reference:
    - "src/forgetting.py"
    - "src/actr_scoring.py"
```

---

### ACT-R-09: Migration installation locale + documentation
```yaml
id: ACT-R-09
title: "Migration installation locale + documentation"
phase: "Phase 5 — Deployment"
priority: critical
status: pending
completion: 0
last_update: "2026-02-22"

description: |
  Perform the complete upgrade of the local production installation and produce
  all end-user documentation required for existing users to migrate.

  Migration procedure:
  1. Create a full PostgreSQL backup (pg_dump) before any changes.
  2. Run scripts/migrate.py to apply 001_actr_schema.sql against the production
     database.
  3. Verify all 1,554+ existing memories retain their data and gain the new
     columns with correct defaults and synthetic timestamps.
  4. Enable USE_ACTR_SCORING=true in the production .env file.
  5. Run a first forgetting cycle to initialize actr_activation and
     memory_status for all existing memories.
  6. Validate that retrieve_memories returns results and that the response
     format is unchanged.

  Documentation deliverables:
  - docs/MIGRATION.md: step-by-step migration guide for existing users,
    including backup instructions, prerequisites, the migration command,
    verification steps, and rollback procedure.
  - README.md: update the Architecture section to mention ACT-R scoring,
    add the new environment variables, and document the memory_forgetting_cycle
    tool.

dependencies:
  - "ACT-R-00"
  - "ACT-R-01"
  - "ACT-R-02"
  - "ACT-R-03"
  - "ACT-R-04"
  - "ACT-R-05"
  - "ACT-R-06"
  - "ACT-R-07"
  - "ACT-R-08"

success_criteria:
  - description: "Production database is backed up before migration"
    validated: false
  - description: "All existing memories retain their data after migration"
    validated: false
  - description: "retrieve_memories works correctly with USE_ACTR_SCORING=true"
    validated: false
  - description: "docs/MIGRATION.md provides complete step-by-step upgrade instructions"
    validated: false
  - description: "README.md is updated with ACT-R scoring documentation"
    validated: false

files:
  create:
    - "docs/MIGRATION.md"
  modify:
    - "README.md"
  reference:
    - "scripts/migrations/001_actr_schema.sql"
    - "scripts/migrate.py"
    - "src/server.py"
    - "src/actr_scoring.py"
    - "src/forgetting.py"
    - "docs/ACT-R.md"
```

---

## Dependency Graph

```
ACT-R-00  (docs)           ----+
ACT-R-05  (config)         ----|--------------------+
ACT-R-01  (schema)         ----|----+               |
                                |    |               |
                                |    v               |
ACT-R-02  (scoring)  <---------+----+               |
                                |    |               |
                                |    v               |
ACT-R-03  (integration)  <-----+----+               |
                                |                    |
                                v                    |
ACT-R-04  (forgetting)  <------+                    |
                                |                    |
                                v                    |
ACT-R-06  (adaptive w)  <-- ACT-R-02               |
ACT-R-07  (tests)  <------- ACT-R-02, ACT-R-04     |
ACT-R-08  (MCP tool)  <---- ACT-R-04               |
                                |                    |
                                v                    v
ACT-R-09  (deployment)  <-- ALL PREVIOUS TASKS -----+
```

## Execution Order (recommended)

| Order | Task | Parallelizable with |
|-------|------|---------------------|
| 1 | ACT-R-00 | ACT-R-05 |
| 1 | ACT-R-05 | ACT-R-00 |
| 2 | ACT-R-01 | -- |
| 3 | ACT-R-02 | -- |
| 4 | ACT-R-03 | ACT-R-04, ACT-R-06 |
| 4 | ACT-R-04 | ACT-R-03, ACT-R-06 |
| 4 | ACT-R-06 | ACT-R-03, ACT-R-04 |
| 5 | ACT-R-07 | ACT-R-08 |
| 5 | ACT-R-08 | ACT-R-07 |
| 6 | ACT-R-09 | -- |
