#!/bin/bash
cd /Users/nnadir/claude-memory-local
export PYTHONPATH="/Users/nnadir/claude-memory-local/src:$PYTHONPATH"
exec ./venv/bin/python -m src.server
