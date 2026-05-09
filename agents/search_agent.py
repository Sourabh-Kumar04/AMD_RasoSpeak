"""
RasoSpeak v2 — Web Search Agent
Real-time web search for answering current events and factual queries.

Supports: Tavily, DuckDuckGo, SerpAPI, Brave Search
"""

import json
import logging
import time
from typing import Optional

import httpx

from .base_agent import BaseAgent
from config.settings import settings

log = logging.getLogger("rasospeak.search")


class SearchAgent(BaseAgent):
    """
    Agent for real-time web search.

    Searches the web for current information when the user asks
    about recent events, factual topics, or anything requiring
    up-to-date information.
    """

    name = "SearchAgent"

    def __init__(self):
        self._client: httpx.AsyncClient = None

    async def initialize(self):
        """Initialize search client."""
        self._client = httpx.AsyncClient(timeout=30.0)

        # Determine which search backend to use
        if settings.TAVILY_API_KEY:
            log.info("✅ SearchAgent initialized with Tavily")
        elif settings.SERP_API_KEY:
            log.info("✅ SearchAgent initialized with SerpAPI")
        elif settings.BRAVE_API_KEY:
            log.info("✅ SearchAgent initialized with Brave Search")
        else:
            log.info("✅ SearchAgent initialized with DuckDuckGo (free)")

        self._shared_memory = None

    def set_shared_memory(self, shared_memory):
        """Connect to shared memory for context."""
        self._shared_memory = shared_memory

    async def search(
        self,
        query: str,
        num_results: int = 5,
        include_summary: bool = True,
    ) -> dict:
        """
        Search the web for information.

        Args:
            query: The search query
            num_results: Number of results to return
            include_summary: Whether to include AI-generated summary

        Returns:
            SearchResult with results, summary, sources
        """
        t_start = time.perf_counter()
        log.info(f"SearchAgent searching: {query[:50]}...")

        try:
            # Try available search backends in priority order
            if settings.TAVILY_API_KEY:
                results = await self._search_tavily(query, num_results)
            elif settings.SERP_API_KEY:
                results = await self._search_serp(query, num_results)
            elif settings.BRAVE_API_KEY:
                results = await self._search_brave(query, num_results)
            else:
                results = await self._search_duckduckgo(query, num_results)

            elapsed_ms = int((time.perf_counter() - t_start) * 1000)

            # Generate summary if requested
            summary = ""
            if include_summary and results:
                summary = self._generate_summary(results)

            return {
                "query": query,
                "results": results,
                "summary": summary,
                "total_found": len(results),
                "processing_ms": elapsed_ms,
            }

        except Exception as e:
            log.error(f"SearchAgent error: {e}")
            elapsed_ms = int((time.perf_counter() - t_start) * 1000)
            return {
                "query": query,
                "results": [],
                "summary": f"Search failed: {str(e)}",
                "error": str(e),
                "processing_ms": elapsed_ms,
            }

    async def _search_tavily(self, query: str, num_results: int) -> list:
        """Search using Tavily API."""
        resp = await self._client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.TAVILY_API_KEY,
                "query": query,
                "max_results": num_results,
                "include_answer": True,
                "include_raw_content": False,
            }
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
                "score": item.get("score", 0),
            })

        return results

    async def _search_serp(self, query: str, num_results: int) -> list:
        """Search using SerpAPI (Google)."""
        resp = await self._client.get(
            "https://serpapi.com/search",
            params={
                "q": query,
                "api_key": settings.SERP_API_KEY,
                "num": num_results,
                "hl": "en",
            }
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("organic_results", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "position": item.get("position", 0),
            })

        return results

    async def _search_brave(self, query: str, num_results: int) -> list:
        """Search using Brave Search API."""
        resp = await self._client.get(
            "https://api.search.brave.com/resolver/v1/web/search",
            params={
                "q": query,
                "count": num_results,
            },
            headers={"Accept": "application/json", "X-Subscription-Token": settings.BRAVE_API_KEY},
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("web", {}).get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
            })

        return results

    async def _search_duckduckgo(self, query: str, num_results: int) -> list:
        """Search using DuckDuckGo (via HTML scrape - fallback)."""
        # Use DuckDuckGo instant answer API
        resp = await self._client.get(
            "https://api.duckduckgo.com/",
            params={
                "q": query,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1,
            }
        )
        resp.raise_for_status()
        data = resp.json()

        results = []

        # Add instant answer if available
        if data.get("AbstractText"):
            results.append({
                "title": data.get("AbstractSource", "DuckDuckGo"),
                "url": data.get("AbstractURL", ""),
                "snippet": data.get("AbstractText", ""),
                "is_answer": True,
            })

        # Add related topics
        for topic in data.get("RelatedTopics", [])[:num_results]:
            if isinstance(topic, dict):
                results.append({
                    "title": topic.get("Text", "").split(" - ")[0] if " - " in topic.get("Text", "") else topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                    "snippet": topic.get("Text", ""),
                })

        return results[:num_results]

    def _generate_summary(self, results: list) -> str:
        """Generate a brief summary from search results."""
        if not results:
            return "No results found."

        # Combine snippets for summary
        snippets = [r.get("snippet", "") for r in results[:3] if r.get("snippet")]
        if snippets:
            return " | ".join(snippets[:2])[:300]
        return results[0].get("snippet", "")[:200] if results else ""

    async def shutdown(self):
        if self._client:
            await self._client.aclose()
        log.info("SearchAgent shut down")