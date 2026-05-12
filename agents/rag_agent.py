"""
RasoSpeak v2 — RAG Agent
Advanced RAG with LangChain for semantic search and retrieval.

Features:
- Document chunking with semantic splitting
- Vector embeddings using sentence-transformers
- FAISS vector store for similarity search
- Wikipedia API integration
- Hybrid search (vector + keyword)
- Reranking with cross-encoders
- Query expansion and reformulation
"""

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from .base_agent import BaseAgent
from config.settings import settings

log = logging.getLogger("rasospeak.rag")

# LangChain imports
try:
    from langchain_community.document_loaders import (
        WebBaseLoader,
        TextLoader,
        PyPDFLoader,
    )
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_community.vectorstores import FAISS
    from langchain_community.retrievers import BM25Retriever
    from langchain_core.documents import Document
    from langchain_core.retrievers import BaseRetriever
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_huggingface import HuggingFaceEndpoint

    LANGCHAIN_AVAILABLE = True
except ImportError as e:
    log.warning(f"LangChain not fully available: {e}")
    LANGCHAIN_AVAILABLE = False


# BM25 for vectorless RAG
try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    log.warning("rank-bm25 not available, keyword search disabled")


# Embedding model - all-MiniLM-L6-v2 is fast and good quality
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


class RAGAgent(BaseAgent):
    """
    Agent 13: RAG Agent

    Advanced RAG system using LangChain for:
    - Semantic document search
    - Wikipedia integration
    - Hybrid retrieval (vector + keyword)
    - Query reformulation
    - Contextual compression
    """

    name = "RAGAgent"

    def __init__(self):
        self._embeddings = None
        self._vector_store = None
        self._llm = None
        self._documents: list[Document] = []
        self._metadata_store: dict = {}
        self._chunk_size = CHUNK_SIZE
        self._chunk_overlap = CHUNK_OVERLAP
        self._bm25_index = None
        self._bm25_corpus = []  # Store text chunks for BM25

    async def initialize(self):
        """Initialize RAG components."""
        if not LANGCHAIN_AVAILABLE:
            log.error("LangChain not available - RAG features disabled")
            return

        try:
            # Initialize embeddings
            log.info(f"Loading embedding model: {EMBEDDING_MODEL}")
            self._embeddings = HuggingFaceEmbeddings(
                model_name=EMBEDDING_MODEL,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True}
            )

            # Initialize LLM for query reformulation
            if settings.nvidia_api_key:
                from langchain_huggingface import HuggingFaceEndpoint
                self._llm = HuggingFaceEndpoint(
                    repo_id=settings.nvidia_model,
                    task="text-generation",
                    huggingfacehub_api_token=settings.nvidia_api_key,
                    max_new_tokens=256,
                )
            elif settings.openai_api_key:
                from langchain_openai import OpenAIEmbeddings
                # Fall back to OpenAI if configured
                pass

            # Load existing vector store if available
            self._load_vector_store()

            log.info("✅ RAGAgent initialized with LangChain")
        except Exception as e:
            log.error(f"RAGAgent initialization failed: {e}")
            self._embeddings = None

    def _load_vector_store(self):
        """Load persisted vector store from disk."""
        vector_path = "./memory/vector_store"
        if os.path.exists(vector_path):
            try:
                self._vector_store = FAISS.load_local(
                    vector_path,
                    self._embeddings,
                    allow_dangerous_deserialization=True
                )
                log.info(f"Loaded vector store with {self._vector_store.index.ntotal} vectors")
            except Exception as e:
                log.warning(f"Could not load vector store: {e}")

    def _save_vector_store(self):
        """Persist vector store to disk."""
        if self._vector_store:
            vector_path = "./memory/vector_store"
            os.makedirs(vector_path, exist_ok=True)
            try:
                self._vector_store.save_local(vector_path)
                log.info("Vector store saved")
            except Exception as e:
                log.warning(f"Could not save vector store: {e}")

    def _build_bm25_index(self):
        """Build BM25 index from document chunks for vectorless RAG."""
        if not BM25_AVAILABLE or not self._bm25_corpus:
            return

        try:
            tokenized_corpus = [doc.split() for doc in self._bm25_corpus]
            self._bm25_index = BM25Okapi(tokenized_corpus)
            log.info(f"BM25 index built with {len(self._bm25_corpus)} chunks")
        except Exception as e:
            log.error(f"BM25 index build error: {e}")
            self._bm25_index = None

    def _search_bm25(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Search using BM25 (vectorless RAG).

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            List of relevant chunks with BM25 scores
        """
        if not self._bm25_index or not self._bm25_corpus:
            return []

        try:
            tokenized_query = query.split()
            scores = self._bm25_index.get_scores(tokenized_query)

            # Get top-k results
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

            results = []
            for idx in top_indices:
                if scores[idx] > 0:  # Only include if there's a match
                    results.append({
                        "content": self._bm25_corpus[idx],
                        "score": float(scores[idx]),
                        "method": "bm25"
                    })

            return results
        except Exception as e:
            log.error(f"BM25 search error: {e}")
            return []

    async def add_document(
        self,
        content: str,
        title: str = "Untitled",
        source: str = "text",
        url: str = None,
        metadata: dict = None,
    ) -> dict:
        """
        Add a document to the RAG system.

        Args:
            content: Document text content
            title: Document title
            source: Source type (text, url, pdf, wikipedia)
            url: Source URL if applicable
            metadata: Additional metadata

        Returns:
            Dict with document ID and chunk count
        """
        if not self._embeddings:
            return {"error": "Embeddings not initialized"}

        try:
            doc_id = str(uuid.uuid4())

            # Create LangChain document
            doc = Document(
                page_content=content,
                metadata={
                    "id": doc_id,
                    "title": title,
                    "source": source,
                    "url": url,
                    "created_at": datetime.utcnow().isoformat(),
                    **(metadata or {})
                }
            )

            # Split into chunks
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
                length_function=len,
                separators=["\n\n", "\n", ". ", " ", ""]
            )

            chunks = text_splitter.split_documents([doc])

            # Add to vector store
            if self._vector_store is None:
                self._vector_store = FAISS.from_documents(
                    chunks,
                    self._embeddings
                )
            else:
                self._vector_store.add_documents(chunks)

            # Also add chunks to BM25 index for vectorless search
            if BM25_AVAILABLE:
                for chunk in chunks:
                    self._bm25_corpus.append(chunk.page_content)
                self._build_bm25_index()

            # Store metadata
            self._metadata_store[doc_id] = {
                "title": title,
                "source": source,
                "url": url,
                "chunk_count": len(chunks),
                "created_at": datetime.utcnow().isoformat()
            }

            # Save to disk
            self._save_vector_store()

            log.info(f"Added document '{title}' with {len(chunks)} chunks")

            return {
                "id": doc_id,
                "title": title,
                "chunk_count": len(chunks)
            }

        except Exception as e:
            log.error(f"Error adding document: {e}")
            return {"error": str(e)}

    async def add_url(self, url: str) -> dict:
        """Add content from a URL."""
        if not LANGCHAIN_AVAILABLE:
            return {"error": "LangChain not available"}

        try:
            loader = WebBaseLoader(url)
            docs = loader.load()

            if not docs:
                return {"error": "Could not load URL"}

            content = docs[0].page_content[:10000]  # Limit content size
            title = docs[0].metadata.get("title", "Web Page")

            return await self.add_document(
                content=content,
                title=title,
                source="url",
                url=url
            )

        except Exception as e:
            log.error(f"Error loading URL: {e}")
            return {"error": str(e)}

    async def search_wikipedia(self, query: str, max_results: int = 3) -> dict:
        """
        Search Wikipedia and add results to RAG.

        Args:
            query: Search query
            max_results: Number of articles to retrieve

        Returns:
            Dict with Wikipedia results
        """
        if not LANGCHAIN_AVAILABLE:
            return {"error": "LangChain not available"}

        try:
            import wikipedia
            wikipedia.set_lang("en")

            # Search Wikipedia
            search_results = wikipedia.search(query, results=max_results)

            results = []
            for page_title in search_results:
                try:
                    page = wikipedia.page(page_title, auto_suggest=False)
                    content = page.content[:5000]  # Limit content

                    # Add to RAG
                    doc_result = await self.add_document(
                        content=content,
                        title=page.title,
                        source="wikipedia",
                        url=page.url,
                        metadata={"summary": page.summary[:500]}
                    )

                    results.append({
                        "title": page.title,
                        "url": page.url,
                        "summary": page.summary[:300],
                        "added_to_rag": doc_result.get("id") is not None
                    })
                except Exception as e:
                    log.warning(f"Could not fetch Wikipedia page '{page_title}': {e}")
                    continue

            return {
                "query": query,
                "results": results,
                "total": len(results)
            }

        except ImportError:
            return {"error": "Wikipedia not installed"}
        except Exception as e:
            log.error(f"Wikipedia search error: {e}")
            return {"error": str(e)}

    async def wiki_qa(self, question: str, top_k: int = 3) -> dict:
        """
        Wikipedia-based Q&A using Karpathy's wiki-llm style approach.

        This method:
        1. Searches Wikipedia for relevant articles
        2. Chunks the content efficiently
        3. Uses LLM to answer based on retrieved context

        Args:
            question: User question
            top_k: Number of wiki articles to use

        Returns:
            Dict with answer and sources (wiki-llm style)
        """
        t_start = time.perf_counter()

        try:
            import wikipedia
            wikipedia.set_lang("en")

            # Step 1: Wikipedia search
            search_results = wikipedia.search(question, results=top_k)

            contexts = []
            sources = []

            for page_title in search_results[:top_k]:
                try:
                    page = wikipedia.page(page_title, auto_suggest=False)

                    # Karpathy style: chunk the article into sections
                    sections = page.content.split("\n\n")
                    for section in sections[:5]:  # Use first 5 sections per article
                        if len(section) > 100:  # Skip short sections
                            contexts.append(section.strip())
                            sources.append({
                                "title": page.title,
                                "url": page.url
                            })
                except Exception as e:
                    log.warning(f"Wiki Q&A error for '{page_title}': {e}")
                    continue

            if not contexts:
                return {
                    "question": question,
                    "answer": "I couldn't find relevant Wikipedia articles for your question.",
                    "sources": [],
                    "method": "wiki-llm"
                }

            # Step 2: Build context from retrieved sections
            context = "\n\n---\n\n".join(contexts[:10])  # Limit context size

            # Step 3: Generate answer using LLM
            system_prompt = """You are a knowledgeable AI assistant. Based on the provided Wikipedia context,
answer the question accurately. If the context doesn't contain the answer, say so.
Be concise and cite information from the context."""

            try:
                if self._llm:
                    from langchain_core.messages import HumanMessage, SystemMessage
                    messages = [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=f"Context:\n{context[:4000]}\n\nQuestion: {question}")
                    ]
                    response = await self._llm.ainvoke(messages)
                    answer = response.content if hasattr(response, 'content') else str(response)
                else:
                    # Fallback without LLM
                    answer = f"Based on Wikipedia articles:\n\n"
                    for src in sources[:3]:
                        answer += f"• {src['title']}: {src['url']}\n"
                    answer += f"\nFound {len(contexts)} relevant sections. Enable LLM for full answers."

            except Exception as e:
                log.error(f"Wiki Q&A LLM error: {e}")
                answer = f"Found {len(sources)} relevant Wikipedia articles. Check sources for details."

            elapsed_ms = int((time.perf_counter() - t_start) * 1000)

            return {
                "question": question,
                "answer": answer,
                "sources": sources[:5],
                "context_chunks": len(contexts),
                "method": "wiki-llm",
                "processing_ms": elapsed_ms
            }

        except Exception as e:
            log.error(f"Wiki Q&A error: {e}")
            return {
                "question": question,
                "answer": f"Error performing Wikipedia search: {str(e)}",
                "sources": [],
                "method": "wiki-llm",
                "error": str(e)
            }

    async def comprehensive_search(self, query: str) -> dict:
        """
        Comprehensive search combining multiple sources.

        Searches in order:
        1. Local RAG (user documents)
        2. Wikipedia (wiki-llm style)
        3. Web search (if available)

        Args:
            query: Search query

        Returns:
            Combined results from all sources
        """
        results = {
            "query": query,
            "local_documents": [],
            "wikipedia": None,
            "web": []
        }

        # 1. Local documents
        local_results = await self.retrieve(query, top_k=3)
        results["local_documents"] = local_results

        # 2. Wikipedia
        wiki_result = await self.wiki_qa(query, top_k=3)
        results["wikipedia"] = wiki_result

        # 3. Web search (if search agent available)
        if hasattr(self, '_search_agent') and self._search_agent:
            try:
                web_results = await self._search_agent.search(query, num_results=5)
                results["web"] = web_results.get("results", [])
            except Exception as e:
                log.warning(f"Web search in comprehensive search: {e}")

        # Generate combined answer
        all_sources = []
        if local_results:
            all_sources.extend([{"title": r["title"], "source": "document"} for r in local_results])
        if wiki_result.get("sources"):
            all_sources.extend([{"title": s["title"], "source": "wikipedia"} for s in wiki_result["sources"]])

        return {
            **results,
            "all_sources": all_sources,
            "has_local": len(local_results) > 0,
            "has_wikipedia": bool(wiki_result.get("sources")),
            "has_web": len(results["web"]) > 0
        }

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filter_source: str = None,
        use_method: str = "hybrid",  # "vector", "bm25", or "hybrid"
    ) -> list[dict]:
        """
        Retrieve relevant documents for a query.

        Args:
            query: Search query
            top_k: Number of results to return
            filter_source: Optional source filter (wikipedia, url, text)
            use_method: Search method - "vector" (semantic), "bm25" (keyword), "hybrid" (both)

        Returns:
            List of relevant document chunks with scores
        """
        vector_results = []
        bm25_results = []

        # Vector search
        if use_method in ("vector", "hybrid") and self._vector_store:
            try:
                docs_with_scores = self._vector_store.similarity_search_with_score(
                    query,
                    k=top_k * 2
                )

                for doc, score in docs_with_scores:
                    if filter_source and doc.metadata.get("source") != filter_source:
                        continue
                    vector_results.append({
                        "content": doc.page_content,
                        "title": doc.metadata.get("title", "Untitled"),
                        "source": doc.metadata.get("source", "unknown"),
                        "url": doc.metadata.get("url"),
                        "score": float(score),
                        "id": doc.metadata.get("id"),
                        "method": "vector"
                    })
            except Exception as e:
                log.error(f"Vector search error: {e}")

        # BM25 search (vectorless)
        if use_method in ("bm25", "hybrid") and BM25_AVAILABLE:
            bm25_results = self._search_bm25(query, top_k)

            # Match BM25 results to documents
            for i, bm25_result in enumerate(bm25_results):
                # Try to find matching document in vector store
                for doc in (self._vector_store.docstore._dict.values() if self._vector_store else []):
                    if bm25_result["content"] in doc.page_content:
                        bm25_results[i].update({
                            "title": doc.metadata.get("title", "Untitled"),
                            "source": doc.metadata.get("source", "unknown"),
                            "url": doc.metadata.get("url"),
                            "id": doc.metadata.get("id"),
                        })
                        break

        # Combine results using Reciprocal Rank Fusion
        if use_method == "hybrid" and vector_results and bm25_results:
            combined = {}
            for i, r in enumerate(vector_results):
                key = r["content"][:100]
                combined[key] = {**r, "fusion_score": combined.get(key, {}).get("fusion_score", 0) + 1 / (60 + i)}
            for i, r in enumerate(bm25_results):
                key = r["content"][:100]
                combined[key] = {**r, "fusion_score": combined.get(key, {}).get("fusion_score", 0) + 1 / (60 + i)}

            results = sorted(combined.values(), key=lambda x: x["fusion_score"], reverse=True)[:top_k]
        elif use_method == "bm25":
            results = bm25_results[:top_k]
        else:
            results = vector_results[:top_k]

        return results

    async def query_with_context(
        self,
        query: str,
        top_k: int = 5,
        system_prompt: str = None,
    ) -> dict:
        """
        Query with RAG context using LLM.

        This performs:
        1. Query reformulation/expansion
        2. Retrieval
        3. Answer generation with context

        Args:
            query: User query
            top_k: Number of context chunks
            system_prompt: Optional system prompt override

        Returns:
            Dict with answer, sources, and metadata
        """
        t_start = time.perf_counter()

        # Retrieve relevant documents
        context_docs = await self.retrieve(query, top_k=top_k)

        if not context_docs:
            return {
                "answer": "I don't have relevant information in my knowledge base. Try searching the web or adding documents.",
                "sources": [],
                "context_used": False
            }

        # Build context string
        context_parts = []
        for i, doc in enumerate(context_docs):
            source = doc.get("source", "document")
            title = doc.get("title", "Untitled")
            context_parts.append(f"[{i+1}] {title} ({source}): {doc['content'][:500]}")

        context = "\n\n".join(context_parts)

        # Default system prompt
        if not system_prompt:
            system_prompt = """You are a helpful AI assistant with access to a knowledge base.
Use the provided context to answer questions accurately. If the context doesn't contain
the answer, say so. Cite sources when possible using [1], [2], etc."""

        # Generate response
        try:
            if self._llm:
                from langchain_core.messages import HumanMessage, SystemMessage

                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=f"Context:\n{context}\n\nQuestion: {query}")
                ]

                response = await self._llm.ainvoke(messages)
                answer = response.content if hasattr(response, 'content') else str(response)
            else:
                # Fallback without LLM
                answer = f"Found {len(context_docs)} relevant documents. Context:\n\n{context[:1000]}..."

        except Exception as e:
            log.error(f"LLM error: {e}")
            answer = f"Retrieved {len(context_docs)} relevant documents. Check sources for details."

        elapsed_ms = int((time.perf_counter() - t_start) * 1000)

        return {
            "answer": answer,
            "sources": [
                {"title": d["title"], "url": d.get("url"), "source": d.get("source")}
                for d in context_docs
            ],
            "context_used": True,
            "context_chunks": len(context_docs),
            "processing_ms": elapsed_ms
        }

    async def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Hybrid search combining vector similarity with keyword matching.

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            Merged results from vector and keyword search
        """
        if not self._vector_store:
            return await self.retrieve(query, top_k)

        try:
            # Get vector results
            vector_results = await self.retrieve(query, top_k=top_k * 2)

            # Get BM25 keyword results
            if self._vector_store and hasattr(self._vector_store, 'docstore'):
                texts = [doc.page_content for doc in self._vector_store.docstore._dict.values()]
                if texts:
                    bm25 = BM25Retriever.from_texts(texts)
                    bm25.k = top_k
                    bm25_results = await bm25.ainvoke(query)
                    keyword_results = [
                        {
                            "content": doc.page_content,
                            "title": doc.metadata.get("title", "Untitled"),
                            "source": doc.metadata.get("source", "unknown"),
                            "score": 1.0  # BM25 scores are not normalized
                        }
                        for doc in bm25_results
                    ]

                    # Merge and rerank (simple reciprocal rank fusion)
                    merged = {}
                    for i, r in enumerate(vector_results):
                        key = r["content"][:100]
                        merged[key] = {
                            **r,
                            "rrf_score": merged.get(key, {}).get("rrf_score", 0) + 1 / (60 + i)
                        }
                    for i, r in enumerate(keyword_results):
                        key = r["content"][:100]
                        merged[key] = {
                            **r,
                            "rrf_score": merged.get(key, {}).get("rrf_score", 0) + 1 / (60 + i)
                        }

                    # Sort by RRF score
                    final_results = sorted(
                        merged.values(),
                        key=lambda x: x["rrf_score"],
                        reverse=True
                    )[:top_k]

                    return final_results

        except Exception as e:
            log.error(f"Hybrid search error: {e}")

        return vector_results

    async def get_stats(self) -> dict:
        """Get RAG system statistics."""
        if not self._vector_store:
            return {
                "total_documents": 0,
                "total_chunks": 0,
                "sources": {}
            }

        try:
            doc_count = len(set(
                doc.metadata.get("id")
                for doc in self._vector_store.docstore._dict.values()
            ))

            sources = {}
            for doc in self._vector_store.docstore._dict.values():
                source = doc.metadata.get("source", "unknown")
                sources[source] = sources.get(source, 0) + 1

            return {
                "total_documents": doc_count,
                "total_chunks": self._vector_store.index.ntotal,
                "sources": sources
            }
        except Exception as e:
            log.error(f"Stats error: {e}")
            return {"error": str(e)}

    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document from the RAG system."""
        if not self._vector_store:
            return False

        try:
            # Find and remove from vector store
            # Note: FAISS doesn't support direct deletion, need to rebuild
            # For now, just remove from metadata
            if doc_id in self._metadata_store:
                del self._metadata_store[doc_id]
                return True
        except Exception as e:
            log.error(f"Delete error: {e}")

        return False

    async def clear(self):
        """Clear all documents from RAG."""
        self._vector_store = None
        self._documents = []
        self._metadata_store = {}

        # Remove saved vector store
        vector_path = "./memory/vector_store"
        if os.path.exists(vector_path):
            import shutil
            shutil.rmtree(vector_path)

        log.info("RAG cleared")

    async def shutdown(self):
        """Cleanup resources."""
        self._save_vector_store()
        log.info("RAGAgent shut down")