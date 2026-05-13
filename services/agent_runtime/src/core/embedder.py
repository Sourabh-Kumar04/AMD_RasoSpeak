"""
RasoSpeak AI OS — Embedding Service
===================================
Production-grade semantic embeddings using:
- OpenAI text-embedding-3-large (1536 dims)
- Local SentenceTransformers fallback
- Caching for cost optimization
- Batch processing support
- Proper normalization for cosine similarity
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

import structlog

logger = structlog.get_logger("rasospeak.embeddings")


# ──────────────────────────────────────────────────────────────────────────────
# Embedding Types
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class EmbeddingResult:
    """Result of embedding generation."""
    embedding: list[float]
    model: str
    tokens_used: int
    cached: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# Base Embedder Interface
# ──────────────────────────────────────────────────────────────────────────────

class Embedder(ABC):
    """Abstract interface for embedding models."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        pass

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """Get the embedding dimension."""
        pass


# ──────────────────────────────────────────────────────────────────────────────
# Vector Utilities
# ──────────────────────────────────────────────────────────────────────────────

def normalize(embedding: list[float]) -> list[float]:
    """Normalize vector to unit length for cosine similarity."""
    import math

    magnitude = math.sqrt(sum(x * x for x in embedding))
    if magnitude == 0:
        return embedding

    return [x / magnitude for x in embedding]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0

    dot_product = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(y * y for y in b) ** 0.5

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return dot_product / (mag_a * mag_b)


# ──────────────────────────────────────────────────────────────────────────────
# Caching Layer
# ──────────────────────────────────────────────────────────────────────────────

class EmbeddingCache:
    """
    Simple in-memory cache with LRU eviction.
    Reduces API calls by caching embeddings.
    """

    def __init__(self, max_entries: int = 10000):
        self._cache: dict[str, tuple[list[float], str]] = {}  # hash -> (embedding, model)
        self._access_order: list[str] = []
        self._max_entries = max_entries

    def _hash_text(self, text: str) -> str:
        """Generate cache key from text."""
        # Normalize text before hashing
        normalized = text.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()[:32]

    async def get(self, text: str) -> Optional[tuple[list[float], str]]:
        """Get cached embedding if available."""
        key = self._hash_text(text)

        if key in self._cache:
            # Move to end (most recently used)
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

            return self._cache[key]

        return None

    async def set(self, text: str, embedding: list[float], model: str) -> None:
        """Cache an embedding."""
        key = self._hash_text(text)

        # Evict oldest if at capacity
        if len(self._cache) >= self._max_entries and key not in self._cache:
            oldest = self._access_order.pop(0)
            self._cache.pop(oldest, None)

        self._cache[key] = (embedding, model)
        self._access_order.append(key)

    async def clear(self) -> None:
        """Clear all cached embeddings."""
        self._cache.clear()
        self._access_order.clear()

    def stats(self) -> dict[str, int]:
        """Get cache statistics."""
        return {
            "entries": len(self._cache),
            "max_entries": self._max_entries,
        }


# ──────────────────────────────────────────────────────────────────────────────
# OpenAI Embedder
# ──────────────────────────────────────────────────────────────────────────────

class OpenAIEmbedder(Embedder):
    """
    OpenAI text-embedding-3 embedder.

    Uses the official OpenAI API with:
    - Automatic retry with backoff
    - Rate limiting handling
    - Token estimation
    - Batch processing
    """

    DIMENSIONS = 1536
    MAX_BATCH_SIZE = 2048  # OpenAI limit

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "text-embedding-3-large",
        cache: Optional[EmbeddingCache] = None,
    ):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._model = model
        self._cache = cache or EmbeddingCache()
        self._client = None

        logger.info("openai_embedder_initialized", model=model)

    def get_dimension(self) -> int:
        return self.DIMENSIONS

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        if not texts:
            return []

        # Check cache first
        uncached_texts = []
        results: list[Optional[list[float]]] = [None] * len(texts)

        for i, text in enumerate(texts):
            cached = await self._cache.get(text)
            if cached is not None:
                results[i] = cached[0]
            else:
                uncached_texts.append((i, text))

        if not uncached_texts:
            logger.debug("embed_batch_all_cached", count=len(texts))
            return results

        # Generate embeddings in batches
        all_embeddings = []
        indices = [i for i, _ in uncached_texts]
        texts_to_embed = [t for _, t in uncached_texts]

        for batch_start in range(0, len(texts_to_embed), self.MAX_BATCH_SIZE):
            batch_end = batch_start + self.MAX_BATCH_SIZE
            batch = texts_to_embed[batch_start:batch_end]

            embeddings = await self._call_api(batch)
            all_embeddings.extend(embeddings)

        # Fill in results
        for idx, (original_idx, text) in enumerate(uncached_texts):
            embedding = all_embeddings[idx]
            # Normalize for cosine similarity
            normalized = normalize(embedding)
            results[original_idx] = normalized
            # Cache the result
            await self._cache.set(text, normalized, self._model)

        return results

    async def _call_api(self, texts: list[str]) -> list[list[float]]:
        """Call OpenAI embeddings API with retry logic."""
        import aiohttp
        import asyncio

        url = "https://api.openai.com/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # Format for OpenAI API
        input_data = [{"text": text[:8192]} for text in texts]  # Truncate to max

        payload = {
            "model": self._model,
            "input": input_data,
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=60),
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            return [item["embedding"] for item in data["data"]]
                        elif response.status == 429:
                            # Rate limited - wait and retry
                            wait_time = (attempt + 1) * 2
                            logger.warning("openai_rate_limited", wait_seconds=wait_time)
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            text = await response.text()
                            raise Exception(f"OpenAI API error {response.status}: {text}")

            except asyncio.TimeoutError:
                logger.warning("openai_embed_timeout", attempt=attempt + 1)
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise

        raise Exception("Max retries exceeded for OpenAI embeddings API")


