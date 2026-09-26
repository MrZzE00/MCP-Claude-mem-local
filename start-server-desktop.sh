#!/bin/bash
# start-server-desktop.sh — Wrapper for Claude Desktop MCP stdio transport
#
# Claude Desktop launches MCP servers via stdio. This script:
#   1. Sets up the environment (loads .env, activates venv)
#   2. Starts the MCP server in stdio mode
#
# Usage in Claude Desktop config:
#   "command": "/absolute/path/to/claude-memory-local/start-server-desktop.sh"

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Logging ──────────────────────────────────────────────────────────────
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/desktop-mcp-$(date +%Y%m%d).log"

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG_FILE"; }

log "Starting MCP server for Claude Desktop"

# ── Environment ──────────────────────────────────────────────────────────
export PATH="/opt/homebrew/bin:$PATH"

# Load .env
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
    log "Loaded .env"
fi

# ── Launch ───────────────────────────────────────────────────────────────
cd "$PROJECT_DIR"
exec "$PROJECT_DIR/venv/bin/python" -m src.server 2>>"$LOG_FILE"
