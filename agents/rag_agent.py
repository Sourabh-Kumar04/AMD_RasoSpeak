"""
RasoSpeak v2 — Lightweight RAG Agent
Vectorless RAG using BM25 + LLM for semantic-free, fast retrieval.

Inspired by LLM Kiwi approach: lightweight, no embeddings, no vectors.
Uses BM25 for keyword matching + LLM for answer synthesis.
"""

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime
from typing import Optional

from .base_agent import BaseAgent
from config.settings import settings

log = logging.getLogger("rasospeak.rag")

# BM25 for keyword retrieval
try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    log.warning("rank-bm25 not available, using simple keyword search")

# LLM for answer synthesis
try:
    import httpx
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    log.warning("httpx not available for LLM calls")


# Chunk settings for vectorless RAG
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


class LightweightRAGAgent(BaseAgent):
    """
    Agent 13: Lightweight RAG Agent (LLM Kiwi style)

    Vectorless RAG system that uses:
    - BM25 for keyword-based retrieval (no embeddings, no vectors)
    - Simple text preprocessing for matching
    - LLM for answer synthesis from retrieved context

    Benefits:
    - No embedding model needed
    - No vector store needed
    - Fast indexing and retrieval
    - Works on 4GB RAM
    - Transparent keyword matching
    """

    name = "LightweightRAGAgent"

    def __init__(self):
        self._documents: list[dict] = []  # Store documents as dicts
        self._chunks: list[str] = []     # Text chunks for BM25
        self._chunk_metadata: list[dict] = []  # Metadata for each chunk
        self._bm25_index = None          # BM25 index
        self._initialized = False

    async def initialize(self):
        """Initialize the lightweight RAG system."""
        log.info("🔧 Initializing Lightweight RAG Agent (vectorless)...")

        if not BM25_AVAILABLE:
            log.warning("BM25 not available - using simple keyword search")

        # Load persisted documents
        self._load_documents()

        # Build BM25 index if we have documents
        if self._chunks:
            self._build_bm25_index()

        self._initialized = True
        log.info(f"✅ Lightweight RAG ready with {len(self._documents)} documents")

    def _load_documents(self):
        """Load documents from disk."""
        docs_path = "./memory/rag_documents.json"
        if os.path.exists(docs_path):
            try:
                with open(docs_path, 'r') as f:
                    data = json.load(f)
                    self._documents = data.get('documents', [])
                    self._chunks = data.get('chunks', [])
                    self._chunk_metadata = data.get('metadata', [])
                log.info(f"Loaded {len(self._documents)} documents from disk")
            except Exception as e:
                log.warning(f"Could not load RAG documents: {e}")

    def _save_documents(self):
        """Persist documents to disk."""
        docs_path = "./memory/rag_documents.json"
        os.makedirs("./memory", exist_ok=True)
        try:
            with open(docs_path, 'w') as f:
                json.dump({
                    'documents': self._documents,
                    'chunks': self._chunks,
                    'metadata': self._chunk_metadata
                }, f)
        except Exception as e:
            log.warning(f"Could not save RAG documents: {e}")

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text for BM25 - simple word tokenization."""
        # Lowercase and split on non-alphanumeric
        text = text.lower()
        tokens = re.findall(r'\b\w+\b', text)
        # Remove very short tokens and common stopwords
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                     'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
                     'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                     'would', 'could', 'should', 'may', 'might', 'can', 'this', 'that',
                     'these', 'those', 'it', 'its', 'i', 'you', 'he', 'she', 'we', 'they'}
        return [t for t in tokens if len(t) > 2 and t not in stopwords]

    def _create_chunks(self, content: str) -> list[tuple[str, dict]]:
        """Split content into overlapping chunks."""
        # Split by sentences first
        sentences = re.split(r'[.!?]+', content)
        chunks = []
        current_chunk = ""
        current_size = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sentence_size = len(sentence)

            if current_size + sentence_size > CHUNK_SIZE and current_chunk:
                chunks.append((current_chunk.strip(), {}))
                # Start overlap
                words = current_chunk.split()
                overlap_size = min(CHUNK_OVERLAP, len(words))
                current_chunk = " ".join(words[-overlap_size:]) + " " + sentence
                current_size = len(current_chunk)
            else:
                current_chunk += " " + sentence
                current_size += sentence_size + 1

        if current_chunk.strip():
            chunks.append((current_chunk.strip(), {}))

        return chunks

    def _build_bm25_index(self):
        """Build BM25 index from chunks."""
        if not BM25_AVAILABLE or not self._chunks:
            return

        try:
            tokenized_chunks = [self._tokenize(chunk) for chunk in self._chunks]
            self._bm25_index = BM25Okapi(tokenized_chunks)
            log.info(f"BM25 index built with {len(self._chunks)} chunks")
        except Exception as e:
            log.error(f"BM25 index build error: {e}")
            self._bm25_index = None

    # ── DOCUMENT MANAGEMENT ──────────────────────────────

    async def add_document(
        self,
        content: str,
        title: str = "Untitled",
        source: str = "text",
        url: str = None,
        metadata: dict = None,
    ) -> dict:
        """Add a document to the RAG system."""
        doc_id = str(uuid.uuid4())

        doc = {
            "id": doc_id,
            "title": title,
            "content": content,
            "source": source,
            "url": url,
            "created_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }

        # Create chunks
        raw_chunks = self._create_chunks(content)

        for chunk_text, chunk_meta in raw_chunks:
            self._documents.append({
                **doc,
                "chunk_text": chunk_text,
                "chunk_id": str(uuid.uuid4())
            })
            self._chunks.append(chunk_text)
            self._chunk_metadata.append({
                "doc_id": doc_id,
                "title": title,
                "source": source,
                "url": url
            })

        # Rebuild index
        self._build_bm25_index()
        self._save_documents()

        log.info(f"Added document '{title}' with {len(raw_chunks)} chunks")

        return {
            "id": doc_id,
            "title": title,
            "chunk_count": len(raw_chunks)
        }

    async def add_url(self, url: str) -> dict:
        """Add content from a URL."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                resp.raise_for_status()

                # Extract text from HTML
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, 'html.parser')

                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()

                content = soup.get_text(separator=' ', strip=True)
                title = soup.title.string if soup.title else "Web Page"

                return await self.add_document(
                    content=content[:10000],  # Limit content
                    title=title or "Web Page",
                    source="url",
                    url=url
                )
        except Exception as e:
            log.error(f"Error loading URL: {e}")
            return {"error": str(e)}

    # ── RETRIEVAL ──────────────────────────────────────

    def _simple_keyword_search(self, query: str, top_k: int = 5) -> list[dict]:
        """Simple keyword-based search without BM25."""
        query_tokens = set(self._tokenize(query))
        results = []

        for i, chunk in enumerate(self._chunks):
            chunk_tokens = set(self._tokenize(chunk))

            # Count matching tokens
            matches = len(query_tokens & chunk_tokens)
            if matches > 0:
                score = matches / max(len(query_tokens), len(chunk_tokens))
                results.append({
                    "content": chunk,
                    "score": score,
                    "metadata": self._chunk_metadata[i] if i < len(self._chunk_metadata) else {},
                    "method": "keyword"
                })

        # Sort by score
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _bm25_search(self, query: str, top_k: int = 5) -> list[dict]:
        """BM25-based search."""
        if not self._bm25_index:
            return self._simple_keyword_search(query, top_k)

        try:
            query_tokens = self._tokenize(query)
            scores = self._bm25_index.get_scores(query_tokens)

            # Get top-k results
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

            results = []
            for idx in top_indices:
                if scores[idx] > 0:
                    results.append({
                        "content": self._chunks[idx],
                        "score": float(scores[idx]),
                        "metadata": self._chunk_metadata[idx] if idx < len(self._chunk_metadata) else {},
                        "method": "bm25"
                    })

            return results
        except Exception as e:
            log.error(f"BM25 search error: {e}")
            return self._simple_keyword_search(query, top_k)

    async def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Retrieve relevant documents for a query."""
        if not self._chunks:
            return []

        if BM25_AVAILABLE and self._bm25_index:
            return self._bm25_search(query, top_k)
        else:
            return self._simple_keyword_search(query, top_k)

    # ── LLM ANSWER GENERATION ──────────────────────────

    async def _call_llm(self, messages: list[dict]) -> str:
        """Call LLM for answer generation."""
        if not LLM_AVAILABLE:
            return "LLM not available. Showing retrieved context instead."

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                headers = {"Authorization": f"Bearer {settings.nvidia_api_key}"}
                payload = {
                    "model": settings.nvidia_model,
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 512
                }

                resp = await client.post(
                    f"{settings.nvidia_api_url}/chat/completions",
                    headers=headers,
                    json=payload
                )

                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
                else:
                    log.warning(f"LLM error: {resp.status_code}")
                    return None
        except Exception as e:
            log.error(f"LLM call error: {e}")
            return None

    async def query_with_context(
        self,
        query: str,
        top_k: int = 5,
        use_llm: bool = True
    ) -> dict:
        """
        Query with context retrieval and optional LLM answer.

        Uses lightweight approach:
        1. BM25 keyword retrieval
        2. Context assembly
        3. Optional LLM answer synthesis
        """
        t_start = time.perf_counter()

        # Retrieve relevant chunks
        results = await self.retrieve(query, top_k=top_k)

        if not results:
            return {
                "answer": "No relevant documents found. Try adding documents or searching the web.",
                "sources": [],
                "context_used": False
            }

        # Build context from retrieved chunks
        context_parts = []
        for i, r in enumerate(results):
            title = r.get("metadata", {}).get("title", "Document")
            source = r.get("metadata", {}).get("source", "unknown")
            context_parts.append(f"[{i+1}] {title} ({source}): {r['content']}")

        context = "\n\n".join(context_parts)

        # Generate answer with LLM if available
        answer = None
        if use_llm:
            system_prompt = """You are a helpful AI assistant. Based on the provided context,
