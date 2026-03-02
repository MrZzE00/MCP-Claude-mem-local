<div align="center">

# claude-memory-local

**Persistent local memory for AI coding assistants — zero cloud tokens, 100% private.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![MCP Server](https://img.shields.io/badge/MCP-Server-blue)](https://modelcontextprotocol.io)
[![pgvector](https://img.shields.io/badge/pgvector-semantic_search-orange)](https://github.com/pgvector/pgvector)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[Quick Start](#quick-start) · [MCP Tools](#mcp-tools) · [How It Works](#how-it-works) · [Configuration](#configuration) · [Documentation](#documentation)

</div>

---

## The Problem

AI coding assistants forget everything between sessions. Architecture decisions, resolved bugs, proven patterns — gone. Every new session starts from zero. Developers repeat explanations, re-discover solutions, and lose the institutional knowledge that makes teams effective.

## The Solution

**claude-memory-local** is a persistent memory system that runs entirely on your machine. Every decision, bugfix, and pattern is stored locally in PostgreSQL with semantic search powered by pgvector. Embeddings are generated locally with Ollama — **zero tokens sent to any cloud API**.

Your team's knowledge compounds across sessions instead of evaporating.

---

## Features

- **Semantic Search** — Find memories by meaning, not just keywords (pgvector + cosine similarity)
- **ACT-R Cognitive Scoring** — Memories ranked like human cognition: frequent access rises, unused fades
- **100% Local & Private** — PostgreSQL + Ollama on your machine, no data leaves your network
- **Zero Token Cost** — Embeddings via local Ollama, no API calls consumed
- **6 MCP Tools** — Store, retrieve, list, stats, delete, and forgetting cycle
- **Automatic Prompt Capture** — Every prompt you submit is indexed for semantic search
- **CLAUDE.md Injection** — Recent memories auto-injected into project context via hooks
- **Web Interface** — Browse, search, and filter memories in your browser
- **Multi-IDE Support** — Works with Claude Code, Cursor, VS Code, JetBrains, and more
- **Strategic Forgetting** — Old unused memories fade gracefully without deletion

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/your-org/claude-memory-local.git
cd claude-memory-local
./install.sh
```

The installer handles PostgreSQL 17 + pgvector, Python venv, database schema, Ollama, and embedding model.

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your PostgreSQL password (generate one: openssl rand -base64 32)
```

### 3. Add MCP server to your IDE

Add to `~/.claude.json`:

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

### 4. Start Ollama

```bash
open -a Ollama        # macOS app
# or: ollama serve &  # command line
```

> PostgreSQL auto-starts via Homebrew. Ollama requires manual start — a deliberate choice to keep human control over AI processes.

### 5. Restart your IDE and test

```
store_memory({ content: "Test memory", category: "discovery" })
retrieve_memories({ query: "test" })
```

---

## MCP Tools

| Tool | Description | Example |
|------|-------------|---------|
| **`store_memory`** | Store a memory with category, tags, importance | `store_memory({ content: "Fixed auth bug by...", category: "bugfix", tags: ["auth"], importance: 0.9 })` |
| **`retrieve_memories`** | Semantic search across memories | `retrieve_memories({ query: "authentication flow", max_results: 5 })` |
| **`list_memories`** | List recent memories, optionally filtered | `list_memories({ limit: 20, category: "decision" })` |
| **`memory_stats`** | Get statistics: totals, distribution, trends | `memory_stats()` |
| **`delete_memory`** | Remove a specific memory by ID | `delete_memory({ memory_id: "uuid" })` |
| **`memory_forgetting_cycle`** | Run ACT-R decay cycle across all memories | `memory_forgetting_cycle()` |

### Memory Categories

| Category | Icon | Use for |
|----------|------|---------|
| `bugfix` | 🔴 | Bug fixes and their solutions |
| `decision` | 🟠 | Architecture and design decisions |
| `feature` | 🟢 | New functionality implemented |
| `discovery` | 🔵 | Learnings and discoveries |
| `refactor` | 🟣 | Refactoring notes |
| `change` | ⚪ | General changes |
| `pattern` | 🟤 | Reusable patterns identified |
| `preference` | 🟡 | User/team preferences |
| `learning` | 📘 | Lessons learned |
| `error_solution` | 🩹 | Specific error solutions |

---

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                      Claude Code (or any MCP client)        │
│                          │                                  │
│                    ┌─────▼─────┐                            │
│                    │ MCP Server │ (6 tools)                 │
│                    └─────┬─────┘                            │
│                          │                                  │
│         ┌────────────────┼────────────────┐                 │
│         ▼                ▼                ▼                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ PostgreSQL  │  │   Ollama    │  │   Hooks     │        │
│  │ + pgvector  │  │ (embeddings)│  │ (automation) │        │
│  └──────┬──────┘  └─────────────┘  └──────┬──────┘        │
│         ▼                                  ▼               │
│  ┌─────────────┐                   ┌─────────────┐        │
│  │  memories   │                   │  CLAUDE.md  │        │
│  │  (table)    │                   │ (per-project)│        │
│  └─────────────┘                   └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

| Component | Role | Auto-start |
|-----------|------|------------|
| **PostgreSQL 17 + pgvector** | Memory storage + vector search | Yes (Homebrew) |
| **Ollama** | Local embedding generation (nomic-embed-text) | No (manual) |
| **MCP Server** | Interface with AI coding assistants (6 tools) | Via IDE |
| **Hooks** | Auto-capture prompts + inject context into CLAUDE.md | Via config |
| **Web Interface** | Browse and search memories | Manual |

---

## ACT-R Cognitive Scoring

Memory retrieval uses the [ACT-R cognitive architecture](https://en.wikipedia.org/wiki/ACT-R), ranking memories like human cognition rather than raw cosine similarity:

```
Activation(m) = Base-level(m) + Weight × Similarity + Spreading(m) + Noise
```

| Component | What it does |
|-----------|-------------|
| **Base-level** | Frequently accessed memories score higher; unused ones decay over time |
| **Similarity** | Semantic match between your query and the memory |
| **Spreading** | Shared tags boost contextually related memories |
| **Noise** | Small random factor prevents static ranking bias |

Memories transition through three states: **Active** → **Dormant** → **Forgotten** (never deleted).

<details>
<summary><strong>ACT-R configuration variables</strong></summary>

```env
USE_ACTR_SCORING=true       # Master switch (false = cosine-only scoring)
ACTR_DECAY_D=0.5            # Power-law decay rate
ACTR_WEIGHT_W=11.0          # Semantic similarity weight
ACTR_NOISE_SIGMA=1.2        # Gaussian noise standard deviation
ACTR_THRESHOLD_TAU=-2.0     # Retrieval threshold
ACTR_SPREADING_S=2.0        # Spreading activation strength
```

</details>

See [docs/MIGRATION.md](docs/MIGRATION.md) for upgrade instructions from v1 (cosine-only) to v2 (ACT-R).

---

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

```env
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=claude_memory
PG_USER=claude
PG_PASSWORD=YOUR_SECURE_PASSWORD    # Generate: openssl rand -base64 32
OLLAMA_HOST=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text
```

<details>
<summary><strong>Optional security settings</strong></summary>

```env
API_KEY=                            # Set to require API key authentication
RATE_LIMIT_REQUESTS=60              # Requests per minute (default: 60)
RATE_LIMIT_WINDOW=60                # Rate limit window in seconds
ALLOWED_ORIGINS=localhost:8080      # CORS allowed origins
```

</details>

### MCP Setup by IDE

<details>
<summary><strong>Claude Code</strong> (~/.claude.json)</summary>

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

</details>

<details>
<summary><strong>GitHub Copilot / VS Code</strong> (.vscode/mcp.json)</summary>

```json
{
  "mcp": {
    "servers": {
      "claude-memory-local": {
        "type": "stdio",
        "command": "~/claude-memory-local/start-server.sh"
      }
    }
  }
}
```

</details>

<details>
<summary><strong>Cursor</strong> (~/.cursor/mcp.json)</summary>

```json
{
  "mcpServers": {
    "claude-memory-local": {
      "command": "~/claude-memory-local/start-server.sh",
      "args": []
    }
  }
}
```

</details>

<details>
<summary><strong>JetBrains (IntelliJ, WebStorm, PyCharm)</strong></summary>

1. Settings → Tools → MCP Servers
2. Add Server → Type: stdio
3. Command: `~/claude-memory-local/start-server.sh`

</details>

<details>
<summary><strong>Windsurf / Other MCP clients</strong></summary>

The server uses the standard **stdio transport** (MCP protocol). Point your MCP client to:

```
~/claude-memory-local/start-server.sh
```

</details>

> **Note**: The hooks system (auto-capture prompts, CLAUDE.md injection) is specific to Claude Code. Other IDEs use the MCP tools directly without automation hooks.

---

## Hooks & Automation

The hooks system provides two automations for Claude Code:

1. **Prompt Capture** — Every prompt you submit is automatically embedded and stored for semantic search
2. **CLAUDE.md Injection** — Recent memories are injected into your project's `CLAUDE.md` at session start, after edits, and at session end

See [docs/hooks-prompts-capture.md](docs/hooks-prompts-capture.md) for setup instructions and hook configuration.

---

## Web Interface

Browse, search, and filter your memories in the browser:

```bash
cd ~/claude-memory-local && python3 -m http.server 8080
# Open http://localhost:8080/viewer.html
```

Features: global stats, text search, category filters, project filters, prompts history tab.

---

## Troubleshooting

**MCP server doesn't connect**
```bash
pg_isready              # Check PostgreSQL
ollama list             # Check Ollama
```

**PostgreSQL doesn't start**
```bash
lsof -i :5432                      # Check port conflict
brew services restart postgresql@17 # Restart service
```

**Error "role claude does not exist"**
```bash
createuser -s claude
psql -c "ALTER USER claude PASSWORD 'YOUR_PASSWORD';"
# Update .env with the same password
```

**Web interface doesn't load**
```bash
cd ~/claude-memory-local && source venv/bin/activate && python src/web_ui.py
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [Getting Started](docs/getting-started.md) | Detailed onboarding guide |
| [Technical Reference](docs/MCP-Claude-mem-local-Documentation-Technique.md) | Full technical documentation |
| [Hooks & Prompt Capture](docs/hooks-prompts-capture.md) | Hook system setup and configuration |
| [Migration Guide](docs/MIGRATION.md) | Upgrading from v1 to v2 (ACT-R) |
| [Agent Template](docs/AGENTS-TEMPLATE.md) | Template for configuring AI agents |

---

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

---

## License

[MIT](LICENSE)