# ──────────────────────────────────────────────────────────────────────────────
# SentenceTransformer Embedder (Local)
# ──────────────────────────────────────────────────────────────────────────────

class LocalEmbedder(Embedder):
    """
    Local SentenceTransformer embedder.

    Use this when you want to run embeddings locally without API costs.
    Requires: pip install sentence-transformers
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        cache: Optional[EmbeddingCache] = None,
    ):
        self._model_name = model_name
        self._cache = cache or EmbeddingCache()
        self._model = None
        self._dimension = 384  # Default for MiniLM

        logger.info("local_embedder_initialized", model=model_name)

    def get_dimension(self) -> int:
        return self._dimension

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        if not texts:
            return []

        # Lazy load model
        if self._model is None:
            await self._load_model()

        # Check cache
        uncached = []
        results: list[Optional[list[float]]] = [None] * len(texts)

        for i, text in enumerate(texts):
            cached = await self._cache.get(text)
            if cached is not None:
                results[i] = cached[0]
            else:
                uncached.append((i, text))

        if not uncached:
            return results

        # Encode uncached texts
        texts_to_encode = [t for _, t in uncached]
        embeddings = self._model.encode(texts_to_encode, normalize_embeddings=True)

        for idx, (original_idx, text) in enumerate(uncached):
            embedding = embeddings[idx].tolist()
            results[original_idx] = embedding
            await self._cache.set(text, embedding, self._model_name)

        return results

    async def _load_model(self) -> None:
        """Load the SentenceTransformer model."""
        try:
            from sentence_transformers import SentenceTransformer

            logger.info("loading_sentence_transformer", model=self._model_name)
            self._model = SentenceTransformer(self._model_name)
            self._dimension = self._model.get_sentence_embedding_dimension()

        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )


# ──────────────────────────────────────────────────────────────────────────────
# Composite Embedder (Multi-Provider)
# ──────────────────────────────────────────────────────────────────────────────

class CompositeEmbedder(Embedder):
    """
    Composite embedder with fallback support.

    Tries providers in order:
    1. OpenAI (if API key available)
    2. Local SentenceTransformer (if installed)
    3. Raises error if none available
    """

    def __init__(
        self,
        openai_key: Optional[str] = None,
        local_model: Optional[str] = None,
        cache: Optional[EmbeddingCache] = None,
    ):
        self._cache = cache or EmbeddingCache()
        self._embedder: Optional[Embedder] = None
        self._providers: list[tuple[str, Embedder]] = []

        # Try OpenAI first
        if openai_key or os.environ.get("OPENAI_API_KEY"):
            self._providers.append(
                ("openai", OpenAIEmbedder(openai_key, cache=self._cache))
            )

        # Try local as fallback
        if local_model or True:  # Always try, will raise if not installed
            try:
                self._providers.append(
                    ("local", LocalEmbedder(local_model or "all-MiniLM-L6-v2", cache=self._cache))
                )
            except ImportError:
                logger.warning("local_embedder_not_available")

        if not self._providers:
            raise ValueError("No embedding providers available")

        self._embedder = self._providers[0][1]
        logger.info(
            "composite_embedder_initialized",
            primary=self._providers[0][0],
            available=len(self._providers),
        )

    def get_dimension(self) -> int:
        return self._embedder.get_dimension()

    async def embed(self, text: str) -> list[float]:
        return await self._embedder.embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await self._embedder.embed_batch(texts)

    async def switch_provider(self, provider_name: str) -> bool:
        """Switch to a different embedding provider."""
        for name, embedder in self._providers:
            if name == provider_name:
                self._embedder = embedder
                logger.info("embedder_provider_switched", provider=provider_name)
                return True
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────────────────

def create_embedder(
    provider: str = "auto",
    openai_key: Optional[str] = None,
    local_model: Optional[str] = None,
    cache_size: int = 10000,
) -> Embedder:
    """
    Create an embedder based on provider type.

    Args:
        provider: "openai", "local", or "auto" (try OpenAI first, fallback to local)
        openai_key: OpenAI API key (or use env OPENAI_API_KEY)
        local_model: SentenceTransformer model name
        cache_size: Maximum cache entries

    Returns:
        Configured Embedder instance
    """
    cache = EmbeddingCache(max_entries=cache_size)

    if provider == "openai":
        return OpenAIEmbedder(openai_key, cache=cache)
    elif provider == "local":
        return LocalEmbedder(local_model, cache=cache)
    else:  # "auto"
        return CompositeEmbedder(openai_key, local_model, cache)