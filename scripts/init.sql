-- Synaptic Database Initialization
-- This script runs automatically when PostgreSQL container starts

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Memories table
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Content
    content TEXT NOT NULL,
    summary TEXT,
    
    -- Classification
    category VARCHAR(50) NOT NULL,
    tags TEXT[],
    project_context VARCHAR(255),
    
    -- Embedding vector (768 dimensions for nomic-embed-text)
    embedding vector(768),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_accessed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Usage statistics
    access_count INTEGER DEFAULT 0,
    importance_score FLOAT DEFAULT 0.5,
    
    -- Team collaboration (future)
    user_id VARCHAR(255),
    team_id VARCHAR(255),
    visibility VARCHAR(20) DEFAULT 'personal',
    
    -- Constraints
    CONSTRAINT valid_category CHECK (category IN (
        'bugfix', 'decision', 'feature', 'discovery',
        'refactor', 'change', 'learning', 'pattern',
        'error_solution', 'preference'
    )),
    CONSTRAINT valid_importance CHECK (importance_score >= 0 AND importance_score <= 1),
    CONSTRAINT valid_visibility CHECK (visibility IN ('personal', 'team', 'organization'))
);

-- User prompts table
CREATE TABLE IF NOT EXISTS user_prompts (
    id SERIAL PRIMARY KEY,
    session_id TEXT,
    prompt_number INTEGER,
    prompt_text TEXT NOT NULL,
    embedding vector(768),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Team collaboration (future)
    user_id VARCHAR(255),
    project_context VARCHAR(255)
);

-- Indexes for vector similarity search (HNSW algorithm)
CREATE INDEX IF NOT EXISTS idx_memories_embedding 
    ON memories USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_prompts_embedding 
    ON user_prompts USING hnsw (embedding vector_cosine_ops);

-- Indexes for filtering
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_context);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance_score DESC);
CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_team ON memories(team_id);
CREATE INDEX IF NOT EXISTS idx_memories_visibility ON memories(visibility);

-- Full-text search index (optional, for keyword search)
CREATE INDEX IF NOT EXISTS idx_memories_content_fts 
    ON memories USING gin(to_tsvector('english', content));

-- Function to update last_accessed_at automatically
CREATE OR REPLACE FUNCTION update_last_accessed()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_accessed_at = NOW();
    NEW.access_count = OLD.access_count + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Statistics view
CREATE OR REPLACE VIEW memory_stats AS
SELECT 
    COUNT(*) as total_memories,
    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') as memories_this_week,
    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 day') as memories_today,
    COUNT(DISTINCT category) as categories_used,
    COUNT(DISTINCT project_context) as projects,
    AVG(importance_score) as avg_importance,
    MAX(access_count) as max_access_count
FROM memories;

-- Category statistics view
CREATE OR REPLACE VIEW category_stats AS
SELECT 
    category,
    COUNT(*) as count,
    AVG(importance_score) as avg_importance,
    SUM(access_count) as total_accesses
FROM memories
GROUP BY category
ORDER BY count DESC;

-- Grant permissions (for team mode)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO synaptic;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO synaptic;

-- Initial data (optional - sample memory)
-- INSERT INTO memories (content, summary, category, importance_score, tags)
-- VALUES (
--     'Synaptic initialized successfully. This is your first memory!',
--     'Synaptic initialization',
--     'discovery',
--     0.5,
--     ARRAY['setup', 'initial']
-- );

COMMENT ON TABLE memories IS 'Stores persistent memories with vector embeddings for semantic search';
COMMENT ON TABLE user_prompts IS 'Stores user prompts history for context analysis';
COMMENT ON COLUMN memories.embedding IS '768-dimensional vector from nomic-embed-text model';
COMMENT ON COLUMN memories.visibility IS 'personal = only user, team = team members, organization = all';