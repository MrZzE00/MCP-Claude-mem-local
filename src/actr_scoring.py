"""
ACT-R Cognitive Memory Scoring Module

Implements the ACT-R activation formula for memory retrieval ranking:
    A(m) = B(m) + w * cosine_similarity + S(m) + epsilon

Based on Honda et al. (HAI '25, Jan 2026) - "Human-Like Remembering and
Forgetting in LLM Agents" and the ACT-R cognitive architecture (CMU).

Components:
    B(m) - Base-level activation: frequency + power-law decay
    w * cosine - Semantic similarity weighted by context
    S(m) - Spreading activation via shared tags
    epsilon - Gaussian noise for probabilistic variability
"""

import math
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ACTRConfig:
    """Configuration for ACT-R cognitive scoring parameters.

    Attributes:
        d: Decay rate for power-law forgetting (0.5 = standard ACT-R).
           Higher values = faster forgetting of old memories.
        w: Weight for cosine similarity in the activation formula.
           11.0 is optimal per Honda et al. simulations.
        sigma: Standard deviation of Gaussian noise (1.2 = standard ACT-R).
               0 = deterministic ranking.
        tau: Retrieval threshold. Memories with A(m) < tau are filtered out.
             -2.0 separates forgotten from dormant.
        S: Maximum associative strength for spreading activation.
        use_spreading: Enable tag-based spreading activation.
        use_noise: Enable Gaussian noise in activation computation.
        prefetch_limit: Number of candidates from SQL pre-filter.
        use_actr: Master switch for ACT-R scoring.
    """

    d: float = 0.5
    w: float = 11.0
    sigma: float = 1.2
    tau: float = -2.0
    S: float = 2.0
    use_spreading: bool = True
    use_noise: bool = True
    prefetch_limit: int = 50
    use_actr: bool = True

    @classmethod
    def from_env(cls) -> "ACTRConfig":
        """Load configuration from environment variables with defaults."""
        return cls(
            d=float(os.getenv("ACTR_DECAY_D", "0.5")),
            w=float(os.getenv("ACTR_WEIGHT_W", "11.0")),
            sigma=float(os.getenv("ACTR_NOISE_SIGMA", "1.2")),
            tau=float(os.getenv("ACTR_THRESHOLD_TAU", "-2.0")),
            S=float(os.getenv("ACTR_SPREADING_S", "2.0")),
            use_spreading=os.getenv("ACTR_USE_SPREADING", "true").lower() == "true",
            use_noise=os.getenv("ACTR_USE_NOISE", "true").lower() == "true",
            prefetch_limit=int(os.getenv("ACTR_PREFETCH_LIMIT", "50")),
            use_actr=os.getenv("USE_ACTR_SCORING", "true").lower() == "true",
        )


def compute_base_level(
    access_timestamps: list[datetime],
    created_at: datetime,
    d: float = 0.5,
) -> float:
    """Compute base-level activation B(m) using power-law decay.

    B(m) = ln(Sum_i (t_now - t_i)^(-d))

    Recent and frequently accessed memories get higher activation.
    If no access timestamps exist, falls back to created_at alone.

    Args:
        access_timestamps: List of timestamps when the memory was accessed.
        created_at: When the memory was originally created.
        d: Decay parameter (default 0.5 per ACT-R standard).

    Returns:
        Base-level activation score (higher = more active).
    """
    now = datetime.now(timezone.utc)

    timestamps = list(access_timestamps) if access_timestamps else []
    if not timestamps:
        timestamps = [created_at]

    total = 0.0
    for ts in timestamps:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta_seconds = max((now - ts).total_seconds(), 1.0)
        total += delta_seconds ** (-d)

    if total <= 0:
        return -10.0

    return math.log(total)


def compute_spreading_activation(
    memory_tags: list[str],
    query_tags: list[str],
    tag_fan_counts: dict[str, int],
    S: float = 2.0,
) -> float:
    """Compute spreading activation S(m) via shared tags.

    For each shared tag j between memory and query:
        Sji = S - ln(fan_j)
    where fan_j is the number of memories that have tag j.

    Tags with fewer memories (lower fan) provide stronger association.

    Args:
        memory_tags: Tags on the memory being scored.
        query_tags: Tags extracted from or associated with the query.
        tag_fan_counts: Dict mapping each tag to its total count across all memories.
        S: Maximum associative strength (default 2.0).

    Returns:
        Spreading activation score (0.0 if no shared tags).
    """
    if not memory_tags or not query_tags:
        return 0.0

    memory_set = set(t.lower() for t in memory_tags)
    query_set = set(t.lower() for t in query_tags)
    shared = memory_set & query_set

    if not shared:
        return 0.0

    W = 1.0 / max(len(query_set), 1)
    total = 0.0
    for tag in shared:
        fan = tag_fan_counts.get(tag.lower(), 1)
        sji = S - math.log(max(fan, 1))
        total += W * sji

    return total


def compute_noise(sigma: float = 1.2) -> float:
    """Compute Gaussian noise epsilon ~ N(0, sigma).

    Adds probabilistic variability to memory retrieval, preventing
    static ranking bias and simulating human recall variability.

    Args:
        sigma: Standard deviation (1.2 = standard ACT-R).

    Returns:
        A random noise value from the normal distribution.
    """
    if sigma <= 0:
        return 0.0
    return random.gauss(0, sigma)


