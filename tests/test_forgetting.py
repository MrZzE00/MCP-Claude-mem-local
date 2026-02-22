"""Tests for the strategic forgetting engine."""

import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ["PG_PASSWORD"] = "test_password"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from actr_scoring import ACTRConfig
from forgetting import (
    classify_memory_status,
    compute_all_activations,
    reactivate_memory,
    run_forgetting_cycle,
    update_memory_statuses,
)


def make_mock_pool(mock_conn):
    """Create a mock pool that properly supports async with pool.acquire()."""
    mock_pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__.return_value = mock_conn
    cm.__aexit__.return_value = None
    mock_pool.acquire.return_value = cm
    return mock_pool


class TestClassifyMemoryStatus:
    """Test status classification based on activation level."""

    def test_active_stays_active(self):
        """Positive activation = active."""
        assert classify_memory_status(1.5) == "active"
        assert classify_memory_status(0.01) == "active"

    def test_zero_is_dormant(self):
        """Zero activation = dormant (boundary)."""
        assert classify_memory_status(0.0) == "dormant"

    def test_negative_is_dormant(self):
        """Slightly negative = dormant."""
        assert classify_memory_status(-0.5) == "dormant"
        assert classify_memory_status(-1.9) == "dormant"

    def test_very_negative_is_forgotten(self):
        """Below -2.0 = forgotten."""
        assert classify_memory_status(-2.0) == "forgotten"
        assert classify_memory_status(-5.0) == "forgotten"
        assert classify_memory_status(-100.0) == "forgotten"

    def test_boundary_dormant_forgotten(self):
        """Exact boundary: -2.0 = forgotten, -1.999 = dormant."""
        assert classify_memory_status(-2.0) == "forgotten"
        assert classify_memory_status(-1.999) == "dormant"


class TestComputeAllActivations:
    """Test batch activation computation."""

    @pytest.mark.asyncio
    async def test_computes_for_all_memories(self):
        """Should compute activation for every memory returned."""
        now = datetime.now(timezone.utc)
        mock_conn = AsyncMock()
        mock_pool = make_mock_pool(mock_conn)

        mock_conn.fetch.return_value = [
            {
                "id": "id-1",
                "access_timestamps": [now - timedelta(hours=1)],
                "created_at": now - timedelta(days=1),
                "memory_status": "active",
            },
            {
                "id": "id-2",
                "access_timestamps": [now - timedelta(days=200)],
                "created_at": now - timedelta(days=365),
                "memory_status": "active",
            },
        ]

        config = ACTRConfig(d=0.5)
        results = await compute_all_activations(mock_pool, config)

        assert len(results) == 2
        assert "id-1" in results
        assert "id-2" in results

        # Recent memory should have higher activation
        base_1, status_1 = results["id-1"]
        base_2, status_2 = results["id-2"]
        assert base_1 > base_2

    @pytest.mark.asyncio
    async def test_old_becomes_dormant(self):
        """Memory accessed long ago should become dormant."""
        now = datetime.now(timezone.utc)
        mock_conn = AsyncMock()
        mock_pool = make_mock_pool(mock_conn)

        mock_conn.fetch.return_value = [
            {
                "id": "old-mem",
                "access_timestamps": [now - timedelta(days=90)],
                "created_at": now - timedelta(days=180),
                "memory_status": "active",
            },
        ]

        results = await compute_all_activations(mock_pool)
        _, status = results["old-mem"]
        # With a single access 90 days ago, base-level should be quite low
        assert status in ("dormant", "forgotten")

    @pytest.mark.asyncio
    async def test_very_old_becomes_forgotten(self):
        """Memory with very old single access should become forgotten."""
        now = datetime.now(timezone.utc)
        mock_conn = AsyncMock()
        mock_pool = make_mock_pool(mock_conn)

        mock_conn.fetch.return_value = [
            {
                "id": "ancient-mem",
                "access_timestamps": [now - timedelta(days=500)],
                "created_at": now - timedelta(days=600),
                "memory_status": "active",
            },
        ]

        results = await compute_all_activations(mock_pool)
        _, status = results["ancient-mem"]
        assert status == "forgotten"


class TestUpdateMemoryStatuses:
    """Test database status update logic."""

    @pytest.mark.asyncio
    async def test_transitions_counted(self):
        """Should count transitions correctly."""
        now = datetime.now(timezone.utc)
        mock_conn = AsyncMock()
        mock_pool = make_mock_pool(mock_conn)

        # First call: compute_all_activations fetch
        # Second call: current statuses fetch
        mock_conn.fetch.side_effect = [
            # For compute_all_activations
            [
                {
                    "id": "mem-1",
                    "access_timestamps": [now - timedelta(minutes=5)],
                    "created_at": now - timedelta(days=1),
                    "memory_status": "active",
                },
                {
                    "id": "mem-2",
                    "access_timestamps": [now - timedelta(days=500)],
                    "created_at": now - timedelta(days=600),
                    "memory_status": "active",
                },
            ],
            # For current statuses
            [
                {"id": "mem-1", "memory_status": "active"},
                {"id": "mem-2", "memory_status": "active"},
            ],
        ]
        mock_conn.executemany = AsyncMock()

        config = ACTRConfig(d=0.5)
        counters = await update_memory_statuses(mock_pool, config)

        # mem-1 stays active (recent), mem-2 transitions to forgotten
        total = sum(counters.values())
        assert total == 2
        assert counters["unchanged"] >= 0


class TestRunForgettingCycle:
    """Test the full forgetting cycle."""

    @pytest.mark.asyncio
    async def test_returns_summary(self):
        """Should return a formatted summary string."""
        now = datetime.now(timezone.utc)
        mock_conn = AsyncMock()
        mock_pool = make_mock_pool(mock_conn)

        mock_conn.fetch.side_effect = [
            [
                {
                    "id": "mem-1",
                    "access_timestamps": [now - timedelta(minutes=5)],
                    "created_at": now - timedelta(days=1),
                    "memory_status": "active",
                }
            ],
            [{"id": "mem-1", "memory_status": "active"}],
        ]
        mock_conn.executemany = AsyncMock()

        result = await run_forgetting_cycle(mock_pool)

        assert "Forgetting cycle complete" in result
        assert "Total memories processed" in result


class TestForgottenRecovery:
    """Test that forgotten memories can be recovered."""

    @pytest.mark.asyncio
    async def test_reactivation(self):
        """Reactivating a forgotten memory should set it to active."""
        mock_conn = AsyncMock()
        mock_pool = make_mock_pool(mock_conn)
        mock_conn.execute.return_value = "UPDATE 1"

        result = await reactivate_memory(mock_pool, "some-uuid")
        assert "reactivated" in result

        # Verify the SQL updated status and timestamps
        call_args = mock_conn.execute.call_args[0][0]
        assert "memory_status = 'active'" in call_args
        assert "array_append" in call_args

    @pytest.mark.asyncio
    async def test_reactivation_not_found(self):
        """Reactivating a non-existent memory should report not found."""
        mock_conn = AsyncMock()
        mock_pool = make_mock_pool(mock_conn)
        mock_conn.execute.return_value = "UPDATE 0"

        result = await reactivate_memory(mock_pool, "nonexistent")
        assert "not found" in result
