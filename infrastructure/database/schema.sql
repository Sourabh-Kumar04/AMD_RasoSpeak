-- RasoSpeak AI OS — PostgreSQL Schema
-- Production-grade database with pgvector for semantic memory

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ──────────────────────────────────────────────────────────────────────────────
-- Tenants
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    plan VARCHAR(50) DEFAULT 'free',
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tenants_name ON tenants(name);

-- ──────────────────────────────────────────────────────────────────────────────
-- Users
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,
    UNIQUE(tenant_id, email)
);

CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_users_email ON users(email);

-- ──────────────────────────────────────────────────────────────────────────────
-- Sessions
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    refresh_token_hash VARCHAR(255),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_token ON sessions(token_hash);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);

-- ──────────────────────────────────────────────────────────────────────────────
-- Token Usage Tracking
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE token_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    prompt_tokens INT DEFAULT 0,
    completion_tokens INT DEFAULT 0,
    total_tokens INT DEFAULT 0,
    cost_usd NUMERIC(10, 6) DEFAULT 0,
    provider VARCHAR(50),
    model VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, date, provider, model)
);

CREATE INDEX idx_token_usage_user_date ON token_usage(user_id, date);
CREATE INDEX idx_token_usage_tenant_date ON token_usage(tenant_id, date);

-- ──────────────────────────────────────────────────────────────────────────────
-- Working Memory Checkpoints (persistence for Redis)
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE working_memory_checkpoints (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID NOT NULL,
    content JSONB NOT NULL,
    token_count INT DEFAULT 0,
    checkpoint_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_working_checkpoint_user_session
    ON working_memory_checkpoints(user_id, session_id);
CREATE INDEX idx_working_checkpoint_time
    ON working_memory_checkpoints(checkpoint_at);

-- ──────────────────────────────────────────────────────────────────────────────
-- Episodic Memory
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE episodic_memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    content JSONB NOT NULL,
    importance FLOAT DEFAULT 0.5,
    emotional_tone VARCHAR(50),
    topics TEXT[],
    episode_type VARCHAR(50) DEFAULT 'conversation',
    outcome VARCHAR(50),
    source VARCHAR(100),
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    archived_at TIMESTAMPTZ,
    summary TEXT,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_episodic_user_time
    ON episodic_memories(user_id, created_at DESC);
CREATE INDEX idx_episodic_topics
    ON episodic_memories USING GIN(topics);
CREATE INDEX idx_episodic_embedding
    ON episodic_memories USING ivfflat(embedding vector_cosine_ops);
CREATE INDEX idx_episodic_type
    ON episodic_memories(user_id, episode_type);
CREATE INDEX idx_episodic_tenant
    ON episodic_memories(tenant_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- Semantic Memory (Facts & Knowledge)
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE semantic_memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding VECTOR(1536),
    confidence FLOAT DEFAULT 1.0,
    importance FLOAT DEFAULT 0.5,
    fact_type VARCHAR(50),
    category VARCHAR(100),
    source_episodes UUID[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_accessed TIMESTAMPTZ DEFAULT NOW(),
    access_count INT DEFAULT 0,
    decay_score FLOAT DEFAULT 1.0,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_semantic_user
    ON semantic_memories(user_id);
CREATE INDEX idx_semantic_embedding
    ON semantic_memories USING ivfflat(embedding vector_cosine_ops);
CREATE INDEX idx_semantic_category
    ON semantic_memories(user_id, category);
CREATE INDEX idx_semantic_trgm
    ON semantic_memories USING GIN(content gin_trgm_ops);
CREATE INDEX idx_semantic_confidence
    ON semantic_memories(user_id, confidence DESC);
CREATE INDEX idx_semantic_tenant
    ON semantic_memories(tenant_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- Knowledge Graph Nodes
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE knowledge_nodes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    node_type VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    properties JSONB DEFAULT '{}',
    embedding VECTOR(1536),
    importance FLOAT DEFAULT 0.5,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_knowledge_node_user
    ON knowledge_nodes(user_id);
CREATE INDEX idx_knowledge_node_type
    ON knowledge_nodes(user_id, node_type);
CREATE INDEX idx_knowledge_node_embedding
    ON knowledge_nodes USING ivfflat(embedding vector_cosine_ops);
CREATE INDEX idx_knowledge_node_trgm
    ON knowledge_nodes USING GIN(name gin_trgm_ops);
CREATE INDEX idx_knowledge_node_tenant
    ON knowledge_nodes(tenant_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- Knowledge Graph Edges
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE knowledge_edges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    target_id UUID NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    relationship VARCHAR(100) NOT NULL,
    weight FLOAT DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    UNIQUE(source_id, target_id, relationship)
);

CREATE INDEX idx_edges_source ON knowledge_edges(source_id);
CREATE INDEX idx_edges_target ON knowledge_edges(target_id);
CREATE INDEX idx_edges_relationship ON knowledge_edges(relationship);

-- ──────────────────────────────────────────────────────────────────────────────
-- Procedural Memory
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE procedures (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    trigger_conditions JSONB NOT NULL,
    steps JSONB NOT NULL,
    success_rate FLOAT DEFAULT 0.0,
    usage_count INT DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_procedures_user ON procedures(user_id);
CREATE INDEX idx_procedures_usage ON procedures(user_id, usage_count DESC);
CREATE INDEX idx_procedures_success ON procedures(user_id, success_rate DESC);
CREATE INDEX idx_procedures_tenant ON procedures(tenant_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- Documents
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    source VARCHAR(100),
    source_url TEXT,
    content TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_documents_user ON documents(user_id);
CREATE INDEX idx_documents_tenant ON documents(tenant_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- Document Chunks
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1536),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_chunks_document ON document_chunks(document_id);
CREATE INDEX idx_chunks_embedding
    ON document_chunks USING ivfflat(embedding vector_cosine_ops);

-- ──────────────────────────────────────────────────────────────────────────────
-- Agent Executions
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE agent_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID,
    agent_id VARCHAR(255) NOT NULL,
    agent_type VARCHAR(100) NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    state VARCHAR(50),
    goal_description TEXT,
    input_payload JSONB,
    output_payload JSONB,
    error TEXT,
    reasoning TEXT,
    confidence FLOAT DEFAULT 1.0,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_ms INT,
    token_usage JSONB,
    cost_usd FLOAT,
    trace_id VARCHAR(255),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_executions_user_time
    ON agent_executions(user_id, started_at DESC);
CREATE INDEX idx_executions_workflow
    ON agent_executions(workflow_id);
CREATE INDEX idx_executions_agent
    ON agent_executions(agent_id, started_at DESC);
CREATE INDEX idx_executions_tenant
    ON agent_executions(tenant_id, started_at DESC);
CREATE INDEX idx_executions_trace
    ON agent_executions(trace_id) WHERE trace_id IS NOT NULL;

-- ──────────────────────────────────────────────────────────────────────────────
-- Workflow Executions
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE workflow_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_name VARCHAR(255) NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    state VARCHAR(50) DEFAULT 'pending',
    input JSONB,
    output JSONB,
    error TEXT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    retry_count INT DEFAULT 0,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_workflows_user
    ON workflow_executions(user_id, started_at DESC);
CREATE INDEX idx_workflows_name
    ON workflow_executions(workflow_name, started_at DESC);
CREATE INDEX idx_workflows_tenant
    ON workflow_executions(tenant_id, started_at DESC);

-- ──────────────────────────────────────────────────────────────────────────────
-- Audit Log
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_user ON audit_log(user_id, created_at DESC);
CREATE INDEX idx_audit_tenant ON audit_log(tenant_id, created_at DESC);
CREATE INDEX idx_audit_action ON audit_log(action, created_at DESC);

-- ──────────────────────────────────────────────────────────────────────────────
-- Scheduled Tasks
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE scheduled_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    workflow_name VARCHAR(255) NOT NULL,
    scheduled_for TIMESTAMPTZ NOT NULL,
    input JSONB,
    status VARCHAR(50) DEFAULT 'pending',
    executed_at TIMESTAMPTZ,
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_scheduled_user
    ON scheduled_tasks(user_id, scheduled_for);
CREATE INDEX idx_scheduled_status
    ON scheduled_tasks(status, scheduled_for);
CREATE INDEX idx_scheduled_tenant
    ON scheduled_tasks(tenant_id, scheduled_for);

-- ──────────────────────────────────────────────────────────────────────────────
-- Functions & Triggers
-- ──────────────────────────────────────────────────────────────────────────────

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trigger_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trigger_semantic_updated_at
    BEFORE UPDATE ON semantic_memories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trigger_knowledge_updated_at
    BEFORE UPDATE ON knowledge_nodes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Decay semantic memory confidence over time
CREATE OR REPLACE FUNCTION decay_semantic_memory()
RETURNS void AS $$
BEGIN
    UPDATE semantic_memories
    SET decay_score = decay_score * 0.999,
        confidence = confidence * 0.999,
        last_accessed = CASE
            WHEN last_accessed < NOW() - INTERVAL '7 days'
            THEN last_accessed
            ELSE NOW()
        END
    WHERE last_accessed < NOW() - INTERVAL '7 days';
END;
$$ LANGUAGE plpgsql;

-- Update access count and last_accessed
CREATE OR REPLACE FUNCTION update_memory_access()
RETURNS TRIGGER AS $$
BEGIN
    NEW.access_count = OLD.access_count + 1;
    NEW.last_accessed = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ──────────────────────────────────────────────────────────────────────────────
-- Row-Level Security Policies
-- ──────────────────────────────────────────────────────────────────────────────

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE episodic_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE semantic_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE procedures ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE token_usage ENABLE ROW LEVEL SECURITY;

-- Example RLS policy (apply per-table as needed)
-- CREATE POLICY tenant_isolation ON users
--     USING (tenant_id = current_setting('app.tenant_id')::UUID);
