"""
RasoSpeak PostgreSQL Database Layer
====================================
Production database integration with asyncpg and pgvector support.
"""

import asyncio
import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import asyncpg
import structlog

logger = structlog.get_logger("rasospeak.db")

# Database connection pool
_pool: Optional[asyncpg.Pool] = None


@dataclass
class DBConfig:
    """Database configuration."""
    host: str = "localhost"
    port: int = 5432
    user: str = "rasospeak"
    password: str = ""
    database: str = "rasospeak"
    min_size: int = 5
    max_size: int = 20


async def init_db(config: DBConfig = None) -> asyncpg.Pool:
    """Initialize database connection pool."""
    global _pool

    if _pool is not None:
        return _pool

    # Get config from settings if not provided
    if config is None:
        from config.settings import settings
        config = DBConfig(
            host=settings.postgres_host,
            port=settings.postgres_port,
            user=settings.postgres_user,
            password=settings.postgres_password,
            database=settings.postgres_database,
        )

    # Check if postgres is configured
    if not settings.postgres_use or not config.password:
        logger.info("PostgreSQL not configured, using file storage")
        return None

    try:
        _pool = await asyncpg.create_pool(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            database=config.database,
            min_size=config.min_size,
            max_size=config.max_size,
        )

        # Create tables
        await _create_tables(_pool)

        logger.info("✅ PostgreSQL connected")
        return _pool
    except Exception as e:
        logger.warning(f"PostgreSQL unavailable ({e}), using file storage")
        return None


async def _create_tables(pool: asyncpg.Pool):
    """Create necessary tables."""
    async with pool.acquire() as conn:
        # Memory nodes table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_nodes (
                node_id UUID PRIMARY KEY,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                node_type TEXT NOT NULL,
                importance FLOAT DEFAULT 0.5,
                embedding vector(1536),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                metadata JSONB DEFAULT '{}',
                source TEXT DEFAULT 'conversation'
            )
        """)

        # Create index for vector search
        try:
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_nodes_embedding
                ON memory_nodes USING ivfflat (embedding vector_cosine_ops)
            """)
        except:
            pass  # pgvector extension might not be available

        # User sessions table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_id UUID PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                metadata JSONB DEFAULT '{}',
                provider_state JSONB DEFAULT '{}'
            )
        """)


async def close_db():
    """Close database connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_db() -> Optional[asyncpg.Pool]:
    """Get database pool."""
    return _pool


# ──────────────────────────────────────────────────────────────────────────────
# Memory Operations
# ──────────────────────────────────────────────────────────────────────────────

async def store_memory(
    user_id: str,
    content: str,
    node_type: str,
    importance: float = 0.5,
    embedding: List[float] = None,
    metadata: Dict = None,
    source: str = "conversation"
) -> str:
    """Store memory in PostgreSQL."""
    if not _pool:
        return None

    node_id = str(uuid.uuid4())

    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO memory_nodes (node_id, user_id, content, node_type, importance, embedding, metadata, source)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, node_id, user_id, content, node_type, importance, embedding, metadata or {}, source)

    return node_id


async def search_memories(
    user_id: str,
    query: str = None,
    embedding: List[float] = None,
    node_types: List[str] = None,
    limit: int = 10
) -> List[Dict]:
    """Search memories in PostgreSQL."""
    if not _pool:
        return []

    async with _pool.acquire() as conn:
        if embedding:
            # Vector similarity search
            rows = await conn.fetch("""
                SELECT node_id, content, node_type, importance, created_at
                FROM memory_nodes
                WHERE user_id = $1
                ORDER BY embedding <=> $2
                LIMIT $3
            """, user_id, embedding, limit)
        else:
            # Keyword search
            rows = await conn.fetch("""
                SELECT node_id, content, node_type, importance, created_at
                FROM memory_nodes
                WHERE user_id = $1 AND content ILIKE $2
                LIMIT $2
            """, user_id, f"%{query}%", limit)

    return [dict(r) for r in rows]


import uuid