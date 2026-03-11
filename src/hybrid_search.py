"""
Hybrid Search Module — Vector + Trigram with Reciprocal Rank Fusion (RRF)

Combines pgvector cosine similarity with pg_trgm trigram matching,
then fuses results using RRF to surface memories that either method
alone would miss (especially technical/structured content with poor
embedding quality).
"""

import logging

logger = logging.getLogger("claude-memory-local")


def build_search_queries(
    embedding_str: str,
    query_text: str,
    min_similarity: float = 0.3,
    prefetch: int = 50,
    category: str | None = None,
    tags: list[str] | None = None,
    project: str | None = None,
    include_forgotten: bool = False,
) -> tuple[str, list, str, list]:
    """Build parallel SQL queries for vector and trigram search.

    Both queries share the same optional filters (category, tags, project, status).
    The trigram query also computes cosine similarity so ACT-R can score all candidates.

    Returns:
        (vector_sql, vector_params, trigram_sql, trigram_params)
    """
    # --- Shared WHERE clause builder ---
    def _build_filters(param_offset: int) -> tuple[str, list]:
        """Build dynamic WHERE clauses starting at $param_offset."""
        clauses = []
        params = []

        if not include_forgotten:
            clauses.append("(memory_status IS NULL OR memory_status != 'forgotten')")

        if category:
            params.append(category)
            clauses.append(f"category = ${param_offset + len(params)}")

        if tags:
            params.append(tags)
            clauses.append(f"tags @> ${param_offset + len(params)}")

        if project:
            params.append(project)
            clauses.append(f"project_context = ${param_offset + len(params)}")

        where = ""
        if clauses:
            where = "AND " + " AND ".join(clauses)

        return where, params

    # --- Vector query ---
    vec_where, vec_filter_params = _build_filters(param_offset=3)
    vector_sql = f"""
        SELECT
            id, content, summary, category, tags,
            importance_score, created_at,
            access_timestamps, memory_status,
            project_context,
            1 - (embedding <=> $1::vector) as sim
        FROM memories
        WHERE 1 - (embedding <=> $1::vector) >= $2
          {vec_where}
        ORDER BY (1 - (embedding <=> $1::vector)) DESC
        LIMIT $3
    """
    vector_params = [embedding_str, min_similarity, prefetch] + vec_filter_params

    # --- Trigram query ---
    # $1 = query_text, $2 = embedding_str, $3 = limit
    trgm_where, trgm_filter_params = _build_filters(param_offset=3)
    trigram_sql = f"""
        SELECT
            id, content, summary, category, tags,
            importance_score, created_at,
            access_timestamps, memory_status,
            project_context,
            similarity(content || ' ' || COALESCE(summary, ''), $1) as trgm_sim,
            1 - (embedding <=> $2::vector) as sim
        FROM memories
        WHERE similarity(content || ' ' || COALESCE(summary, ''), $1) >= 0.05
          {trgm_where}
        ORDER BY similarity(content || ' ' || COALESCE(summary, ''), $1) DESC
        LIMIT $3
    """
    trigram_params = [query_text, embedding_str, prefetch] + trgm_filter_params

    return vector_sql, vector_params, trigram_sql, trigram_params


def reciprocal_rank_fusion(
    vector_results: list[dict],
    text_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """Fuse two ranked lists using Reciprocal Rank Fusion.

    RRF(d) = sum_r  1 / (k + rank_r(d))

    For documents appearing in both lists, the vector version is preferred
    (it has the canonical 'sim' value for ACT-R scoring).

    Args:
        vector_results: Ranked results from vector search.
        text_results: Ranked results from trigram search.
        k: RRF constant (default 60, standard value).

    Returns:
        Fused list sorted by RRF score descending, each dict augmented
        with 'rrf_score' key.
    """
    rrf_scores: dict[str, float] = {}
    doc_store: dict[str, dict] = {}
    doc_source: dict[str, str] = {}

    # Score vector results
    for rank, row in enumerate(vector_results):
        doc_id = str(row["id"])
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)
        doc_store[doc_id] = row
        doc_source[doc_id] = "vector"

    # Score text results
    for rank, row in enumerate(text_results):
        doc_id = str(row["id"])
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)
        # Only store if not already from vector (vector preferred)
        if doc_id not in doc_store:
            doc_store[doc_id] = row
            doc_source[doc_id] = "text"

    # Build fused list
    fused = []
    for doc_id, score in rrf_scores.items():
        entry = dict(doc_store[doc_id])
        entry["rrf_score"] = score
        fused.append(entry)

    fused.sort(key=lambda x: x["rrf_score"], reverse=True)
    return fused
