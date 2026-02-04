# MCP-Claude-mem-local

Persistent local memory system for Claude Code using PostgreSQL + pgvector for semantic search.

**Zero API tokens consumed** — All embeddings are generated locally with Ollama.

---

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [MCP Tools](#mcp-tools)
  - [Automatic Prompt Capture](#automatic-prompt-capture)
  - [Web Interface](#web-interface)
  - [CLAUDE.md Integration](#claudemd-integration)
- [Recommended Workflow](#recommended-workflow)
- [Maintenance](#maintenance)
- [Troubleshooting](#troubleshooting)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Claude Code                             │
│                          │                                   │
│                    ┌─────▼─────┐                            │
│                    │ MCP Server │ (5 tools)                 │
│                    └─────┬─────┘                            │
│                          │                                   │
│         ┌────────────────┼────────────────┐                 │
│         ▼                ▼                ▼                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ PostgreSQL  │  │   Ollama    │  │  Plugin     │        │
│  │ + pgvector  │  │ (embeddings)│  │  (hooks)    │        │
│  │ (Homebrew)  │  │             │  │             │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│         │                                    │              │
│         ▼                                    ▼              │
│  ┌─────────────┐                    ┌─────────────┐        │
│  │  memories   │                    │  CLAUDE.md  │        │
│  │  (table)    │                    │ (per-folder)│        │
│  └─────────────┘                    └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

### Components

| Component | Role | Port | Auto-start |
|-----------|------|------|------------|
| **PostgreSQL 17 + pgvector** | Memory storage + vector search (Homebrew) | 5432 | ✅ Yes |
| **Ollama** | Local embedding generation (nomic-embed-text) | 11434 | ❌ Manual |
| **MCP Server** | Interface with Claude Code (5 tools) | stdio | - |
| **Plugin hooks** | Auto-inject context into CLAUDE.md + capture prompts | - | - |
| **Web Interface** | Memory and prompt visualization | 8080 | - |

### After a System Reboot

| Service | Behavior | Action Required |
|---------|----------|-----------------|
| **PostgreSQL** | Starts automatically via `brew services` | None |
| **Ollama** | Does NOT start automatically (intentional) | Launch manually |

**Why Ollama requires manual start?** This is a deliberate design choice to keep human control over AI processes. Before using MCP-Claude-mem-local after a reboot, launch Ollama:

```bash
# Option 1: Open Ollama.app (if installed)
open -a Ollama

# Option 2: Start via command line
ollama serve &
```

---

## Prerequisites

- **macOS** (Homebrew) or **Linux**
- **Python 3.11+**
- **Homebrew** (macOS) or apt/dnf (Linux)
- **Claude Code** (with MCP support)

---

## Installation

### Quick Install

```bash
# Clone the repository
git clone https://github.com/your-org/claude-memory-local.git
cd claude-memory-local

# Run the installer
./install.sh
```

The installer will:
1. Install PostgreSQL 17 + pgvector via Homebrew
2. Create Python virtual environment
3. Initialize database schema
4. Install Ollama and download embedding model
5. Configure Claude Code MCP server

After installation, **restart Claude Code** and the `claude-memory-local` MCP server will be available.

### Directory Structure

```
~/claude-memory-local/
├── .env                    # Configuration
├── venv/                   # Python virtual environment
├── src/
│   ├── server.py          # MCP server
│   └── web_ui.py          # Web UI generator
├── plugins/
│   ├── hooks/
│   │   └── hooks.json     # Hook configuration
│   └── scripts/
│       └── context-hook.py # Context injection script
├── viewer.html            # Web interface
└── start-server.sh        # Server launch script
```

---

## Configuration

### Environment Variables (`.env`)

Copy `.env.example` to `.env` and configure:

```env
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=claude_memory
PG_USER=claude
PG_PASSWORD=YOUR_SECURE_PASSWORD    # Generate with: openssl rand -base64 32
OLLAMA_HOST=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text

# Security (optional)
API_KEY=                            # Set to require API key authentication
RATE_LIMIT_REQUESTS=60              # Requests per minute (default: 60)
RATE_LIMIT_WINDOW=60                # Rate limit window in seconds
ALLOWED_ORIGINS=localhost:8080      # CORS allowed origins
```

> ⚠️ **Security**: Never commit `.env` with real credentials. Use strong passwords in production.

---

## Security

### API Key Authentication (Optional)

Set `API_KEY` in `.env` to require authentication for all API endpoints:

```env
API_KEY=your-secret-api-key-here
```

When set, all requests must include the header: `X-API-Key: your-secret-api-key-here`

### Rate Limiting

Default: 60 requests per minute. Configure via environment variables:

```env
RATE_LIMIT_REQUESTS=60    # Max requests per window
RATE_LIMIT_WINDOW=60      # Window duration in seconds
```

### Security Headers

All HTTP responses include security headers:
- `Content-Security-Policy` (CSP)
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `X-XSS-Protection: 1; mode=block`

### CORS

By default, CORS is restricted to localhost. Configure allowed origins:

```env
ALLOWED_ORIGINS=localhost:8080,localhost:3000
```

### SSRF Protection

The `OLLAMA_HOST` variable is validated to prevent Server-Side Request Forgery attacks.

---

### MCP Configuration (`~/.claude.json`)

```json
{
  "mcpServers": {
    "claude-memory-local": {
      "type": "stdio",
      "command": "~/claude-memory-local/start-server.sh",
      "args": []
    }
  }
}
```

---

## Usage

### MCP Tools

The server exposes **5 tools** directly usable in Claude Code:

#### 1. `store_memory` — Store a memory

```typescript
store_memory({
  content: "Full description of the problem and solution",
  category: "bugfix",        // bugfix|decision|feature|discovery|refactor|change
  summary: "Short summary",   // optional, auto-generated if absent
  tags: ["auth", "supabase"], // optional
  importance: 0.9,           // 0.0 to 1.0, default: 0.5
  project: "/path/to/project" // optional, enables per-folder CLAUDE.md
})
```

**Available categories:**

| Category | Icon | Usage |
|----------|------|-------|
| `bugfix` | 🔴 | Bug fix |
| `decision` | 🟠 | Architectural decision |
| `feature` | 🟢 | New feature |
| `discovery` | 🔵 | Learning, discovery |
| `refactor` | 🟣 | Refactoring |
| `change` | ⚪ | General change |
| `pattern` | 🟤 | Reusable pattern identified |
| `preference` | 🟡 | User preference |
| `learning` | 📘 | Lesson learned |
| `error_solution` | 🩹 | Solution to specific error |

**New Feature: Per-folder CLAUDE.md**

When you provide a `project` path, `store_memory` automatically updates:
- The `CLAUDE.md` in the specified directory
- The `CLAUDE.md` in the project root (if different)

#### 2. `retrieve_memories` — Search memories

```typescript
retrieve_memories({
  query: "authentication supabase RLS",
  max_results: 5,           // default: 5
  category: "bugfix",       // optional, filter by category
  min_similarity: 0.5       // default: 0.5
})
```

Returns relevant memories via semantic search (cosine similarity).

#### 3. `list_memories` — List recent memories

```typescript
list_memories({
  limit: 20,                // default: 20
  category: "decision"      // optional
})
```

#### 4. `memory_stats` — Statistics

```typescript
memory_stats()
```

Returns:
- Total memories
- Distribution by category
- Memories this week
- Most accessed memories

#### 5. `delete_memory` — Delete a memory

```typescript
delete_memory({
  memory_id: "uuid-of-memory"
})
```

---

### Automatic Prompt Capture

MCP-Claude-mem-local automatically captures your prompts using the `UserPromptSubmit` hook. This enables semantic search across your prompt history.

**How it works:**
1. Every prompt you submit triggers the `UserPromptSubmit` hook
2. The `capture-prompt.py` script extracts the project context
3. An embedding is generated via Ollama (nomic-embed-text)
4. The prompt is stored in the `user_prompts` table

**Key features:**
- **Non-blocking**: Never slows down Claude Code (10s timeout, silent failures)
- **Project-aware**: Associates prompts with the current project
- **Searchable**: Vector embeddings enable semantic search
- **Visible in Web UI**: Prompts tab shows your history

**Configuration** (in `~/.claude/settings.json`):
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

> 📖 Full documentation: [docs/hooks-prompts-capture.md](docs/hooks-prompts-capture.md)

---

### Web Interface

The web interface is included in the repo as `viewer.html`.

#### Launch the web server

```bash
cd ~/claude-memory-local && python3 -m http.server 8080
```

#### Access the interface

Open: **http://localhost:8080/viewer.html**

**Features:**
- Global statistics
- Text search
- Filters by type (bugfix, feature, etc.)
- Filters by project
- Prompts tab

---

### CLAUDE.md Integration

The system automatically updates `CLAUDE.md` files with recent memories when you call `store_memory` with a `project` path.

#### Result in CLAUDE.md

```markdown
<claude-memory-local-context>
# Recent Activity - /path/to/project

| Time | Type | Summary |
|------|------|---------|
| 02/03 10:44 | 🔴 bugfix | Fixed PostgreSQL connection... |
| 02/03 09:30 | 🟢 feature | Added new authentication... |

</claude-memory-local-context>
```

#### Manual context injection

```bash
cd /path/to/your/project
~/claude-memory-local/claude-context.sh
```

---

## Recommended Workflow

### Session Start

```
1. Claude Code starts
2. retrieve_memories({ query: "project context" })
3. Read CLAUDE.md with injected context
```

### During Work

```
After a bugfix → store_memory({ category: "bugfix", project: "/path/to/project", ... })
After a decision → store_memory({ category: "decision", project: "/path/to/project", ... })
Important discovery → store_memory({ category: "discovery", project: "/path/to/project", ... })
```

### Session End

Store important learnings from the session.

---

## Maintenance

### Start services after reboot

```bash
# PostgreSQL - auto-starts via brew services, verify with:
pg_isready

# Ollama - MUST be started manually (intentional design choice)
open -a Ollama
# or: ollama serve &

# Verify Ollama is running
ollama list
```

### Regenerate web interface

```bash
cd ~/claude-memory-local
source venv/bin/activate
python src/web_ui.py
```

### Backup database

```bash
pg_dump -U claude claude_memory > ~/backup-claude-memory-$(date +%Y%m%d).sql
```

### Restore a backup

```bash
psql -U claude claude_memory < ~/backup-claude-memory-YYYYMMDD.sql
```

---

## Troubleshooting

### MCP server doesn't connect

```bash
# Verify PostgreSQL is running
pg_isready

# Verify Ollama is running
ollama list

# Test connection manually
cd ~/claude-memory-local
source venv/bin/activate
python -c "
import asyncio
import asyncpg
import os
from dotenv import load_dotenv
load_dotenv()
async def test():
    conn = await asyncpg.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', 5432)),
        database=os.getenv('PG_DATABASE', 'claude_memory'),
        user=os.getenv('PG_USER', 'claude'),
        password=os.getenv('PG_PASSWORD')
    )
    print('Connection OK')
    await conn.close()
asyncio.run(test())
"
```

### PostgreSQL doesn't start

```bash
# Check if another PostgreSQL is running on port 5432
lsof -i :5432

# If using Homebrew
brew services restart postgresql@17
```

### Error "role claude does not exist"

```bash
createuser -s claude
# Set a secure password (generate one with: openssl rand -base64 32)
psql -c "ALTER USER claude PASSWORD 'YOUR_SECURE_PASSWORD';"
# Update .env with the same password
```

### Web interface doesn't load

```bash
cd ~/claude-memory-local
source venv/bin/activate
python src/web_ui.py
```

---

## Configuration Files

| File | Purpose |
|------|---------|
| `~/.claude.json` | MCP servers config |
| `~/.claude/settings.json` | Enabled plugins |
| `~/claude-memory-local/.env` | Environment variables |
| `~/claude-memory-local/plugins/hooks/hooks.json` | Hooks config |

---

## License

MIT License - See LICENSE file for details.
