#!/bin/bash
# start-server-desktop.sh — Wrapper for Claude Desktop MCP stdio transport
#
# Claude Desktop launches MCP servers via stdio. This script:
#   1. Sets up the environment (loads .env, activates venv)
#   2. Starts the MCP server in stdio mode
#
# Usage in Claude Desktop config:
#   "command": "/Users/nnadir/claude-memory-local/start-server-desktop.sh"

set -euo pipefail

# ── Logging ──────────────────────────────────────────────────────────────
LOG_DIR="/Users/nnadir/claude-memory-local/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/desktop-mcp-$(date +%Y%m%d).log"

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG_FILE"; }

log "Starting MCP server for Claude Desktop"

# ── Environment ──────────────────────────────────────────────────────────
export PATH="/opt/homebrew/bin:$PATH"

# Load .env
if [ -f /Users/nnadir/claude-memory-local/.env ]; then
    set -a
    source /Users/nnadir/claude-memory-local/.env
    set +a
    log "Loaded .env"
fi

# ── Launch ───────────────────────────────────────────────────────────────
cd /Users/nnadir/claude-memory-local
exec /Users/nnadir/claude-memory-local/venv/bin/python -m src.server 2>>"$LOG_FILE"
