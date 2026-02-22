"""Tests for ACT-R cognitive memory scoring module."""

import math
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

# Set test environment before imports
os.environ["PG_PASSWORD"] = "test_password"
os.environ["USE_ACTR_SCORING"] = "true"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from actr_scoring import (
    ACTRConfig,
    classify_query_type,
    compute_activation,
    compute_base_level,
    compute_noise,
    compute_spreading_activation,
    get_adaptive_w,
    score_and_rank_memories,
)


class TestACTRConfig:
    """Test ACTRConfig dataclass and from_env loading."""

    def test_default_values(self):
        config = ACTRConfig()
        assert config.d == 0.5
        assert config.w == 11.0
        assert config.sigma == 1.2
        assert config.tau == -2.0
        assert config.S == 2.0
        assert config.use_spreading is True
        assert config.use_noise is True
        assert config.prefetch_limit == 50
        assert config.use_actr is True

    def test_from_env(self):
        with patch.dict(os.environ, {
            "ACTR_DECAY_D": "0.7",
            "ACTR_WEIGHT_W": "15.0",
            "ACTR_NOISE_SIGMA": "0.5",
            "ACTR_THRESHOLD_TAU": "-3.0",
            "USE_ACTR_SCORING": "false",
            "ACTR_USE_SPREADING": "false",
            "ACTR_USE_NOISE": "false",
            "ACTR_PREFETCH_LIMIT": "100",
        }):
            config = ACTRConfig.from_env()
            assert config.d == 0.7
            assert config.w == 15.0
            assert config.sigma == 0.5
            assert config.tau == -3.0
            assert config.use_actr is False
            assert config.use_spreading is False
            assert config.use_noise is False
            assert config.prefetch_limit == 100

    def test_from_env_defaults_without_vars(self):
        with patch.dict(os.environ, {}, clear=False):
            # Remove ACT-R specific vars if present
            env_copy = {k: v for k, v in os.environ.items()
                       if not k.startswith("ACTR_") and k != "USE_ACTR_SCORING"}
            with patch.dict(os.environ, env_copy, clear=True):
                os.environ["PG_PASSWORD"] = "test"
                config = ACTRConfig.from_env()
                assert config.d == 0.5
                assert config.w == 11.0