answer the user's question accurately and concisely. If the context doesn't contain
the answer, say so. Cite sources using [1], [2], etc."""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}
            ]

            answer = await self._call_llm(messages)

        elapsed_ms = int((time.perf_counter() - t_start) * 1000)

        return {
            "answer": answer or f"Based on {len(results)} relevant documents:\n\n{context[:1000]}...",
            "sources": [
                {
                    "title": r.get("metadata", {}).get("title", "Untitled"),
                    "url": r.get("metadata", {}).get("url"),
                    "source": r.get("metadata", {}).get("source", "unknown"),
                    "score": r.get("score", 0),
                    "method": r.get("method", "unknown")
                }
                for r in results
            ],
            "context_used": True,
            "context_chunks": len(results),
            "processing_ms": elapsed_ms
        }

    # ── WIKIPEDIA Q&A (LLM Kiwi Style) ───────────────

    async def wiki_qa(self, question: str, max_results: int = 3) -> dict:
        """
        Wikipedia-based Q&A - LLM Kiwi style.

        Efficient approach:
        1. Search Wikipedia for relevant articles
        2. Extract key sections
        3. Use LLM to answer from wiki context
        """
        t_start = time.perf_counter()

        try:
            import wikipedia
            wikipedia.set_lang("en")

            # Search Wikipedia
            search_results = wikipedia.search(question, results=max_results)

            contexts = []
            sources = []

            for page_title in search_results[:max_results]:
                try:
                    page = wikipedia.page(page_title, auto_suggest=False)

                    # Extract sections (Kiwi style - focus on relevant sections)
                    sections = page.content.split("\n\n")
                    for section in sections[:8]:  # First 8 sections per article
                        if len(section) > 100:
                            contexts.append(section.strip())
                            sources.append({
                                "title": page.title,
                                "url": page.url
                            })
                except Exception as e:
                    log.warning(f"Wiki page error: {e}")
                    continue

            if not contexts:
                return {
                    "question": question,
                    "answer": "No Wikipedia articles found for your question.",
                    "sources": [],
                    "method": "llm-kiwi"
                }

            # Build context
            context = "\n\n---\n\n".join(contexts[:15])  # Limit context

            # Try to generate answer with LLM
            system_prompt = """You are a knowledgeable AI assistant. Based on the Wikipedia context provided,
