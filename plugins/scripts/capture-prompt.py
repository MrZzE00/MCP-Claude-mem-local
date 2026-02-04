#!/usr/bin/env python3
"""
MCP-Claude-mem-local - User Prompt Capture Hook
Automatically captures user prompts from Claude Code sessions.

This script is triggered by the UserPromptSubmit hook and stores
prompts in the user_prompts table with vector embeddings for
semantic search.

Input (stdin): JSON with session_id, user_prompt, cwd, hook_event_name
Output: Exit 0 to continue (never blocks Claude)
"""

import json
import os
import sys
from pathlib import Path

import asyncio
import asyncpg
import httpx
from dotenv import load_dotenv

# Load configuration
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DATABASE = os.getenv("PG_DATABASE", "claude_memory")
PG_USER = os.getenv("PG_USER", "claude")
PG_PASSWORD = os.getenv("PG_PASSWORD")
if not PG_PASSWORD:
    # Silent exit for hooks - don't block Claude
    sys.exit(0)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")


import re

def extract_project_name(cwd: str) -> str | None:
    """Extract project name from CLAUDE.md or fallback to directory name."""
    if not cwd:
        return None

    project_path = Path(cwd)

    # Try to find CLAUDE.md
    claude_md = project_path / "CLAUDE.md"
    if claude_md.exists():
        try:
            content = claude_md.read_text(encoding="utf-8")
            # Look for pattern: **project-name** in Project Overview section
            # Format: **nom-du-projet** - Description...
            match = re.search(r'\*\*([a-zA-Z0-9_-]+)\*\*\s*[-–—]', content)
            if match:
                return match.group(1)
        except Exception:
            pass

    # Fallback: extract from directory name, remove numeric prefixes
    project_name = project_path.name
    project_name = re.sub(r'^\d+_', '', project_name)
    return project_name if project_name else None


async def get_embedding(text: str) -> list | None:
    """Generate embedding via Ollama (timeout 5s)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{OLLAMA_HOST}/api/embeddings",
                json={"model": EMBEDDING_MODEL, "prompt": text}
            )
            if response.status_code == 200:
                return response.json().get("embedding")
    except Exception:
        pass
    return None


async def store_prompt(session_id: str, prompt_text: str, project: str | None) -> bool:
    """Store prompt in database with embedding."""
    conn = None
    try:
        conn = await asyncpg.connect(
            host=PG_HOST,
            port=PG_PORT,
            database=PG_DATABASE,
            user=PG_USER,
            password=PG_PASSWORD
        )

        # Get next prompt number for this session
        result = await conn.fetchval(
            "SELECT COALESCE(MAX(prompt_number), 0) + 1 FROM user_prompts WHERE session_id = $1",
            session_id
        )
        prompt_number = result or 1

        # Generate embedding
        embedding = await get_embedding(prompt_text)

        if embedding:
            # Format embedding for PostgreSQL vector type
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
            await conn.execute(
                """
                INSERT INTO user_prompts (session_id, prompt_number, prompt_text, embedding, project_context)
                VALUES ($1, $2, $3, $4::vector, $5)
                """,
                session_id, prompt_number, prompt_text, embedding_str, project
            )
        else:
            # Store without embedding if Ollama is unavailable
            await conn.execute(
                """
                INSERT INTO user_prompts (session_id, prompt_number, prompt_text, project_context)
                VALUES ($1, $2, $3, $4)
                """,
                session_id, prompt_number, prompt_text, project
            )

        return True

    except Exception:
        return False
    finally:
        if conn:
            await conn.close()


async def main():
    """Main entry point - reads JSON from stdin."""
    try:
        # Read JSON from stdin (Claude Code passes hook data this way)
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        # No valid input, exit silently
        sys.exit(0)

    # Extract fields from hook payload
    # Claude Code uses "prompt", but accept "user_prompt" for backwards compatibility
    prompt_text = data.get("prompt") or data.get("user_prompt", "")
    session_id = data.get("session_id") or os.getenv("CLAUDE_SESSION_ID")
    cwd = data.get("cwd") or os.getenv("CLAUDE_PROJECT_DIR")

    # Extract project name from CLAUDE.md or fallback to directory name
    project = None
    if cwd:
        project = extract_project_name(cwd)

    # Skip empty prompts
    if not prompt_text or not prompt_text.strip():
        sys.exit(0)

    # Skip very short prompts (likely commands or typos)
    if len(prompt_text.strip()) < 3:
        sys.exit(0)

    # Store the prompt
    await store_prompt(session_id, prompt_text.strip(), project)

    # Always exit 0 to not block Claude
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
