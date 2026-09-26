#!/bin/bash
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
export PYTHONPATH="$PROJECT_DIR/src:$PYTHONPATH"
exec ./venv/bin/python -m src.server
