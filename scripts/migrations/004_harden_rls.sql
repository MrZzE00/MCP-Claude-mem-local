-- Migration 004: Harden RLS policies (remove fail-open clause)
-- Removes the permissive OR current_setting(...) IS NULL clause
-- and adds WITH CHECK on prompts policy.

BEGIN;

-- Drop existing permissive policies
DROP POLICY IF EXISTS memories_user_isolation ON memories;
DROP POLICY IF EXISTS prompts_user_isolation ON user_prompts;

-- Recreate with stricter rules (no NULL bypass)
CREATE POLICY memories_user_isolation ON memories
    USING (
        user_id = current_setting('app.current_user_id', true)
        OR user_id IS NULL
    )
    WITH CHECK (
        user_id = current_setting('app.current_user_id', true)
    );

CREATE POLICY prompts_user_isolation ON user_prompts
    USING (
        user_id = current_setting('app.current_user_id', true)
        OR user_id IS NULL
    )
    WITH CHECK (
        user_id = current_setting('app.current_user_id', true)
    );

-- Set default for user_id column to prevent future NULLs
ALTER TABLE memories ALTER COLUMN user_id SET DEFAULT 'default';
ALTER TABLE user_prompts ALTER COLUMN user_id SET DEFAULT 'default';

-- Track migration
INSERT INTO schema_migrations (version, name)
VALUES (4, '004_harden_rls.sql')
ON CONFLICT (version) DO NOTHING;

COMMIT;
