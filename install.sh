#!/bin/bash
#
# Claude Memory Local Installation Script
# Installs PostgreSQL via Homebrew (macOS) or native package manager (Linux)
#
# Usage: ./install.sh
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="${CLAUDE_MEMORY_HOME:-$HOME/claude-memory-local}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Database credentials
DB_NAME="claude_memory"
DB_USER="claude"
# Generate a secure random password or use existing from environment
if [ -n "$PG_PASSWORD" ]; then
    DB_PASSWORD="$PG_PASSWORD"
else
    DB_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 32)
fi

echo -e "${BLUE}"
echo "   _____ _                 _        __  __                                   "
echo "  / ____| |               | |      |  \/  |                                  "
echo " | |    | | __ _ _   _  __| | ___  | \  / | ___ _ __ ___   ___  _ __ _   _   "
echo " | |    | |/ _\` | | | |/ _\` |/ _ \ | |\/| |/ _ \ '_ \` _ \ / _ \| '__| | | |  "
echo " | |____| | (_| | |_| | (_| |  __/ | |  | |  __/ | | | | | (_) | |  | |_| |  "
echo "  \_____|_|\__,_|\__,_|\__,_|\___| |_|  |_|\___|_| |_| |_|\___/|_|   \__, |  "
echo "                                                                      __/ |  "
echo "  Local                                                              |___/   "
echo -e "${NC}"
echo "Persistent memory for AI-assisted development"
echo ""

# Functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_command() {
    if ! command -v "$1" &> /dev/null; then
        return 1
    fi
    return 0
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    else
        echo "unknown"
    fi
}

OS=$(detect_os)
log_info "Detected OS: $OS"

# Check prerequisites
log_info "Checking prerequisites..."

# Python check
if ! check_command "python3"; then
    log_error "Python 3 is not installed. Please install it first."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
REQUIRED_VERSION="3.11"
if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    log_error "Python 3.11+ is required. Found: $PYTHON_VERSION"
    exit 1
fi
log_success "Python $PYTHON_VERSION"

# ===========================================
# PostgreSQL Installation (Homebrew)
# ===========================================

if [[ "$OS" == "macos" ]]; then
    # Check Homebrew
    if ! check_command "brew"; then
        log_error "Homebrew is not installed. Install it from https://brew.sh"
        exit 1
    fi
    log_success "Homebrew found"

    # Install PostgreSQL 17 with pgvector
    if ! brew list postgresql@17 &> /dev/null; then
        log_info "Installing PostgreSQL 17..."
        brew install postgresql@17
    else
        log_success "PostgreSQL 17 already installed"
    fi

    # Install pgvector
    if ! brew list pgvector &> /dev/null; then
        log_info "Installing pgvector..."
        brew install pgvector
    else
        log_success "pgvector already installed"
    fi

    # Start PostgreSQL service
    log_info "Starting PostgreSQL service..."
    brew services start postgresql@17 || true
    sleep 3

    # Add PostgreSQL to PATH if needed
    PG_BIN="/opt/homebrew/opt/postgresql@17/bin"
    if [[ -d "$PG_BIN" ]] && [[ ":$PATH:" != *":$PG_BIN:"* ]]; then
        export PATH="$PG_BIN:$PATH"
        log_info "Added PostgreSQL to PATH"
    fi

elif [[ "$OS" == "linux" ]]; then
    log_info "Installing PostgreSQL on Linux..."

    if check_command "apt-get"; then
        sudo apt-get update
        sudo apt-get install -y postgresql postgresql-contrib
        # pgvector needs to be compiled or installed from a PPA
        log_warning "pgvector may need manual installation on Linux. See: https://github.com/pgvector/pgvector"
    elif check_command "dnf"; then
        sudo dnf install -y postgresql-server postgresql-contrib
    else
        log_error "Unsupported package manager. Please install PostgreSQL manually."
        exit 1
    fi

    sudo systemctl start postgresql
    sudo systemctl enable postgresql
else
    log_error "Unsupported OS: $OS"
    exit 1
fi

# Wait for PostgreSQL to be ready
log_info "Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if pg_isready -q 2>/dev/null; then
        break
    fi
    sleep 1
done

if ! pg_isready -q 2>/dev/null; then
    log_error "PostgreSQL failed to start"
    exit 1
fi
log_success "PostgreSQL is ready"

# ===========================================
# Database Setup
# ===========================================

log_info "Setting up database..."

# Create user if not exists
if ! psql -U postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" 2>/dev/null | grep -q 1; then
    log_info "Creating database user '$DB_USER'..."
    createuser -s "$DB_USER" 2>/dev/null || psql -c "CREATE USER $DB_USER WITH SUPERUSER;" 2>/dev/null || true
