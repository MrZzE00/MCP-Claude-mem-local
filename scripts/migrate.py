#!/usr/bin/env python3
"""Migration runner for claude-memory-local schema updates."""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv()

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
CHECKSUMS_FILE = MIGRATIONS_DIR / "checksums.json"


def load_checksums() -> dict[str, str]:
    """Load expected checksums for migration files."""
    if CHECKSUMS_FILE.exists():
        return json.loads(CHECKSUMS_FILE.read_text())
    return {}


def compute_checksum(path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
            checksum VARCHAR(64),
            applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    # Add checksum column if missing (backwards compat)
    try:
        await conn.execute("""
            ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum VARCHAR(64)
        """)
    except Exception:
        pass


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
        checksums = load_checksums()

        pending = [(v, n, p) for v, n, p in migrations if v not in applied]

        if not pending:
            print("No pending migrations.")
            return

        for version, name, path in pending:
            # Verify checksum if available
            actual_checksum = compute_checksum(path)
            if name in checksums:
                expected = checksums[name]
                if actual_checksum != expected:
                    print(f"ERROR: Checksum mismatch for {name}!")
                    print(f"  Expected: {expected}")
                    print(f"  Actual:   {actual_checksum}")
                    print("  Migration file may have been tampered with. Aborting.")
                    sys.exit(1)

            print(f"{'[DRY RUN] ' if dry_run else ''}Applying migration {name} (sha256: {actual_checksum[:12]}...)...")
            if not dry_run:
                sql = path.read_text()
                await conn.execute(sql)
                # Record checksum in migrations table
                await conn.execute(
                    "UPDATE schema_migrations SET checksum = $1 WHERE version = $2",
                    actual_checksum, version,
                )
                print(f"  Applied migration {version}: {name}")
            else:
                print(f"  Would apply migration {version}: {name}")

        print(f"Done. {len(pending)} migration(s) {'would be ' if dry_run else ''}applied.")
    finally:
        await conn.close()


def generate_checksums():
    """Generate checksums.json for all migration files."""
    migrations = discover_migrations()
    checksums = {}
    for _, name, path in migrations:
        checksums[name] = compute_checksum(path)
    CHECKSUMS_FILE.write_text(json.dumps(checksums, indent=2) + "\n")
    print(f"Generated checksums for {len(checksums)} migration(s) in {CHECKSUMS_FILE}")


def main():
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be applied without executing")
    parser.add_argument("--generate-checksums", action="store_true", help="Generate checksums.json for migration files")
    args = parser.parse_args()

    if args.generate_checksums:
        generate_checksums()
    else:
        asyncio.run(run_migrations(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
