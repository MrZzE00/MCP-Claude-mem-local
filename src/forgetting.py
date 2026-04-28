"""
Strategic Forgetting Engine

Periodically recalculates base-level activation for all memories
and transitions their status:
    A(m) > 0      -> active    (readily retrievable)
    -2 < A(m) <= 0 -> dormant  (retrievable but deprioritized)
    A(m) <= -2     -> forgotten (excluded from default results)

IMPORTANT: forgotten != deleted
- Stays in database, excluded from results by default
- Queryable explicitly via include_forgotten=true
- Can become active again if explicitly accessed
"""

import logging
from datetime import datetime, timezone

from actr_scoring import ACTRConfig, compute_base_level

logger = logging.getLogger("claude-memory-local")

# Thresholds for status transitions (based on base-level activation only)
ACTIVE_THRESHOLD = 0.0
DORMANT_THRESHOLD = -2.0


def classify_memory_status(base_level: float) -> str:
    """Classify memory status based on base-level activation.

    Args:
        base_level: B(m) computed from access timestamps.

    Returns:
        'active', 'dormant', or 'forgotten'
    """
    if base_level > ACTIVE_THRESHOLD:
        return "active"
    elif base_level > DORMANT_THRESHOLD:
        return "dormant"
    else:
        return "forgotten"


async def update_memory_statuses(pool, config: ACTRConfig | None = None) -> dict:
    """Recalculate activations and update memory statuses in the database.

    Uses SELECT ... FOR UPDATE with an advisory lock to prevent TOCTOU
    race conditions between concurrent forgetting cycles.

    Args:
        pool: asyncpg connection pool.
        config: ACTRConfig instance.

    Returns:
        Transition counts: {active: N, dormant: N, forgotten: N, unchanged: N}
    """
    if config is None:
        config = ACTRConfig()

    counters = {"active": 0, "dormant": 0, "forgotten": 0, "unchanged": 0}
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Advisory lock prevents concurrent forgetting cycles
            await conn.execute("SELECT pg_advisory_xact_lock(42)")

            rows = await conn.fetch("""
                SELECT id, access_timestamps, created_at, memory_status
                FROM memories
                WHERE memory_status IS NULL
                   OR memory_status IN ('active', 'dormant', 'forgotten')
                FOR UPDATE
            """)

            updates = {"active": [], "dormant": [], "forgotten": []}

            for row in rows:
                access_ts = row["access_timestamps"] or []
                created_at = row["created_at"]
                if created_at and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)

                base_level = compute_base_level(access_ts, created_at, config.d)
                new_status = classify_memory_status(base_level)
                old_status = row["memory_status"]

                if old_status != new_status:
                    updates[new_status].append((row["id"], base_level))
                    counters[new_status] += 1
                else:
                    counters["unchanged"] += 1

            # Apply batch updates within the same transaction
            for status, memory_list in updates.items():
                if not memory_list:
                    continue
                await conn.executemany("""
                    UPDATE memories
                    SET memory_status = $1,
                        actr_activation = $2,
                        activation_updated_at = $3
                    WHERE id = $4
                """, [(status, act, now, mid) for mid, act in memory_list])

    return counters


async def run_forgetting_cycle(pool, config: ACTRConfig | None = None) -> str:
    """Execute a full forgetting cycle.

    Computes activation for all memories, updates statuses,
    and returns a summary of transitions.

    Args:
        pool: asyncpg connection pool.
        config: ACTRConfig instance.

    Returns:
        Formatted summary string of the forgetting cycle results.
    """
    logger.info("Starting forgetting cycle...")

    counters = await update_memory_statuses(pool, config)
    total = sum(counters.values())

    summary = (
        f"Forgetting cycle complete.\n"
        f"Total memories processed: {total}\n"
        f"  Active: {counters['active']} transitions\n"
        f"  Dormant: {counters['dormant']} transitions\n"
        f"  Forgotten: {counters['forgotten']} transitions\n"
        f"  Unchanged: {counters['unchanged']}"
    )

    logger.info(summary)
    return summary


async def reactivate_memory(pool, memory_id) -> str:
    """Reactivate a forgotten or dormant memory by recording an access.

    This simulates forced recall — the memory gets a new access timestamp
    and transitions back to active status. Uses ring buffer to cap timestamps.

    Args:
        pool: asyncpg connection pool.
        memory_id: UUID of the memory to reactivate.

    Returns:
        Status message.
    """
    async with pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE memories
            SET memory_status = 'active',
                access_timestamps = (
                    CASE
                        WHEN array_length(COALESCE(access_timestamps, '{}'), 1) >= 1000
                        THEN array_append(access_timestamps[2:], NOW())
                        ELSE array_append(COALESCE(access_timestamps, '{}'), NOW())
                    END
                ),
                access_count = access_count + 1,
                last_accessed_at = NOW()
            WHERE id = $1
        """, memory_id)

        if result == "UPDATE 1":
            return f"Memory {memory_id} reactivated."
        return f"Memory {memory_id} not found."