fi

# Set password
psql -c "ALTER USER $DB_USER PASSWORD '$DB_PASSWORD';" 2>/dev/null || \
psql -U postgres -c "ALTER USER $DB_USER PASSWORD '$DB_PASSWORD';" 2>/dev/null || true

# Create database if not exists
if ! psql -U "$DB_USER" -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
    log_info "Creating database '$DB_NAME'..."
    createdb -O "$DB_USER" "$DB_NAME" 2>/dev/null || \
    psql -U postgres -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || true
fi

log_success "Database user and database ready"

# Enable pgvector extension and create schema
log_info "Initializing database schema..."
psql -U "$DB_USER" -d "$DB_NAME" << 'EOSQL'
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Memories table
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    summary TEXT,
    category VARCHAR(50) NOT NULL CHECK (category IN (
        'learning', 'pattern', 'preference', 'error_solution',
        'decision', 'bugfix', 'feature', 'discovery', 'refactor', 'change'
    )),
    tags TEXT[] DEFAULT '{}',
    project_context VARCHAR(500),
    embedding vector(768),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_accessed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    access_count INTEGER DEFAULT 0,
    importance_score FLOAT DEFAULT 0.5 CHECK (importance_score >= 0 AND importance_score <= 1),
    visibility VARCHAR(20) DEFAULT 'private' CHECK (visibility IN ('private', 'team', 'public'))
);

-- User prompts table
CREATE TABLE IF NOT EXISTS user_prompts (
    id SERIAL PRIMARY KEY,
    session_id TEXT,
    prompt_number INTEGER,
    prompt_text TEXT NOT NULL,
    project_context VARCHAR(500),
    embedding vector(768),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_context);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance_score DESC);
CREATE INDEX IF NOT EXISTS idx_memories_tags ON memories USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_prompts_embedding ON user_prompts USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_prompts_session ON user_prompts(session_id);
CREATE INDEX IF NOT EXISTS idx_prompts_created ON user_prompts(created_at DESC);

-- Views for statistics
CREATE OR REPLACE VIEW memory_stats AS
SELECT
    COUNT(*) as total_memories,
    COUNT(DISTINCT category) as categories_used,
    COUNT(DISTINCT project_context) as projects,
    AVG(importance_score) as avg_importance,
    MAX(created_at) as last_memory_at
FROM memories;

CREATE OR REPLACE VIEW category_stats AS
SELECT
    category,
    COUNT(*) as count,
    AVG(importance_score) as avg_importance,
    MAX(created_at) as last_at
FROM memories
GROUP BY category
ORDER BY count DESC;
EOSQL

log_success "Database schema initialized"

# ===========================================
# Ollama Installation
# ===========================================

if ! check_command "ollama"; then
    log_info "Installing Ollama..."
    if [[ "$OS" == "macos" ]]; then
        brew install ollama
    else
        curl -fsSL https://ollama.com/install.sh | sh
    fi
fi
log_success "Ollama found"

# Start Ollama if not running
if ! pgrep -x "ollama" > /dev/null; then
    log_info "Starting Ollama..."
    if [[ "$OS" == "macos" ]]; then
        # Check if Ollama.app exists and use it
        if [[ -d "/Applications/Ollama.app" ]]; then
            open -a Ollama
        else
            ollama serve &
        fi
    else
        ollama serve &
    fi
    sleep 5
fi

# Download embedding model
log_info "Downloading embedding model (nomic-embed-text)..."
ollama pull nomic-embed-text
log_success "Embedding model ready"

# ===========================================
# Install Python Dependencies
# ===========================================

log_info "Setting up Python environment..."
mkdir -p "$INSTALL_DIR"

# Copy files from repo
if [[ -d "$REPO_DIR/src" ]]; then
    cp -r "$REPO_DIR/src" "$INSTALL_DIR/"
    cp -r "$REPO_DIR/plugins" "$INSTALL_DIR/" 2>/dev/null || true
    cp "$REPO_DIR/viewer.html" "$INSTALL_DIR/" 2>/dev/null || true
    cp "$REPO_DIR/requirements.txt" "$INSTALL_DIR/" 2>/dev/null || true
fi

cd "$INSTALL_DIR"

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip

# Install dependencies
if [[ -f "requirements.txt" ]]; then
    pip install -r requirements.txt
else
    pip install mcp asyncpg httpx python-dotenv
fi

log_success "Python environment ready"

# ===========================================
# Create Configuration Files
# ===========================================

log_info "Creating configuration..."

# Create .env file
cat > "$INSTALL_DIR/.env" << EOF
# Claude Memory Local Configuration

