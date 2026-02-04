# Hooks & Automatic Prompt Capture

This document describes the hook system in MCP-Claude-mem-local, particularly the `UserPromptSubmit` hook that automatically captures user prompts for semantic search and analysis.

---

## Table of Contents

- [Overview](#overview)
- [UserPromptSubmit Hook](#userpromptsubmit-hook)
- [capture-prompt.py Script](#capture-promptpy-script)
- [user_prompts Table](#user_prompts-table)
- [Complete Flow](#complete-flow)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## Overview

MCP-Claude-mem-local uses Claude Code's hook system to automatically capture and store user prompts. This enables:

- **Semantic search** across your prompt history
- **Project-based filtering** of prompts
- **Session tracking** for context analysis
- **Web UI visualization** of prompt patterns

The capture happens transparently without blocking Claude Code's normal operation.

---

## UserPromptSubmit Hook

The `UserPromptSubmit` hook triggers every time a user submits a prompt to Claude Code.

### Hook Configuration

Located in `plugins/hooks/hooks.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "description": "Capture user prompts automatically for memory and search",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_MEMORY_HOME:-$HOME/claude-memory-local}/venv/bin/python3\" \"${CLAUDE_MEMORY_HOME:-$HOME/claude-memory-local}/plugin/scripts/capture-prompt.py\"",
            "timeout": 10,
            "failOnError": false
          }
        ]
      }
    ]
  }
}
```

### Key Properties

| Property | Value | Description |
|----------|-------|-------------|
| `type` | `command` | Executes a shell command |
| `timeout` | `10` | Maximum 10 seconds to complete |
| `failOnError` | `false` | **Never blocks Claude** — errors are silently ignored |

### Input Format

Claude Code passes hook data as JSON via stdin:

```json
{
  "session_id": "abc123-def456",
  "prompt": "Help me fix the authentication bug",
  "cwd": "/Users/user/projects/my-app",
  "hook_event_name": "UserPromptSubmit"
}
```

| Field | Description |
|-------|-------------|
| `session_id` | Unique identifier for the Claude Code session |
| `prompt` | The user's prompt text |
| `cwd` | Current working directory (project path) |
| `hook_event_name` | Always `UserPromptSubmit` for this hook |

---

## capture-prompt.py Script

The `capture-prompt.py` script processes each prompt and stores it with a vector embedding.

### Location

```
plugins/scripts/capture-prompt.py
```

### Functionality

1. **Read JSON input** from stdin
2. **Extract project name** from `CLAUDE.md` or directory name
3. **Skip invalid prompts** (empty, too short < 3 chars)
4. **Generate embedding** via Ollama (nomic-embed-text)
5. **Store in PostgreSQL** with session context

### Project Name Extraction

The script intelligently extracts the project name:

1. **Priority 1**: Look for pattern `**project-name** -` in `CLAUDE.md`
2. **Fallback**: Use directory name, stripping numeric prefixes (e.g., `36_my-project` → `my-project`)

```python
def extract_project_name(cwd: str) -> str | None:
    # Try CLAUDE.md first
    claude_md = Path(cwd) / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text()
        match = re.search(r'\*\*([a-zA-Z0-9_-]+)\*\*\s*[-–—]', content)
        if match:
            return match.group(1)

    # Fallback to directory name
    project_name = Path(cwd).name
    return re.sub(r'^\d+_', '', project_name)
```

### Embedding Generation

```python
async def get_embedding(text: str) -> list | None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(
            f"{OLLAMA_HOST}/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": text}
        )
        return response.json().get("embedding")
```

- **Timeout**: 5 seconds (short to avoid blocking)
- **Model**: nomic-embed-text (768 dimensions)
- **Fallback**: Stores prompt without embedding if Ollama unavailable

### Error Handling

The script **never blocks Claude Code**:

- All exceptions are caught silently
- Missing `.env` → silent exit
- Database unavailable → silent exit
- Ollama timeout → store without embedding
- Always returns exit code `0`

---

## user_prompts Table

### Schema

```sql
CREATE TABLE user_prompts (
    id SERIAL PRIMARY KEY,
    session_id TEXT,                 -- Claude Code session ID
    prompt_number INTEGER,           -- Sequence number within session
    prompt_text TEXT NOT NULL,       -- Full prompt text
    embedding vector(768),           -- Vector for semantic search
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    user_id VARCHAR(255),            -- Future: multi-user support
    project_context VARCHAR(255)     -- Extracted project name
);
```

### Indexes

```sql
-- Vector similarity search (HNSW algorithm)
CREATE INDEX idx_prompts_embedding
    ON user_prompts USING hnsw (embedding vector_cosine_ops);
```

### Example Data

| id | session_id | prompt_number | prompt_text | project_context | created_at |
|----|------------|---------------|-------------|-----------------|------------|
| 1 | abc123 | 1 | "Help me fix auth bug" | my-app | 2026-02-04 10:30:00 |
| 2 | abc123 | 2 | "Now add tests" | my-app | 2026-02-04 10:35:00 |
| 3 | def456 | 1 | "Explain this code" | other-project | 2026-02-04 11:00:00 |

---

## Complete Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User types prompt                            │
│                              │                                       │
│                              ▼                                       │
│                    ┌─────────────────┐                              │
│                    │   Claude Code   │                              │
│                    │ UserPromptSubmit│                              │
│                    │     hook        │                              │
│                    └────────┬────────┘                              │
│                             │ JSON via stdin                        │
│                             ▼                                       │
│                    ┌─────────────────┐                              │
│                    │capture-prompt.py│                              │
│                    │                 │                              │
│                    │ 1. Parse JSON   │                              │
│                    │ 2. Extract proj │                              │
│                    │ 3. Validate     │                              │
│                    └────────┬────────┘                              │
│                             │                                       │
│              ┌──────────────┼──────────────┐                       │
│              ▼                             ▼                        │
│    ┌─────────────────┐           ┌─────────────────┐               │
│    │     Ollama      │           │   PostgreSQL    │               │
│    │  POST /api/     │           │    INSERT       │               │
│    │   embeddings    │           │  user_prompts   │               │
│    └────────┬────────┘           └────────┬────────┘               │
│             │                             │                         │
│             │ vector[768]                 │                         │
│             └─────────────────────────────┘                        │
│                             │                                       │
│                             ▼                                       │
│                    ┌─────────────────┐                              │
│                    │   Web UI        │                              │
│                    │  viewer.html    │                              │
│                    │  Prompts tab    │                              │
│                    └─────────────────┘                              │
└─────────────────────────────────────────────────────────────────────┘
```

### Timing

| Step | Duration |
|------|----------|
| Hook trigger → Script start | ~50ms |
| Embedding generation | ~100-500ms |
| Database insert | ~10-50ms |
| **Total** | **~200-600ms** |

The 10-second timeout provides ample margin for slow systems.

---

## Configuration

### Enable the Hook

The hook is configured in `~/.claude/settings.json` (not via a local plugin):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "type": "command",
        "command": "~/claude-memory-local/venv/bin/python3 ~/claude-memory-local/plugins/scripts/capture-prompt.py",
        "timeout": 10,
        "failOnError": false
      }
    ]
  }
}
```

### Environment Variables

In `~/claude-memory-local/.env`:

```env
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=claude_memory
PG_USER=claude
PG_PASSWORD=your_secure_password
OLLAMA_HOST=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text
```

### Disable Prompt Capture

To disable, remove the `UserPromptSubmit` section from `~/.claude/settings.json`.

---

## Troubleshooting

### Prompts not being captured

1. **Check PostgreSQL is running**:
   ```bash
   pg_isready
   ```

2. **Check Ollama is running**:
   ```bash
   ollama list
   ```

3. **Verify .env configuration**:
   ```bash
   cat ~/claude-memory-local/.env
   ```

4. **Test the script manually**:
   ```bash
   echo '{"prompt": "test", "session_id": "test123", "cwd": "/tmp"}' | \
     ~/claude-memory-local/venv/bin/python3 \
     ~/claude-memory-local/plugins/scripts/capture-prompt.py
   ```

5. **Check database for entries**:
   ```bash
   psql -U claude -d claude_memory -c "SELECT * FROM user_prompts ORDER BY created_at DESC LIMIT 5;"
   ```

### Embeddings missing

If prompts are stored but `embedding` is NULL:

1. **Verify Ollama is running and model available**:
   ```bash
   ollama list
   # Should show: nomic-embed-text
   ```

2. **Test embedding API**:
   ```bash
   curl http://localhost:11434/api/embeddings \
     -d '{"model": "nomic-embed-text", "prompt": "test"}'
   ```

3. **Pull model if missing**:
   ```bash
   ollama pull nomic-embed-text
   ```

### Performance issues

If prompts cause noticeable delays:

1. **Reduce embedding timeout** in capture-prompt.py (currently 5s)
2. **Check Ollama resources** — may need more RAM
3. **Verify PostgreSQL performance** — check for connection pooling issues

---

## See Also

- [Main Documentation](./MCP-Claude-mem-local-Documentation-Technique.md)
- [Plugin & Hooks Section](./MCP-Claude-mem-local-Documentation-Technique.md#7-plugin--hooks)
- [Web Interface](./MCP-Claude-mem-local-Documentation-Technique.md#8-interface-web)