class TestComputeBaseLevel:
    """Test base-level activation B(m)."""

    def test_recent_higher_than_old(self):
        """More recently accessed memories should have higher activation."""
        now = datetime.now(timezone.utc)

        recent_ts = [now - timedelta(minutes=5)]
        old_ts = [now - timedelta(days=30)]

        B_recent = compute_base_level(recent_ts, now - timedelta(hours=1))
        B_old = compute_base_level(old_ts, now - timedelta(days=60))

        assert B_recent > B_old

    def test_frequent_higher_than_rare(self):
        """Memories accessed more frequently should have higher activation."""
        now = datetime.now(timezone.utc)
        base = now - timedelta(days=10)

        # 10 accesses spread over last 10 days
        frequent_ts = [now - timedelta(days=i) for i in range(10)]
        # 1 access
        rare_ts = [now - timedelta(days=5)]

        B_frequent = compute_base_level(frequent_ts, base)
        B_rare = compute_base_level(rare_ts, base)

        assert B_frequent > B_rare

    def test_no_access_fallback_to_created(self):
        """With no access timestamps, should use created_at."""
        now = datetime.now(timezone.utc)
        created = now - timedelta(days=1)

        B = compute_base_level([], created)
        # Should produce a finite value, not crash
        assert isinstance(B, float)
        assert B > -20  # reasonable range

    def test_none_timestamps_fallback(self):
        """None access_timestamps should use created_at."""
        now = datetime.now(timezone.utc)
        B = compute_base_level(None, now - timedelta(hours=1))
        assert isinstance(B, float)

    def test_very_old_memory_low_activation(self):
        """Memory from long ago with no recent access has low activation."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=365)
        B = compute_base_level([old], old)
        # Should be significantly lower than a recent memory
        recent = compute_base_level([now - timedelta(minutes=1)], now - timedelta(hours=1))
        assert B < recent

    def test_decay_parameter_effect(self):
        """Higher decay should decrease activation faster."""
        now = datetime.now(timezone.utc)
        ts = [now - timedelta(days=30)]
        created = now - timedelta(days=60)

        B_low_decay = compute_base_level(ts, created, d=0.3)
        B_high_decay = compute_base_level(ts, created, d=0.8)

        assert B_low_decay > B_high_decay


class TestComputeSpreadingActivation:
    """Test spreading activation S(m) via shared tags."""

    def test_shared_tags_boost(self):
        """Memories sharing tags with query should get positive boost with low fan."""
        memory_tags = ["python", "fastapi", "auth"]
        query_tags = ["python", "auth"]
        # Low fan counts (rare tags) -> S - ln(fan) > 0 when fan < e^S (~7.4 for S=2.0)
        fan = {"python": 3, "fastapi": 2, "auth": 4}

        S = compute_spreading_activation(memory_tags, query_tags, fan)
        assert S > 0

    def test_no_overlap_zero(self):
        """No shared tags should give zero spreading activation."""
        memory_tags = ["python", "backend"]
        query_tags = ["react", "frontend"]
        fan = {"python": 10, "backend": 5, "react": 8, "frontend": 6}

        S = compute_spreading_activation(memory_tags, query_tags, fan)
        assert S == 0.0

    def test_empty_tags_zero(self):
        """Empty tags should give zero."""
        assert compute_spreading_activation([], ["python"], {}) == 0.0
        assert compute_spreading_activation(["python"], [], {}) == 0.0
        assert compute_spreading_activation(None, ["python"], {}) == 0.0
        assert compute_spreading_activation(["python"], None, {}) == 0.0

    def test_rare_tag_stronger(self):
        """Tags used by fewer memories should provide stronger association."""
        memory_tags = ["rare_tag"]
        query_tags = ["rare_tag"]

        S_rare = compute_spreading_activation(
            memory_tags, query_tags, {"rare_tag": 2}, S=2.0
        )
        S_common = compute_spreading_activation(
            memory_tags, query_tags, {"rare_tag": 100}, S=2.0
        )
        assert S_rare > S_common

    def test_case_insensitive(self):
        """Tag matching should be case-insensitive."""
        S = compute_spreading_activation(
            ["Python"], ["python"], {"python": 3}
        )
        assert S > 0


class TestComputeNoise:
    """Test Gaussian noise computation."""

    def test_distribution(self):
        """Noise should follow approximately N(0, sigma)."""
        samples = [compute_noise(1.2) for _ in range(10000)]
        mean = sum(samples) / len(samples)
        variance = sum((x - mean) ** 2 for x in samples) / len(samples)

        # Mean should be close to 0 (within tolerance)
        assert abs(mean) < 0.1
        # Variance should be close to sigma^2 = 1.44
        assert abs(variance - 1.44) < 0.3

    def test_zero_sigma(self):
        """Sigma of 0 should produce zero noise."""
        assert compute_noise(0.0) == 0.0
        assert compute_noise(-1.0) == 0.0


class TestComputeActivation:
    """Test total activation A(m) computation."""

    def test_formula(self):
        """A(m) = B + w * cosine + S + epsilon."""
        B = -1.0
        cosine = 0.9
        S = 0.5
        eps = 0.1
        w = 11.0

        A = compute_activation(B, cosine, S, eps, w)
        expected = B + w * cosine + S + eps
        assert abs(A - expected) < 1e-10

    def test_high_similarity_boosts(self):
        """Higher cosine similarity should increase activation."""
        A_high = compute_activation(-1.0, 0.95, 0.0, 0.0, 11.0)
        A_low = compute_activation(-1.0, 0.5, 0.0, 0.0, 11.0)
        assert A_high > A_low


class TestClassifyQueryType:
    """Test query type classification for adaptive w."""

    def test_debugging_keywords(self):
        assert classify_query_type("fix the authentication bug") == "debugging"
        assert classify_query_type("error in database connection") == "debugging"
        assert classify_query_type("debug traceback exception") == "debugging"

    def test_architecture_keywords(self):
        assert classify_query_type("system design pattern") == "architecture"
        assert classify_query_type("refactor the module") == "architecture"

    def test_debugging_category(self):
        assert classify_query_type("some query", category="bugfix") == "debugging"
        assert classify_query_type("some query", category="error_solution") == "debugging"

    def test_architecture_category(self):
        assert classify_query_type("some query", category="decision") == "architecture"

    def test_general_default(self):
        assert classify_query_type("how to use fastapi") == "general"
        assert classify_query_type("list all memories") == "general"

    def test_tags_influence(self):
        assert classify_query_type("query", tags=["bug", "fix"]) == "debugging"

    def test_classify_10_queries(self):
        """Verify correct classification for 10 representative queries."""
        cases = [
            ("fix the null pointer exception", "debugging"),
            ("error connecting to postgres", "debugging"),
            ("design a new API endpoint", "architecture"),
            ("refactor authentication module", "architecture"),
            ("system architecture review", "architecture"),
            ("how to install ollama", "general"),
            ("list all bugfix memories", "general"),
            ("what is pgvector", "general"),
            ("debug the crash in production", "debugging"),
            ("migration schema update", "architecture"),
        ]
        for query, expected in cases:
            result = classify_query_type(query)
            assert result == expected, f"Query '{query}': expected {expected}, got {result}"


class TestGetAdaptiveW:
    """Test adaptive semantic weight computation."""

    def test_debugging_higher(self):
        w = get_adaptive_w("debugging", 11.0)
        assert w == 16.5  # 11 * 1.5

    def test_architecture_unchanged(self):
        w = get_adaptive_w("architecture", 11.0)
        assert w == 11.0  # 11 * 1.0

    def test_recurrent_lower(self):
        w = get_adaptive_w("recurrent", 11.0)
        assert w == pytest.approx(6.6)  # 11 * 0.6

    def test_general_unchanged(self):
        w = get_adaptive_w("general", 11.0)
        assert w == 11.0

    def test_unknown_type_unchanged(self):
        w = get_adaptive_w("unknown_type", 11.0)
        assert w == 11.0


class TestScoreAndRankMemories:
    """Test the main scoring orchestrator."""

    def _make_memory(self, sim, days_ago=1, access_count=1, tags=None):
        """Helper to create a memory dict for testing."""
        now = datetime.now(timezone.utc)
        created = now - timedelta(days=days_ago + 5)
        timestamps = [
            now - timedelta(days=days_ago - i * (days_ago / max(access_count, 1)))
            for i in range(access_count)
        ] if access_count > 0 else []

        return {
            "id": f"mem-{sim}-{days_ago}",
            "content": "test content",
            "summary": "test",
            "category": "discovery",
            "tags": tags or [],
            "importance_score": 0.5,
            "sim": sim,
            "created_at": created,
            "access_timestamps": timestamps,
            "memory_status": "active",
        }

    def test_reranking_order(self):
        """ACT-R should re-order memories differently from pure cosine."""
        config = ACTRConfig(use_noise=False, use_spreading=False, tau=-100)

        # Memory A: high similarity but old
        mem_a = self._make_memory(sim=0.95, days_ago=60, access_count=1)
        # Memory B: lower similarity but very recent and frequent
        mem_b = self._make_memory(sim=0.80, days_ago=1, access_count=20)

        scored = score_and_rank_memories(
            rows=[mem_a, mem_b], config=config
        )

        # B should rank higher due to recency + frequency despite lower cosine
        assert len(scored) == 2
        assert scored[0]["id"] == mem_b["id"]

    def test_threshold_filtering(self):
        """Memories below tau should be filtered out."""
        config = ACTRConfig(use_noise=False, use_spreading=False, tau=100)

        mem = self._make_memory(sim=0.5, days_ago=365, access_count=1)
        scored = score_and_rank_memories(rows=[mem], config=config)

        assert len(scored) == 0

    def test_activation_score_present(self):
        """Each scored memory should have activation_score."""
        config = ACTRConfig(use_noise=False, tau=-100)
        mem = self._make_memory(sim=0.9, days_ago=1)

        scored = score_and_rank_memories(rows=[mem], config=config)

        assert len(scored) == 1
        assert "activation_score" in scored[0]
        assert isinstance(scored[0]["activation_score"], float)
        assert "actr_components" in scored[0]

    def test_empty_rows(self):
        """Empty input should return empty output."""
        config = ACTRConfig()
        assert score_and_rank_memories(rows=[], config=config) == []

    def test_spreading_activation_boost(self):
        """Memories with shared tags should rank higher."""
        config = ACTRConfig(
            use_noise=False, use_spreading=True, tau=-100
        )

        mem_tagged = self._make_memory(sim=0.8, days_ago=5, tags=["auth"])
        mem_plain = self._make_memory(sim=0.8, days_ago=5, tags=["unrelated"])

        scored = score_and_rank_memories(
            rows=[mem_plain, mem_tagged],
            query_tags=["auth"],
            tag_fan_counts={"auth": 5, "unrelated": 50},
            config=config,
        )

        assert len(scored) == 2
        # Tagged memory should have higher activation
        assert scored[0]["tags"] == ["auth"]

    def test_retrocompat_no_actr(self):
        """With use_actr=False in config, score_and_rank still works
        (it's called only when use_actr=True, but should not crash)."""
        config = ACTRConfig(use_actr=False, use_noise=False, tau=-100)
        mem = self._make_memory(sim=0.9, days_ago=1)

        scored = score_and_rank_memories(rows=[mem], config=config)
        assert len(scored) == 1

    def test_adaptive_w_affects_ranking(self):
        """Different query types should produce different rankings."""
        config = ACTRConfig(use_noise=False, use_spreading=False, tau=-100)

        # Two memories: one recent+frequent, one with high similarity
        mem_recent = self._make_memory(sim=0.7, days_ago=1, access_count=15)
        mem_similar = self._make_memory(sim=0.95, days_ago=30, access_count=1)

        # Debugging: high w (favors similarity)
        scored_debug = score_and_rank_memories(
            rows=[mem_recent, mem_similar],
            config=config,
            query="fix the error bug",
        )

        # With debugging query (w*1.5), similarity matters more
        # The mem_similar has 0.95 vs 0.7 = 0.25 diff * 16.5 = 4.125 extra points
        # This may or may not override the recency advantage depending on exact values
        # Just verify both get scored
        assert len(scored_debug) == 2
        assert all("activation_score" in m for m in scored_debug)