# PostgreSQL (Homebrew)
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=$DB_NAME
PG_USER=$DB_USER
PG_PASSWORD=$DB_PASSWORD

# Ollama
OLLAMA_HOST=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768

# Web UI
WEB_PORT=8080
EOF

log_success "Configuration created at $INSTALL_DIR/.env"

# Create start script
cat > "$INSTALL_DIR/start-server.sh" << EOF
#!/bin/bash
cd "$INSTALL_DIR"
source venv/bin/activate
python src/server.py
EOF
chmod +x "$INSTALL_DIR/start-server.sh"

# Create context injection script
cat > "$INSTALL_DIR/claude-context.sh" << EOF
#!/bin/bash
cd "\${1:-.}"
"$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/plugins/scripts/context-hook.py" session-start
EOF
chmod +x "$INSTALL_DIR/claude-context.sh"

# ===========================================
# Configure Claude Code
# ===========================================

log_info "Configuring Claude Code..."

CLAUDE_CONFIG="$HOME/.claude.json"
if [[ -f "$CLAUDE_CONFIG" ]]; then
    cp "$CLAUDE_CONFIG" "$CLAUDE_CONFIG.backup"

    if grep -q '"claude-memory-local"' "$CLAUDE_CONFIG"; then
        log_warning "claude-memory-local already configured in Claude Code"
    else
        log_info "Adding claude-memory-local to Claude Code configuration..."
        python3 << PYEOF
import json

with open("$CLAUDE_CONFIG", "r") as f:
    config = json.load(f)

if "mcpServers" not in config:
    config["mcpServers"] = {}

config["mcpServers"]["claude-memory-local"] = {
    "type": "stdio",
    "command": "$INSTALL_DIR/start-server.sh",
    "args": []
}

with open("$CLAUDE_CONFIG", "w") as f:
    json.dump(config, f, indent=2)

print("Claude Code configuration updated")
PYEOF
    fi
else
    cat > "$CLAUDE_CONFIG" << EOF
{
  "mcpServers": {
    "claude-memory-local": {
      "type": "stdio",
      "command": "$INSTALL_DIR/start-server.sh",
      "args": []
    }
  }
}
EOF
fi

log_success "Claude Code configured"

# ===========================================
# Test Connection
# ===========================================

log_info "Testing database connection..."
cd "$INSTALL_DIR"
source venv/bin/activate
python3 << PYEOF
import asyncio
import asyncpg

async def test():
    try:
        conn = await asyncpg.connect(
            host='localhost', port=5432,
            database='$DB_NAME', user='$DB_USER', password='$DB_PASSWORD'
        )
        result = await conn.fetchval('SELECT COUNT(*) FROM memories')
        print(f'✅ Connection OK! {result} memories in database.')
        await conn.close()
    except Exception as e:
        print(f'❌ Connection failed: {e}')
        exit(1)

asyncio.run(test())
PYEOF

# ===========================================
# Print Summary
# ===========================================

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}   Claude Memory Local installed successfully!  ${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "Installation directory: $INSTALL_DIR"
echo ""
echo -e "${YELLOW}Database credentials (saved to .env):${NC}"
echo "  User: $DB_USER"
echo "  Database: $DB_NAME"
echo -e "  Password: ${YELLOW}$DB_PASSWORD${NC}"
echo ""
echo -e "${RED}IMPORTANT: Save this password securely! It won't be shown again.${NC}"
echo ""
echo "Services:"
echo "  • PostgreSQL 17: localhost:5432 (auto-starts on boot)"
echo "  • Ollama: localhost:11434 (manual start required)"
echo ""
echo -e "${YELLOW}IMPORTANT - After a system reboot:${NC}"
echo "  PostgreSQL starts automatically (via brew services)"
echo "  Ollama must be started manually:"
echo "    open -a Ollama     # or: ollama serve &"
echo ""
echo "  This is intentional to keep human control over AI processes."
echo ""
echo "Usage:"
echo "  1. Restart Claude Code"
echo "  2. The 'claude-memory-local' MCP server should appear in /mcp"
echo ""
echo "MCP Tools:"
echo "  store_memory      - Store a new memory"
echo "  retrieve_memories - Search memories semantically"
echo "  list_memories     - List recent memories"
echo "  memory_stats      - View statistics"
echo "  delete_memory     - Delete a memory"
echo ""
echo "Web UI:"
echo "  cd $INSTALL_DIR && python3 -m http.server 8080"
echo "  Open: http://localhost:8080/viewer.html"
echo ""
echo "Context injection:"
echo "  $INSTALL_DIR/claude-context.sh /path/to/project"
echo ""
echo -e "${BLUE}Documentation: https://github.com/your-org/claude-memory-local${NC}"
echo ""