answer the question accurately. Be concise and cite sources."""

            answer = await self._call_llm([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Wikipedia Context:\n{context[:6000]}\n\nQuestion: {question}"}
            ])

            elapsed_ms = int((time.perf_counter() - t_start) * 1000)

            if answer:
                return {
                    "question": question,
                    "answer": answer,
                    "sources": sources[:10],
                    "context_chunks": len(contexts),
                    "method": "llm-kiwi",
                    "processing_ms": elapsed_ms
                }
            else:
                # Fallback without LLM
                return {
                    "question": question,
                    "answer": f"Found {len(sources)} Wikipedia articles. Check sources for details.",
                    "sources": sources[:10],
                    "method": "llm-kiwi",
                    "processing_ms": elapsed_ms
                }

        except ImportError:
            return {"error": "Wikipedia library not installed"}
        except Exception as e:
            log.error(f"Wikipedia Q&A error: {e}")
            return {
                "question": question,
                "answer": f"Error: {str(e)}",
                "sources": [],
                "method": "llm-kiwi"
            }

    # ── COMPREHENSIVE SEARCH ───────────────────────────

    async def comprehensive_search(self, query: str) -> dict:
        """
        Comprehensive search across all sources.

        Searches:
        1. Local documents (BM25)
        2. Wikipedia (LLM Kiwi)
        3. Web search (if available)
        """
        results = {
            "query": query,
            "local_documents": [],
            "wikipedia": None,
            "web": []
        }

        # 1. Local documents
        local_results = await self.retrieve(query, top_k=5)
        results["local_documents"] = local_results

        # 2. Wikipedia
        wiki_result = await self.wiki_qa(query, top_k=3)
        results["wikipedia"] = wiki_result

        # 3. Web search (if search agent available)
        if hasattr(self, '_search_agent') and self._search_agent:
            try:
                web_results = await self._search_agent.search(query, num_results=5)
                results["web"] = web_results.get("results", [])
            except Exception:
                pass

        return results

    # ── UTILITY METHODS ────────────────────────────────

    async def get_stats(self) -> dict:
        """Get RAG statistics."""
        sources = {}
        for meta in self._chunk_metadata:
            source = meta.get("source", "unknown")
            sources[source] = sources.get(source, 0) + 1

        return {
            "total_documents": len(set(d.get("id") for d in self._documents if "id" in d)),
            "total_chunks": len(self._chunks),
            "sources": sources,
            "method": "bm25" if BM25_AVAILABLE else "keyword",
            "llm_enabled": LLM_AVAILABLE
        }

    async def clear(self):
        """Clear all documents."""
        self._documents = []
        self._chunks = []
        self._chunk_metadata = []
        self._bm25_index = None
        self._save_documents()
        log.info("RAG cleared")

    async def shutdown(self):
        """Cleanup."""
        self._save_documents()
        log.info("Lightweight RAG Agent shut down")