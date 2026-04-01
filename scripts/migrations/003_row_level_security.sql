-- Migration 003: Row Level Security for multi-user isolation
-- Adds user_id/team_id columns if missing, enables RLS with user_id-based policies.

BEGIN;

-- Add user_id and team_id columns if they don't exist
ALTER TABLE memories ADD COLUMN IF NOT EXISTS user_id VARCHAR(255);
ALTER TABLE memories ADD COLUMN IF NOT EXISTS team_id VARCHAR(255);
ALTER TABLE user_prompts ADD COLUMN IF NOT EXISTS user_id VARCHAR(255);

-- Create indexes for user isolation
CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_team ON memories(team_id);

-- Backfill NULL user_id with 'default'
UPDATE memories SET user_id = 'default' WHERE user_id IS NULL;
UPDATE user_prompts SET user_id = 'default' WHERE user_id IS NULL;

-- Enable Row Level Security
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_prompts ENABLE ROW LEVEL SECURITY;

-- Policy: users can only see/modify their own memories (or unassigned ones)
CREATE POLICY memories_user_isolation ON memories
    USING (
        user_id = current_setting('app.current_user_id', true)
        OR user_id IS NULL
        OR current_setting('app.current_user_id', true) IS NULL
    )
    WITH CHECK (
        user_id = current_setting('app.current_user_id', true)
        OR current_setting('app.current_user_id', true) IS NULL
    );

CREATE POLICY prompts_user_isolation ON user_prompts
    USING (
        user_id = current_setting('app.current_user_id', true)
        OR user_id IS NULL
        OR current_setting('app.current_user_id', true) IS NULL
    );

-- Track migration
INSERT INTO schema_migrations (version, name)
VALUES (3, '003_row_level_security.sql')
ON CONFLICT (version) DO NOTHING;

COMMIT;
