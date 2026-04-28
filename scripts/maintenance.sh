#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "[$(date)] Maintenance start"

# Vacuum SQLite database
if [ -f data/memories.db ]; then
    ./venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('data/memories.db')
conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
conn.execute('VACUUM')
conn.close()
print('Database vacuumed successfully')
"
fi

# Rotate logs > 10MB
for log in logs/*.log; do
    if [ -f "$log" ] && [ "$(stat -f%z "$log" 2>/dev/null || echo 0)" -gt 10485760 ]; then
        mv "$log" "${log}.old"
        echo "Rotated: $log"
    fi
done

echo "[$(date)] Maintenance done"
