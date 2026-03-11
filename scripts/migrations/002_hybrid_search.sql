-- Migration 002: Hybrid Search (trigram indexes for text-based search)
-- This migration is purely additive: no DELETE, DROP, ALTER, or TRUNCATE.

BEGIN;

-- Enable pg_trgm for trigram similarity search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Trigram indexes for fuzzy text matching on content and summary
CREATE INDEX IF NOT EXISTS idx_memories_content_trgm
    ON memories USING gin (content gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_memories_summary_trgm
    ON memories USING gin (summary gin_trgm_ops);

-- Record migration
INSERT INTO schema_migrations (version, name)
    VALUES (2, '002_hybrid_search')
    ON CONFLICT (version) DO NOTHING;

COMMIT;