def compute_activation(
    base_level: float,
    cosine_sim: float,
    spreading: float,
    noise: float,
    w: float = 11.0,
) -> float:
    """Compute total ACT-R activation A(m).

    A(m) = B(m) + w * cosine_similarity + S(m) + epsilon

    Args:
        base_level: B(m) from compute_base_level.
        cosine_sim: Cosine similarity between query and memory embeddings.
        spreading: S(m) from compute_spreading_activation.
        noise: epsilon from compute_noise.
        w: Weight for semantic similarity (default 11.0).

    Returns:
        Total activation score.
    """
    return base_level + w * cosine_sim + spreading + noise


# --- Query type classification and adaptive w ---

DEBUGGING_KEYWORDS = frozenset([
    "error", "bug", "fix", "debug", "exception", "traceback", "crash",
    "fail", "broken", "issue", "stack", "trace", "erreur", "probleme",
    "corrige", "repare",
])

ARCHITECTURE_KEYWORDS = frozenset([
    "design", "architecture", "pattern", "system", "schema", "structure",
    "module", "component", "interface", "abstraction", "conception",
    "refactor", "migration",
])


def classify_query_type(
    query: str,
    tags: list[str] | None = None,
    category: str | None = None,
) -> str:
    """Classify a query to determine the appropriate w weight.

    Categories:
        - 'debugging': error-related queries (privilege semantic precision)
        - 'architecture': design-related queries (balanced)
        - 'recurrent': frequently accessed patterns (privilege frequency)
        - 'general': default

    Args:
        query: The search query text.
        tags: Optional tags associated with the query.
        category: Optional category filter.

    Returns:
        Query type string: 'debugging' | 'architecture' | 'recurrent' | 'general'
    """
    words = set(query.lower().split())
    all_terms = words | set(t.lower() for t in (tags or []))

    if category in ("bugfix", "error_solution") or all_terms & DEBUGGING_KEYWORDS:
        return "debugging"

    if category in ("decision", "refactor") or all_terms & ARCHITECTURE_KEYWORDS:
        return "architecture"

    return "general"


def get_adaptive_w(query_type: str, base_w: float = 11.0) -> float:
    """Get adaptive semantic weight based on query type.

    - debugging: w * 1.5  (15-20) — privilege semantic precision
    - architecture: w * 1.0 (10-12) — balanced
    - recurrent: w * 0.6  (5-8) — privilege frequency/recency
    - general: w (unchanged)

    Args:
        query_type: Output from classify_query_type.
        base_w: Base semantic weight (default 11.0).

    Returns:
        Adjusted w value.
    """
    multipliers = {
        "debugging": 1.5,
        "architecture": 1.0,
        "recurrent": 0.6,
        "general": 1.0,
    }
    return base_w * multipliers.get(query_type, 1.0)


# --- Main scoring orchestrator ---


def score_and_rank_memories(
    rows: list[dict],
    query_tags: list[str] | None = None,
    tag_fan_counts: dict[str, int] | None = None,
    config: ACTRConfig | None = None,
    query: str = "",
    category: str | None = None,
) -> list[dict]:
    """Score and re-rank memories using ACT-R activation formula.

    This is the main orchestrator called after SQL pre-filtering.
    For each memory, computes A(m) = B(m) + w*cosine + S(m) + epsilon,
    filters by threshold tau, and returns sorted results.

    Args:
        rows: List of memory dicts from SQL query. Each must have:
              - 'sim': cosine similarity (float)
              - 'access_timestamps': list of datetime or None
              - 'created_at': datetime
              - 'tags': list of str or None
        query_tags: Tags extracted from the query context.
        tag_fan_counts: Dict of tag -> count across all memories.
        config: ACTRConfig instance (uses defaults if None).
        query: Original query text (for adaptive w).
        category: Category filter (for adaptive w).

    Returns:
        List of memory dicts sorted by activation (descending),
        each augmented with 'activation_score' key.
    """
    if config is None:
        config = ACTRConfig()

    if tag_fan_counts is None:
        tag_fan_counts = {}

    query_type = classify_query_type(query, query_tags, category)
    effective_w = get_adaptive_w(query_type, config.w)

    scored = []
    for row in rows:
        access_ts = row.get("access_timestamps") or []
        created_at = row.get("created_at", datetime.now(timezone.utc))
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        cosine_sim = float(row.get("sim", 0.0))
        memory_tags = row.get("tags") or []

        B = compute_base_level(access_ts, created_at, config.d)

        S_val = 0.0
        if config.use_spreading and query_tags:
            S_val = compute_spreading_activation(
                memory_tags, query_tags, tag_fan_counts, config.S
            )

        epsilon = compute_noise(config.sigma) if config.use_noise else 0.0

        activation = compute_activation(B, cosine_sim, S_val, epsilon, effective_w)

        if activation >= config.tau:
            entry = dict(row)
            entry["activation_score"] = activation
            entry["actr_components"] = {
                "base_level": B,
                "semantic": effective_w * cosine_sim,
                "spreading": S_val,
                "noise": epsilon,
            }
            scored.append(entry)

    scored.sort(key=lambda x: x["activation_score"], reverse=True)
    return scored
