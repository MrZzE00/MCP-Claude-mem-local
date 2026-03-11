"""
Tests for hybrid_search module (pure unit tests, no DB required).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hybrid_search import build_search_queries, reciprocal_rank_fusion


class TestReciprocalRankFusion:
    """Test RRF merging logic."""

    def test_disjoint_results(self):
        """Two lists with no overlap — all docs appear in output."""
        vec = [{"id": "a", "sim": 0.9}, {"id": "b", "sim": 0.8}]
        txt = [{"id": "c", "sim": 0.7, "trgm_sim": 0.3}, {"id": "d", "sim": 0.6, "trgm_sim": 0.2}]

        fused = reciprocal_rank_fusion(vec, txt)
        ids = [r["id"] for r in fused]

        assert len(fused) == 4
        assert set(ids) == {"a", "b", "c", "d"}
        # All have rrf_score
        assert all("rrf_score" in r for r in fused)

    def test_overlapping_results_vector_preferred(self):
        """Overlapping doc uses vector version (higher sim)."""
        vec = [{"id": "a", "sim": 0.95, "content": "vec-version"}]
        txt = [{"id": "a", "sim": 0.80, "trgm_sim": 0.4, "content": "txt-version"}]

        fused = reciprocal_rank_fusion(vec, txt)

        assert len(fused) == 1
        assert fused[0]["content"] == "vec-version"
        # RRF score should be sum of both ranks
        expected_rrf = 1.0 / (60 + 0) + 1.0 / (60 + 0)
        assert abs(fused[0]["rrf_score"] - expected_rrf) < 1e-9

    def test_empty_inputs(self):
        """Both empty — returns empty list."""
        assert reciprocal_rank_fusion([], []) == []

    def test_one_empty(self):
        """One list empty — returns the other."""
        vec = [{"id": "x", "sim": 0.5}]
        fused = reciprocal_rank_fusion(vec, [])

        assert len(fused) == 1
        assert fused[0]["id"] == "x"

    def test_ordering_by_rrf_score(self):
        """Doc appearing in both lists ranks higher than single-list docs."""
        vec = [{"id": "shared", "sim": 0.7}, {"id": "vec-only", "sim": 0.9}]
        txt = [{"id": "shared", "sim": 0.7, "trgm_sim": 0.5}, {"id": "txt-only", "sim": 0.3, "trgm_sim": 0.6}]

        fused = reciprocal_rank_fusion(vec, txt)

        # "shared" appears in both lists so should have highest RRF
        assert fused[0]["id"] == "shared"

    def test_custom_k(self):
        """Custom k parameter changes scores but not relative ordering."""
        vec = [{"id": "a", "sim": 0.9}]
        txt = [{"id": "a", "sim": 0.9, "trgm_sim": 0.5}]

        fused_k10 = reciprocal_rank_fusion(vec, txt, k=10)
        fused_k100 = reciprocal_rank_fusion(vec, txt, k=100)

        # Higher k = lower scores
        assert fused_k10[0]["rrf_score"] > fused_k100[0]["rrf_score"]


class TestBuildSearchQueries:
    """Test SQL query construction."""

    def test_no_filters(self):
        """Basic query with no optional filters."""
        vec_sql, vec_p, trgm_sql, trgm_p = build_search_queries(
            embedding_str="[0.1,0.2]",
            query_text="test query",
            min_similarity=0.3,
            prefetch=50,
        )

        assert "embedding <=>" in vec_sql
        assert "LIMIT $3" in vec_sql
        assert vec_p == ["[0.1,0.2]", 0.3, 50]

        assert "similarity(" in trgm_sql
        assert "LIMIT $3" in trgm_sql
        assert trgm_p[0] == "test query"
        assert trgm_p[1] == "[0.1,0.2]"
        assert trgm_p[2] == 50

    def test_with_category(self):
        """Category filter appears in both queries."""
        vec_sql, vec_p, trgm_sql, trgm_p = build_search_queries(
            embedding_str="[0.1]",
            query_text="test",
            category="bugfix",
        )

        assert "category = $4" in vec_sql
        assert "bugfix" in vec_p

        assert "category = $4" in trgm_sql
        assert "bugfix" in trgm_p

    def test_with_tags(self):
        """Tags filter uses @> (array contains)."""
        vec_sql, vec_p, trgm_sql, trgm_p = build_search_queries(
            embedding_str="[0.1]",
            query_text="test",
            tags=["setup", "mac"],
        )

        assert "tags @>" in vec_sql
        assert ["setup", "mac"] in vec_p

        assert "tags @>" in trgm_sql
        assert ["setup", "mac"] in trgm_p

    def test_with_project(self):
        """Project filter uses = operator."""
        vec_sql, vec_p, trgm_sql, trgm_p = build_search_queries(
            embedding_str="[0.1]",
            query_text="test",
            project="project-m4",
        )

        assert "project_context =" in vec_sql
        assert "project-m4" in vec_p

        assert "project_context =" in trgm_sql
        assert "project-m4" in trgm_p

    def test_all_filters_combined(self):
        """All filters present simultaneously."""
        vec_sql, vec_p, trgm_sql, trgm_p = build_search_queries(
            embedding_str="[0.1]",
            query_text="test",
            category="decision",
            tags=["arch"],
            project="proj-x",
            include_forgotten=False,
        )

        # Should have base params (3) + category + tags + project
        assert len(vec_p) == 6
        assert "category" in vec_sql
        assert "tags @>" in vec_sql
        assert "project_context" in vec_sql
        assert "memory_status" in vec_sql

    def test_include_forgotten(self):
        """When include_forgotten=True, no status filter in WHERE clause."""
        vec_sql, vec_p, trgm_sql, trgm_p = build_search_queries(
            embedding_str="[0.1]",
            query_text="test",
            include_forgotten=True,
        )

        # memory_status appears in SELECT but should NOT appear in WHERE/AND filter
        assert "memory_status !=" not in vec_sql
        assert "memory_status !=" not in trgm_sql
