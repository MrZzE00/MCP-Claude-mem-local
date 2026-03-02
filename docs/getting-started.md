# Getting Started with MCP-Claude-mem-local

This guide will help you install and configure MCP-Claude-mem-local for your development workflow.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Install](#quick-install)
3. [Manual Installation](#manual-installation)
4. [Configuration](#configuration)
5. [First Steps](#first-steps)
6. [Integrating with Your Project](#integrating-with-your-project)

---

## Prerequisites

Before installing MCP-Claude-mem-local, ensure you have:

| Requirement | Version | Check Command |
|-------------|---------|---------------|
| **Homebrew** | Latest | `brew --version` |
| **Python** | 3.11+ | `python3 --version` |
| **Ollama** | 0.15+ | `ollama --version` |
| **Claude Code** | Latest | - |

### Installing Prerequisites

#### Homebrew (macOS)
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### Python 3.11+
```bash
# macOS
brew install python@3.13

# Linux
sudo apt install python3.11
```

#### Ollama
```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh
```

---

## Quick Install

The fastest way to get started:

```bash
# Clone the repository
git clone https://github.com/your-org/claude-memory-local.git
cd claude-memory-local

# Run the installer
./install.sh
```

The installer will:
1. ✅ Check prerequisites
2. ✅ Install PostgreSQL 17 + pgvector via Homebrew
3. ✅ Create Python virtual environment
4. ✅ Initialize database schema
5. ✅ Download embedding model (nomic-embed-text)
6. ✅ Configure Claude Code MCP server

After installation, **restart Claude Code** and the `claude-memory-local` MCP server will be available.

---

## Manual Installation

If you prefer to install step by step:

### Step 1: Install PostgreSQL with pgvector

```bash
# macOS with Homebrew
brew install postgresql@17 pgvector

# Start PostgreSQL service
brew services start postgresql@17
```

### Step 2: Create Database and User

```bash
# Create user
createuser -s claude

# Set a secure password (generate one with: openssl rand -base64 32)
psql -c "ALTER USER claude PASSWORD 'YOUR_SECURE_PASSWORD';"

# Create database
createdb -O claude claude_memory

# Enable pgvector extension
psql -d claude_memory -c "CREATE EXTENSION vector;"
```

### Step 3: Initialize Schema

```bash
psql -U claude -d claude_memory << 'EOSQL'
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    summary TEXT,
    category VARCHAR(50) NOT NULL,
    tags TEXT[] DEFAULT '{}',
    project_context VARCHAR(500),
    embedding vector(768),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_accessed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    access_count INTEGER DEFAULT 0,
    importance_score FLOAT DEFAULT 0.5
);

CREATE TABLE IF NOT EXISTS user_prompts (
    id SERIAL PRIMARY KEY,
    session_id TEXT,
    prompt_number INTEGER,
    prompt_text TEXT NOT NULL,
    project_context VARCHAR(500),
    embedding vector(768),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_memories_category ON memories(category);
CREATE INDEX idx_prompts_embedding ON user_prompts USING hnsw (embedding vector_cosine_ops);
EOSQL
```

### Step 4: Setup Python Environment

```bash
mkdir -p ~/claude-memory-local
cd ~/claude-memory-local

python3 -m venv venv
source venv/bin/activate
pip install mcp asyncpg httpx python-dotenv
```

### Step 5: Download Embedding Model

```bash
ollama pull nomic-embed-text
```

### Step 6: Create Configuration

Copy `.env.example` to `.env` and configure your credentials:

```bash
cp ~/claude-memory-local/.env.example ~/claude-memory-local/.env
# Edit .env with your secure password
```

Or create manually:

```bash
cat > ~/claude-memory-local/.env << 'EOF'
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=claude_memory
PG_USER=claude
PG_PASSWORD=YOUR_SECURE_PASSWORD    # Generate with: openssl rand -base64 32
OLLAMA_HOST=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text

# Security (optional)
API_KEY=                            # Set to require API authentication
RATE_LIMIT_REQUESTS=60
ALLOWED_ORIGINS=localhost:8080
EOF
```

> ⚠️ **Security**: Never commit `.env` with real credentials.

### Step 7: Copy Server Files

Copy `src/server.py` from the repository to `~/claude-memory-local/src/`.

### Step 8: Configure Claude Code

Edit `~/.claude.json`:

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

### Step 9: Verify Installation

```bash
# Test database connection
psql -U claude -d claude_memory -c "SELECT 1;"

# Test Python environment
cd ~/claude-memory-local && source venv/bin/activate
python -c "import asyncpg, httpx, mcp; print('Dependencies OK')"
```

---

## Configuration

### Environment Variables

Edit `~/claude-memory-local/.env` (see `.env.example` for all options):

```bash
# Database (Homebrew PostgreSQL)
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=claude_memory
PG_USER=claude
PG_PASSWORD=YOUR_SECURE_PASSWORD    # Generate with: openssl rand -base64 32

# Ollama
OLLAMA_HOST=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text

# Security (optional)
API_KEY=                            # Enable API key authentication
RATE_LIMIT_REQUESTS=60              # Rate limiting
ALLOWED_ORIGINS=localhost:8080      # CORS
```

### Security Best Practices

1. **Use strong passwords**: Generate with `openssl rand -base64 32`
2. **Never commit `.env`**: Add to `.gitignore`
3. **Enable API key** for production: Set `API_KEY` in `.env`
4. **Review CORS settings**: Restrict `ALLOWED_ORIGINS` to necessary hosts

### Claude Code Configuration

Your `~/.claude.json` should include:

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

### Configuration for Other IDEs

The MCP server uses the **stdio transport** (standard MCP protocol), making it compatible with all MCP-enabled tools.

#### GitHub Copilot (VS Code)

Create `.vscode/mcp.json` in your workspace:
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

#### Cursor

Add to `~/.cursor/mcp.json`:
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

#### JetBrains (IntelliJ, WebStorm, PyCharm)

1. Settings → Tools → MCP Servers
2. Add Server → Type: stdio
3. Command: `~/claude-memory-local/start-server.sh`

#### Antigravity

1. Settings → MCP Servers → Add Custom Server
2. Type: stdio
3. Command: `~/claude-memory-local/start-server.sh`

#### VS Code (with MCP extension)

Add to `settings.json`:
```json
{
  "mcp.servers": {
    "claude-memory-local": {
      "type": "stdio",
      "command": "~/claude-memory-local/start-server.sh"
    }
  }
}
```

> **Note**: The hooks system (auto-capture prompts, CLAUDE.md injection) is specific to Claude Code. Other IDEs will use the MCP tools directly without automation hooks.

---

## First Steps

### 1. Verify Connection

In Claude Code, check that MCP-Claude-mem-local is connected:

```
/mcp
```

You should see `claude-memory-local · ✔ connected`.

### 2. Store Your First Memory

Ask Claude:

```
Store a memory: "MCP-Claude-mem-local successfully installed and configured"
with category "discovery" and tags ["setup", "initial"]
```

Or use the tool directly:

```
store_memory({
  content: "MCP-Claude-mem-local successfully installed and configured",
  category: "discovery",
  tags: ["setup", "initial"]
})
```

### 3. Retrieve Memories

```
retrieve_memories({ query: "installation" })
```

### 4. View Statistics

```
memory_stats()
```

### 5. Launch Web UI

```bash
cd ~/claude-memory-local && python3 -m http.server 8080
```

Open: http://localhost:8080/viewer.html

---

## Integrating with Your Project

### Add CLAUDE.md to Your Project

Copy `CLAUDE.md.example` from the `docs/` folder to your project root and customize it:

```bash
cp ~/claude-memory-local/docs/CLAUDE.md.example /your/project/CLAUDE.md
```

### Per-Folder Context

When storing memories with a `project` path, the memory is associated with that project.

**CLAUDE.md is updated via hooks**, not directly by `store_memory`:
- The `context-hook.py` script runs on `SessionStart`, `PostToolUse`, and `Stop`
- It reads memories for the current project from PostgreSQL
- It injects a context block into the project's `CLAUDE.md`

```typescript
store_memory({
  content: "Fixed authentication bug in login component",
  category: "bugfix",
  project: "/path/to/your/project"  // <-- Associates memory with project
})
```

On the next hook trigger, this creates or updates a context block in your project's `CLAUDE.md`:

```markdown
<claude-memory-local-context>
# Recent Activity - /path/to/your/project

| Time | Type | Summary |
|------|------|---------|
| 02/03 10:44 | 🔴 bugfix | Fixed authentication bug... |

</claude-memory-local-context>
```

### Workflow Rules

Add to your `CLAUDE.md`:

```markdown
## Memory Workflow

- **Start of session**: `retrieve_memories` for relevant context
- **After bugfix**: `store_memory` with category="bugfix"
- **After decision**: `store_memory` with category="decision"
- **End of session**: `store_memory` for key learnings

### Categories

| Category | When to Use |
|----------|-------------|
| `bugfix` | After fixing a bug |
| `decision` | Architectural decisions |
| `feature` | New feature implemented |
| `discovery` | Learning something new |
| `refactor` | Code restructuring |
| `change` | General modifications |
| `pattern` | Reusable pattern identified |
| `preference` | User preference |
| `learning` | Lesson learned |
| `error_solution` | Solution to specific error |
```

---

## Next Steps

- Read the [API Reference](api-reference.md) for all available tools
- Check [Configuration](configuration.md) for advanced options
- See [Troubleshooting](troubleshooting.md) if you encounter issues

---

## Need Help?

- Open an [issue on GitHub](https://github.com/your-org/claude-memory-local/issues)
- Start a [discussion](https://github.com/your-org/claude-memory-local/discussions)
