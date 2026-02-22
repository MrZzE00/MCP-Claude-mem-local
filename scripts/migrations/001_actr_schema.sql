-- Migration 001: ACT-R Cognitive Scoring Schema
-- Adds columns for ACT-R activation-based memory scoring
-- Safe to run on existing databases with data

BEGIN;

-- 1. Add access_timestamps array column
ALTER TABLE memories ADD COLUMN IF NOT EXISTS access_timestamps TIMESTAMP WITH TIME ZONE[] DEFAULT '{}';

-- 2. Add memory status column (active/dormant/forgotten)
-- Use DO block since ADD COLUMN IF NOT EXISTS doesn't support CHECK constraints well
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'memories' AND column_name = 'memory_status') THEN
        ALTER TABLE memories ADD COLUMN memory_status VARCHAR(10) DEFAULT 'active';
        ALTER TABLE memories ADD CONSTRAINT check_memory_status CHECK (memory_status IN ('active', 'dormant', 'forgotten'));
    END IF;
END $$;

-- 3. Add cached activation score
ALTER TABLE memories ADD COLUMN IF NOT EXISTS actr_activation FLOAT;

-- 4. Add activation cache timestamp
ALTER TABLE memories ADD COLUMN IF NOT EXISTS activation_updated_at TIMESTAMP WITH TIME ZONE;

-- 5. Migrate existing access_count data to synthetic timestamps
-- For each memory with access_count > 0, generate N timestamps
-- evenly spaced between created_at and last_accessed_at
DO $$
DECLARE
    rec RECORD;
    ts_array TIMESTAMP WITH TIME ZONE[];
    interval_step INTERVAL;
    i INTEGER;
BEGIN
    FOR rec IN
        SELECT id, access_count, created_at, last_accessed_at
        FROM memories
        WHERE access_count > 0
          AND (access_timestamps IS NULL OR array_length(access_timestamps, 1) IS NULL)
    LOOP
        ts_array := '{}';
        IF rec.access_count = 1 THEN
            ts_array := ARRAY[COALESCE(rec.last_accessed_at, rec.created_at)];
        ELSE
            interval_step := (COALESCE(rec.last_accessed_at, NOW()) - rec.created_at) / GREATEST(rec.access_count - 1, 1);
            FOR i IN 0..rec.access_count - 1 LOOP
                ts_array := array_append(ts_array, rec.created_at + (interval_step * i));
            END LOOP;
        END IF;

        UPDATE memories SET access_timestamps = ts_array WHERE id = rec.id;
    END LOOP;
END $$;

-- 6. Set all existing memories to 'active' status
UPDATE memories SET memory_status = 'active' WHERE memory_status IS NULL;

-- 7. Index for memory_status filtering
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(memory_status);

-- 8. Index for GIN on access_timestamps (for array operations)
CREATE INDEX IF NOT EXISTS idx_memories_access_timestamps ON memories USING GIN (access_timestamps);

-- 9. Migration version tracking table
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Record this migration
INSERT INTO schema_migrations (version, name) VALUES (1, '001_actr_schema')
ON CONFLICT (version) DO NOTHING;

COMMIT;
