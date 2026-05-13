-- RasoSpeak OS Database Schema
-- PostgreSQL + pgvector for production-grade memory and cognition

-- Users and Authentication
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    avatar_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    is_admin BOOLEAN DEFAULT false,

    -- Security
    mfa_enabled BOOLEAN DEFAULT false,
    mfa_secret VARCHAR(255),
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE,

    -- Settings (JSON for flexibility)
    preferences JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}'
);

-- API Keys (User-provided)
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL, -- openai, anthropic, google, etc.
    key_name VARCHAR(100),
    encrypted_key TEXT NOT NULL, -- Encrypted with user-specific key
    is_active BOOLEAN DEFAULT true,
    rate_limit INTEGER, -- Requests per minute
    monthly_budget DECIMAL(10,2), -- Budget in USD
    used_this_month DECIMAL(10,2) DEFAULT 0,
    last_used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE
);

-- Sessions (Voice/Chat)
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_type VARCHAR(50) NOT NULL, -- voice, chat, workflow
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    provider_used VARCHAR(50),
    model_used VARCHAR(100),
    total_tokens INTEGER DEFAULT 0,
    cost_usd DECIMAL(10,6) DEFAULT 0,
    message_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active', -- active, completed, interrupted
    metadata JSONB DEFAULT '{}'
);

-- Messages
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL, -- user, assistant, system
    content TEXT NOT NULL,
    model_used VARCHAR(100),
    provider_used VARCHAR(50),
    input_tokens INTEGER,
    output_tokens INTEGER,
    latency_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Unified Memory (Vector-enabled)
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,

    -- Memory content
    content TEXT NOT NULL,
    summary TEXT,
    memory_type VARCHAR(50) NOT NULL, -- working, episodic, semantic, procedural, social, emotional
    importance FLOAT DEFAULT 0.5,

    -- Embeddings (pgvector)
    embedding vector(1536),

    -- Source
    source VARCHAR(50) DEFAULT 'conversation',
    source_id UUID,

    -- Entities and relationships
    entities TEXT[], -- Array of entity names
    relationships JSONB DEFAULT '[]',

    -- Context
    speaker VARCHAR(100),
    emotional_tone VARCHAR(50),
    tags TEXT[],

    -- Temporal
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    access_count INTEGER DEFAULT 0,
    expires_at TIMESTAMP WITH TIME ZONE,

    -- Importance for GC
    importance_score FLOAT GENERATED ALWAYS AS (
        importance * (1 + access_count::float / 100)
    ) STORED
);

-- Create vector index for semantic search
CREATE INDEX memories_embedding_idx ON memories USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Indexes for memory retrieval
CREATE INDEX memories_user_idx ON memories(user_id);
CREATE INDEX memories_type_idx ON memories(memory_type);
CREATE INDEX memories_session_idx ON memories(session_id);
CREATE INDEX memories_created_idx ON memories(created_at DESC);

-- Knowledge Graph (Entities and Relationships)
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50), -- person, project, concept, etc.
    description TEXT,
    properties JSONB DEFAULT '{}',
    importance FLOAT DEFAULT 0.5,
    embedding vector(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, name)
);

CREATE TABLE relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    from_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    to_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relationship_type VARCHAR(100),
    properties JSONB DEFAULT '{}',
    strength FLOAT DEFAULT 0.5,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX entities_user_idx ON entities(user_id);
CREATE INDEX relationships_from_idx ON relationships(from_entity_id);
CREATE INDEX relationships_to_idx ON relationships(to_entity_id);

-- Goals and Tasks
CREATE TABLE goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    status VARCHAR(20) DEFAULT 'active', -- active, completed, paused, cancelled
    priority INTEGER DEFAULT 5, -- 1-10
    due_date TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    progress INTEGER DEFAULT 0, -- 0-100
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_id UUID REFERENCES goals(id) ON DELETE SET NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    status VARCHAR(20) DEFAULT 'pending', -- pending, in_progress, completed
    due_date TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Provider Usage Tracking
CREATE TABLE provider_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    model VARCHAR(100) NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd DECIMAL(10,6) DEFAULT 0,
    latency_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Aggregate daily usage
CREATE TABLE daily_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    provider VARCHAR(50) NOT NULL,
    total_requests INTEGER DEFAULT 0,
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_cost_usd DECIMAL(10,6) DEFAULT 0,
    UNIQUE(user_id, date, provider)
);

-- Audio Recording Metadata
CREATE TABLE audio_recordings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    storage_path TEXT NOT NULL,
    duration_ms INTEGER,
    sample_rate INTEGER,
    channels INTEGER,
    format VARCHAR(20),
    transcription TEXT,
    speakers TEXT[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Workflows (Persistent)
CREATE TABLE workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    workflow_type VARCHAR(50), -- automation, agent, scheduled
    definition JSONB NOT NULL, -- Workflow definition (JSON)
    state JSONB DEFAULT '{}', -- Current state
    status VARCHAR(20) DEFAULT 'idle', -- idle, running, paused, completed, failed
    current_step VARCHAR(100),
    progress INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Audit Log
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id UUID,
    details JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Consent Management (for continuous audio)
CREATE TABLE consents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    consent_type VARCHAR(50) NOT NULL, -- audio_recording, memory_storage, etc.
    granted BOOLEAN DEFAULT false,
    granted_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}',
    UNIQUE(user_id, consent_type)
);

-- Tenant Isolation (for future multi-tenant)
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE users ADD COLUMN org_id UUID REFERENCES organizations(id);

-- Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE provider_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE audio_recordings ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY user_isolation ON users USING (true);
CREATE POLICY session_isolation ON sessions USING (user_id = current_setting('app.current_user_id')::UUID);
CREATE POLICY message_isolation ON messages USING (user_id = current_setting('app.current_user_id')::UUID);
CREATE POLICY memory_isolation ON memories USING (user_id = current_setting('app.current_user_id')::UUID);
CREATE POLICY entity_isolation ON entities USING (user_id = current_setting('app.current_user_id')::UUID);
CREATE POLICY goal_isolation ON goals USING (user_id = current_setting('app.current_user_id')::UUID);
CREATE POLICY task_isolation ON tasks USING (user_id = current_setting('app.current_user_id')::UUID);
CREATE POLICY usage_isolation ON provider_usage USING (user_id = current_setting('app.current_user_id')::UUID);

-- Set current_user_id for RLS
CREATE OR REPLACE FUNCTION set_current_user() RETURNS TRIGGER AS $$
BEGIN
    EXECUTE format('SET LOCAL app.current_user_id TO %L', NEW.user_id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_user_context
    BEFORE INSERT ON sessions
    FOR EACH ROW EXECUTE FUNCTION set_current_user();

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;