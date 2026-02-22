#!/usr/bin/env python3
"""Migration runner for claude-memory-local schema updates."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv()

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def get_connection():
    return await asyncpg.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5432")),
        database=os.getenv("PG_DATABASE", "claude_memory"),
        user=os.getenv("PG_USER", "claude"),
        password=os.getenv("PG_PASSWORD"),
    )


async def ensure_migrations_table(conn):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)


async def get_applied_versions(conn):
    rows = await conn.fetch("SELECT version FROM schema_migrations ORDER BY version")
    return {row["version"] for row in rows}


def discover_migrations():
    migrations = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        # Extract version number from filename like 001_actr_schema.sql
        version = int(f.name.split("_")[0])
        migrations.append((version, f.name, f))
    return migrations


async def run_migrations(dry_run=False):
    conn = await get_connection()
    try:
        await ensure_migrations_table(conn)
        applied = await get_applied_versions(conn)
        migrations = discover_migrations()

        pending = [(v, n, p) for v, n, p in migrations if v not in applied]

        if not pending:
            print("No pending migrations.")
            return

        for version, name, path in pending:
            print(f"{'[DRY RUN] ' if dry_run else ''}Applying migration {name}...")
            if not dry_run:
                sql = path.read_text()
                await conn.execute(sql)
                print(f"  Applied migration {version}: {name}")
            else:
                print(f"  Would apply migration {version}: {name}")

        print(f"Done. {len(pending)} migration(s) {'would be ' if dry_run else ''}applied.")
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be applied without executing")
    args = parser.parse_args()
    asyncio.run(run_migrations(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
