# ACT-R Integration -- Strategic Impact Analysis

> **Project**: MCP-Claude-mem-local
> **Scope**: Replacement of naive scoring with ACT-R cognitive memory model
> **Reference**: [docs/ACT-R.md](./ACT-R.md) -- Formulas, parameters, and competitive landscape
> **Date**: 2026-02-22

---

## Table of Contents

1. [Limite actuelle -- Analyse du scoring naif](#a-limite-actuelle--analyse-du-scoring-naif)
2. [Pourquoi -- Justification scientifique](#b-pourquoi--justification-scientifique)
3. [Comment -- Architecture technique](#c-comment--architecture-technique)
4. [Valeur ajoutee -- Differenciation](#d-valeur-ajoutee--differenciation)
5. [Impact -- Mesurable](#e-impact--mesurable)

---

## a) Limite actuelle -- Analyse du scoring naif

### Current ranking formula

The existing `retrieve_memories` implementation in `src/server.py` ranks results
using a single expression:

```
ORDER BY (1 - (embedding <=> query_embedding)) * importance_score DESC
```

This reduces to:

```
final_score = cosine_similarity(memory, query) * importance_score
```

Where `cosine_similarity` is computed by pgvector via the `<=>` cosine distance
operator, and `importance_score` is a static float between 0.0 and 1.0 set at
memory creation time.

### What the database tracks but never uses

The `memories` table (defined in `scripts/init.sql`) contains two columns that
are updated on every retrieval but play no role in ranking:

| Column | Type | Updated by | Used in ORDER BY |
|--------|------|------------|------------------|
| `access_count` | INTEGER | `update_last_accessed()` trigger | No |
| `last_accessed_at` | TIMESTAMP | `update_last_accessed()` trigger | No |

The trigger increments `access_count` and refreshes `last_accessed_at` on every
access, but neither value influences which memories are returned or in what order.

### Five structural deficiencies

**1. No temporal decay.**
A memory stored six months ago and never accessed since receives the same ranking
as one accessed yesterday, provided their cosine similarity and importance are
equal. The system has no concept of recency beyond the static `created_at`
timestamp. Real memory systems -- both biological and practical -- require that
older, unused information gradually loses salience.

**2. No frequency activation.**
A memory retrieved 100 times is treated identically to one retrieved once. The
`access_count` column exists but is excluded from the ranking formula. In
practice, frequently accessed memories are more likely to be relevant in the
future -- a pattern formalized by the ACT-R base-level learning equation.

**3. No associative context.**
Tags are stored as a `TEXT[]` array and used only for optional pre-filtering
(`WHERE tags @> ARRAY[...]`). They do not contribute to the relevance score.
Two memories with identical cosine similarity but different tag relationships to
the query receive identical scores. The associative structure captured by tags
is discarded at ranking time.

**4. No variability.**
The ranking is fully deterministic: given the same query embedding and the same
database state, the same memories appear in the same order every time. This
creates a static ranking bias where borderline-relevant memories with slightly
lower cosine scores are permanently buried, even when they might be contextually
appropriate. Human recall includes a stochastic component that prevents this
rigidity.

**5. Equivalent to a simple weighted vector search.**
After removing the unused columns and the optional category/project filters,
the entire retrieval pipeline reduces to:

```sql
SELECT * FROM memories
ORDER BY cosine_similarity * importance_score DESC
LIMIT :max_results
```

This is functionally equivalent to a weighted vector nearest-neighbor search.
It ignores the temporal, frequency, and contextual signals that distinguish a
memory system from a search index.

---

## b) Pourquoi -- Justification scientifique

### Reference study

**"Human-Like Remembering and Forgetting in LLM Agents"**
Honda, Fujita, Zempo, Fukushima
HAI '25, January 2026
Source: https://dl.acm.org/doi/10.1145/3765766.3765803

This paper demonstrates that LLM agents equipped with ACT-R-based memory
scoring significantly outperform those using simple recency or vector-similarity
retrieval on realistic dialogue tasks. The key finding: composite scoring that
models human forgetting curves produces more contextually appropriate recall
than any single-signal approach.

### The ACT-R cognitive architecture

ACT-R (Adaptive Control of Thought -- Rational) is a cognitive architecture
developed at Carnegie Mellon University over more than 40 years of research.
Its declarative memory module models how humans store, retrieve, and forget
information using mathematically precise activation equations.

The core activation formula (see [docs/ACT-R.md](./ACT-R.md) for full notation):

```
A(m) = B(m) + w * cosine_similarity + S(m) + epsilon
```

| Component | Formula | Models |
|-----------|---------|--------|
| B(m) | `ln(sum((t - ti)^-d))` | Frequency + power-law recency decay |
| w * cosine | Weighted semantic similarity | Content relevance |
| S(m) | `sum_j(Wj * (S - ln(fan_j)))` | Associative context via shared tags |
| epsilon | `N(0, sigma)` | Probabilistic variability in recall |

### Why cosine similarity alone is insufficient

The human brain does not retrieve information by computing vector distances.
Human memory combines four independent signals:

1. **Frequency**: information accessed repeatedly becomes easier to recall.
   This is the power-law practice effect formalized in B(m).
2. **Recency**: recent information is more available than old information.
   This is the temporal decay component of B(m), where activation decreases
   as a power function of time since last access.
3. **Context**: related concepts prime each other during retrieval. Thinking
   about "PostgreSQL" activates associated concepts like "indexing", "migration",
   and "pgvector". This is spreading activation S(m).
4. **Variability**: recall is probabilistic, not deterministic. The same cue
   does not always retrieve the same memory. This is the noise term epsilon,
   which prevents static ranking bias.

A system that uses only cosine similarity captures none of these effects. Adding
`importance_score` as a static multiplier adds a fifth signal (user-assigned
salience) but does not compensate for the missing four.

### Competitors and their limitations

The competitive landscape (detailed in [docs/ACT-R.md](./ACT-R.md)) reveals
that no existing system combines all four cognitive signals in a local-first
architecture:

| System | Approach | Missing signals |
|--------|----------|-----------------|
| **MemoryBank** (AAAI 2024) | Ebbinghaus forgetting curve `R=e^(-t/S)` | No frequency, no spreading, no noise |
| **A-MEM** (NeurIPS 2025) | Zettelkasten auto-organization | No mathematical activation scoring |
| **Zep/Graphiti** | Knowledge graph + BM25 + semantic | No forgetting model, no activation |
| **Mem0** | Decay + confidence scoring | Depends on external LLM (gpt-4.1-nano), not local-first |
| **LangMem** | LLM-as-judge consolidation | No mathematical scoring at all |
| **MemGPT/Letta** | OS-like two-tier architecture | No cognitive activation model |

### Supporting surveys

- "Memory in the Age of AI Agents" (arXiv:2512.13564, January 2026) --
  comprehensive lifecycle taxonomy: Formation, Evolution, Retrieval
- "Cognitive Memory in Large Language Models" (arXiv:2504.02441, April 2025) --
  theoretical foundations for cognitive memory in LLM systems

---

## c) Comment -- Architecture technique

### Two-stage retrieval pipeline

The ACT-R integration preserves the existing PostgreSQL-based retrieval as a
fast pre-filter and adds a Python re-ranking stage. This design avoids
implementing complex mathematical functions in SQL while maintaining query
performance.

```
Query
  |
  v
[Stage 1: SQL Pre-filter]
  - pgvector cosine similarity (HNSW index)
  - WHERE memory_status != 'forgotten'
  - Optional category/project filters
  - LIMIT 50 candidates
  |
  v
[Stage 2: Python ACT-R Re-ranking]
  - compute_base_level() for each candidate
  - compute_spreading_activation() using query tags
  - Apply weighted cosine: w * cosine_sim
  - Add Gaussian noise: epsilon ~ N(0, sigma)
  - Composite: A(m) = B(m) + w*cosine + S(m) + epsilon
  - Sort by A(m) descending
  - Return top max_results
  |
  v
[Post-retrieval]
  - Append current timestamp to access_timestamps[]
  - Return results (unchanged response format)
```

### Four scoring components

Each component is implemented as an independent, testable function in
`src/actr_scoring.py` (see [docs/ACT-R.md](./ACT-R.md) for mathematical
definitions):

**B(m) -- Base-level activation.**
Computes the log-sum of power-law decayed access times. Memories accessed
frequently and recently receive higher base-level scores. The `access_timestamps`
array replaces the scalar `access_count` to enable precise temporal computation.

**w * cosine -- Weighted semantic similarity.**
The cosine similarity from pgvector is multiplied by a configurable weight w
(default: 11.0, from Honda et al. optimization). This preserves the existing
semantic signal while allowing it to be balanced against temporal and contextual
factors.

**S(m) -- Spreading activation.**
Tags shared between the query context and the memory contribute positive
activation, diluted by the "fan" (number of memories sharing each tag). A tag
shared by 3 memories provides more activation than one shared by 300. This
formalizes the intuition that specific, targeted tags are more informative than
generic ones.

**epsilon -- Gaussian noise.**
A random sample from N(0, sigma) with sigma=1.2 (configurable). This prevents
deterministic ranking rigidity and allows borderline memories to surface
occasionally, matching the probabilistic nature of human recall.

### Strategic forgetting engine

The forgetting engine (`src/forgetting.py`) manages memory lifecycle through
three states:

```
                  A > 0              -2 < A <= 0           A <= -2
Created  --->  [ ACTIVE ]  --->  [ DORMANT ]  --->  [ FORGOTTEN ]
                    ^                  |                     |
                    |                  |                     |
                    +------------------+                     |
                    (re-access raises activation)            |
                    +----------------------------------------+
                    (explicit re-access can resurrect)
```

Key design decisions:

- **Forgotten does not mean deleted.** The `memory_status` column changes to
  'forgotten' but the row remains in the database. A direct query with explicit
  status filters can retrieve forgotten memories.
- **Thresholds are configurable.** The activation boundaries (0 for
  active/dormant, -2 for dormant/forgotten) are exposed as environment variables.
- **Resurrection is possible.** If a forgotten memory is explicitly retrieved
  or referenced, its `access_timestamps` array receives a new entry, raising
  its base-level activation and potentially transitioning it back to dormant
  or active.

### Backward-compatible configuration

All ACT-R features are gated behind the `USE_ACTR_SCORING` environment variable
(default: `false`). When disabled:

- `retrieve_memories` uses the original `cosine_similarity * importance_score`
  ranking.
- The `memory_forgetting_cycle` MCP tool returns an informative message stating
  that ACT-R scoring is not enabled.
- The `memory_stats` tool reports `actr_enabled: false` without additional
  indicators.
- No new columns are queried or updated during retrieval.

This ensures that the migration can be applied to the database schema without
changing runtime behavior until the operator explicitly enables it.

### Safe migration of existing data

The project database contains 1,554+ memories in production. The migration
strategy (detailed in ACT-R-01):

1. Add new columns with safe defaults (`access_timestamps = '{}'`,
   `memory_status = 'active'`, `actr_activation = NULL`).
2. Convert existing `access_count` values into synthetic timestamps, evenly
   distributed between `created_at` and `last_accessed_at`, preserving the
   statistical signal of past usage.
3. All existing memories begin as 'active' until the first forgetting cycle
   computes their actual activation scores.
4. The migration is idempotent: running it twice produces no errors or
   duplicate data.

---

## d) Valeur ajoutee -- Differenciation

### Only local-first MCP system with composite cognitive scoring

No other MCP memory server -- commercial or open-source -- combines a
mathematically validated cognitive model (ACT-R) with a fully local, air-gapped
architecture. Existing alternatives either require external API calls (Mem0,
LangMem), lack mathematical scoring (MemGPT/Letta, A-MEM), or implement
simplified single-factor decay (MemoryBank). MCP-Claude-mem-local with ACT-R
integration occupies a unique position in the ecosystem.

### Recall improves with usage

Memories that are retrieved frequently accumulate timestamps in the
`access_timestamps` array, raising their base-level activation B(m). Over time,
the system naturally surfaces the memories that have proven most useful to the
developer. A pattern explanation retrieved during every refactoring session will
rank higher than one retrieved once six months ago, even if their cosine
similarities to a new query are identical. The system learns which memories
matter through usage, not through manual curation.

### Natural forgetting of obsolete memories

Memories that are never accessed experience power-law activation decay. Their
B(m) value decreases over time, eventually crossing the dormant and forgotten
thresholds. This removes stale information from default results without
requiring the user to manually delete or archive anything. A bugfix for a
dependency version that was upgraded months ago will gradually fade from active
recall. If the user needs it again, an explicit search can still find it.

### Tag contextualization through spreading activation

Tags transition from passive metadata to active scoring signals. When a query
context includes tags like "supabase" and "auth", memories tagged with those
terms receive a spreading activation bonus proportional to the specificity of
the tags. A memory tagged with a rare, specific tag like "rls-policy-bug" gains
more activation from a matching query than one tagged with a common tag like
"javascript". This rewards precise tagging and makes the tag system functionally
valuable beyond filtering.

### Probabilistic variability prevents static ranking bias

The Gaussian noise component epsilon ensures that memories near the ranking
boundary are not permanently ordered. On two consecutive queries with identical
text, the noise term may reorder two memories with similar activation scores.
This matches human recall behavior (the same prompt does not always trigger
exactly the same memory) and ensures that borderline-relevant memories are
occasionally surfaced rather than perpetually hidden behind a fixed ranking.

### Adaptive semantic weight by query type

The optional adaptive w feature (ACT-R-06) adjusts the balance between semantic
similarity and temporal/frequency signals based on query classification:

- **Debugging queries** (w increased): favor exact semantic match because
  error-specific memories must be precisely relevant.
- **Architecture queries** (w balanced): equal weight to semantics and
  frequency because architectural decisions are both content-specific and
  usage-validated.
- **Recurrent queries** (w decreased): favor frequency because recurring
  questions indicate operational patterns where the most-accessed memory is
  typically the most useful.

This context sensitivity is not available in any competing system.

---

## e) Impact -- Mesurable

### Recall relevance

Multi-factor scoring (frequency + recency + context + noise + semantics)
captures information signals that cosine similarity alone discards. A memory
that is semantically similar to a query but has not been accessed in six months
will rank lower than one with slightly less cosine similarity but recent,
frequent access. This aligns ranking with actual utility rather than pure
textual overlap.

**Measurement**: compare mean reciprocal rank (MRR) of user-selected results
under the old and new scoring models over a 30-day evaluation period.

### Noise reduction

Forgotten memories (activation <= -2) are excluded from the default SQL
pre-filter. As the database grows beyond its current 1,554 memories, the
forgetting engine progressively removes obsolete entries from the candidate
pool. This reduces the number of irrelevant results returned and improves
signal-to-noise ratio without manual cleanup.

**Measurement**: track the ratio of active to total memories over time, and
monitor the percentage of retrieved results that are subsequently accessed
again (a proxy for relevance).

### Personalization through usage patterns

The base-level activation function B(m) creates an implicit user profile
through access patterns. Developers who frequently retrieve memories about
"authentication" will find those memories surface more readily in ambiguous
queries. This personalization happens without explicit profiling or preference
configuration -- it emerges naturally from the mathematical properties of the
power-law decay function.

**Measurement**: compare retrieval diversity and user satisfaction (click-through
on first result) between fixed-ranking and ACT-R-ranked systems.

### Performance characteristics

The two-stage architecture ensures no performance regression:

- **Stage 1** (SQL): leverages the existing HNSW index with an increased limit
  (50 vs current max_results). Query time remains O(log n) via approximate
  nearest neighbor search. The additional WHERE clause on `memory_status`
  reduces the candidate set.
- **Stage 2** (Python): re-ranks at most 50 candidates. Each activation
  computation involves arithmetic on small arrays (access_timestamps typically
  < 100 entries). Expected re-ranking time: < 10ms for 50 candidates.
- **Total**: the additional latency is bounded by the Python re-ranking of a
  small candidate set. For the current database size (1,554 memories), the
  overhead is negligible.

**Measurement**: instrument Stage 1 and Stage 2 separately to track p50 and p99
latency under production load.

### Community differentiation

For the open-source project on GitHub, ACT-R integration provides a concrete,
research-backed feature that distinguishes MCP-Claude-mem-local from
alternatives. The combination of cognitive science foundations (40+ years of
CMU research), a peer-reviewed reference implementation (Honda et al., HAI '25),
and a practical local-first architecture creates a compelling narrative for
adoption. No competing project offers this combination.

**Measurement**: track GitHub stars, forks, and contributor growth before and
after the ACT-R release. Monitor issue discussions referencing the cognitive
scoring feature.

### Research contribution

The implementation constitutes a concrete, production-tested application of the
ACT-R declarative memory model to LLM agent memory management. This bridges
the gap between cognitive science theory (CMU's ACT-R architecture) and
practical software engineering (MCP-based developer tools). The codebase,
configuration parameters, and performance measurements can serve as a reference
for future research on cognitive memory in AI systems.

**Measurement**: document parameter choices (d, w, sigma, thresholds) and their
empirical behavior over time. Publish findings as the system accumulates
production usage data.

---

## References

- Honda, Fujita, Zempo, Fukushima. "Human-Like Remembering and Forgetting in
  LLM Agents." HAI '25, January 2026.
  https://dl.acm.org/doi/10.1145/3765766.3765803
- Anderson, J.R. et al. "An Integrated Theory of the Mind." Psychological
  Review 111(4), 2004. (ACT-R foundational reference)
- "Memory in the Age of AI Agents." arXiv:2512.13564, January 2026.
- "Cognitive Memory in Large Language Models." arXiv:2504.02441, April 2025.
- PyACTUp: Python implementation of ACT-R declarative memory. DDM Lab, CMU.
  https://pypi.org/project/pyactup/
- Project formulas and competitive analysis: [docs/ACT-R.md](./ACT-R.md)
