"""
RasoSpeak v2 — Document Import Agent
Import documents, notes, PDFs, and files into your AI memory.

Supported formats:
- Text files (.txt)
- Markdown (.md)
- PDF (.pdf) - via PyPDF2
- Web pages (URLs)
- Notes and snippets
"""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from .base_agent import BaseAgent
from .shared_memory_agent import SharedMemoryAgent
from config.settings import settings

log = logging.getLogger("rasospeak.document")


class DocumentAgent(BaseAgent):
    """
    Agent for importing documents and files into your AI memory.

    This allows you to:
    - Import notes, PDFs, text files
    - Add web page content
    - Paste snippets and articles
    - Import from URLs

    All imported content goes into shared memory and can be
    queried by your AI partner.
    """

    name = "DocumentAgent"

    def __init__(self):
        self._storage_path = Path(settings.documents_path or "./memory/documents")
        self._shared_memory: Optional[SharedMemoryAgent] = None
        self._second_brain = None  # Second Brain for enhanced memory storage
        self._ensure_storage()

    def _ensure_storage(self):
        """Create storage directories."""
        self._storage_path.mkdir(parents=True, exist_ok=True)
        log.info(f"Document storage: {self._storage_path}")

    async def initialize(self):
        """Initialize document agent."""
        log.info("✅ DocumentAgent initialized")

    def set_second_brain(self, second_brain):
        """Connect to Second Brain for enhanced memory storage."""
        self._second_brain = second_brain
        log.info("DocumentAgent connected to SecondBrainAgent")

    def set_shared_memory(self, shared_memory: SharedMemoryAgent):
        """Connect to shared memory."""
        self._shared_memory = shared_memory

    # ══════════════════════════════════════════════════════
    # IMPORT METHODS
    # ══════════════════════════════════════════════════════

    async def import_text(
        self,
        content: str,
        title: str = None,
        tags: list = None,
        category: str = "note",
    ) -> dict:
        """
        Import text content directly.

        Args:
            content: The text content to import
            title: Optional title
            tags: Optional tags
            category: note | article | snippet | book | other

        Returns:
            Import result with ID
        """
        doc_id = f"doc_{int(time.time())}"
        title = title or f"Imported Note {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        document = {
            "id": doc_id,
            "title": title,
            "content": content,
            "category": category,
            "tags": tags or [],
            "imported_at": datetime.utcnow().isoformat(),
            "word_count": len(content.split()),
            "char_count": len(content),
        }

        # Save to disk
        await self._save_document(doc_id, document)

        # Store in Second Brain (handles dual-write to legacy automatically)
        if self._second_brain:
            await self._second_brain.add_document(
                content=content,
                title=title,
                doc_type=category,
                tags=tags,
            )

            # Extract and store key points
            key_points = self._extract_key_points(content)
            for point in key_points:
                await self._second_brain.add_user_fact(
                    fact=point,
                    category="document_key_point",
                )

        log.info(f"📄 Imported document: {title} ({document['word_count']} words)")

        return {
            "imported": True,
            "document_id": doc_id,
            "title": title,
            "word_count": document["word_count"],
        }

    async def import_file(
        self,
        file_path: str,
        tags: list = None,
    ) -> dict:
        """
        Import a file from disk.

        Supports: .txt, .md, .json
        """
        path = Path(file_path)

        if not path.exists():
            return {"error": "File not found", "path": file_path}

        # Determine type
        ext = path.suffix.lower()

        if ext in [".txt", ".md"]:
            content = path.read_text(encoding="utf-8")
            return await self.import_text(
                content=content,
                title=path.stem,
                tags=tags,
                category="file"
            )
        elif ext == ".json":
            try:
                data = json.loads(path.read_text())
                content = json.dumps(data, indent=2)
                return await self.import_text(
                    content=content,
                    title=path.stem,
                    tags=tags,
                    category="data"
                )
            except Exception as e:
                return {"error": f"Failed to parse JSON: {e}"}
        else:
            return {"error": f"Unsupported file type: {ext}"}

    async def import_url(
        self,
        url: str,
        title: str = None,
        tags: list = None,
    ) -> dict:
        """
        Import content from a URL (web page).

        Fetches the page and extracts main content.
        """
        log.info(f"🌐 Fetching URL: {url}")

        try:
            client = httpx.Client(timeout=30)
            resp = client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; RasoSpeak/1.0)"
            })
            resp.raise_for_status()

            html = resp.text

            # Extract text content (simple approach)
            content = self._extract_text_from_html(html)

            # Get title if not provided
            if not title:
                title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
                title = title_match.group(1) if title_match else url

            return await self.import_text(
                content=content,
                title=title,
                tags=tags + ["web", "url"] if tags else ["web", "url"],
                category="article"
            )

        except Exception as e:
            log.error(f"Failed to fetch URL: {e}")
            return {"error": f"Failed to fetch URL: {e}"}

    async def import_pdf(
        self,
        pdf_path: str,
        title: str = None,
        tags: list = None,
    ) -> dict:
        """
        Import a PDF file.

        Note: Requires pypdf or PyPDF2 installed.
        """
        try:
            from pypdf import PdfReader
        except ImportError:
            return {"error": "pypdf not installed. Run: pip install pypdf"}

        path = Path(pdf_path)
        if not path.exists():
            return {"error": "PDF not found"}

        try:
            reader = PdfReader(pdf_path)
            text = ""

            for page in reader.pages:
                text += page.extract_text() + "\n"

            title = title or path.stem

            return await self.import_text(
                content=text,
                title=title,
                tags=tags + ["pdf"] if tags else ["pdf"],
                category="document"
            )

        except Exception as e:
            return {"error": f"Failed to read PDF: {e}"}

    async def import_snippet(
        self,
        content: str,
        label: str = None,
    ) -> dict:
        """Import a quick snippet/clipboard content."""
        return await self.import_text(
            content=content,
            title=label or f"Snippet {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            tags=["snippet", "clipboard"],
            category="snippet"
        )

    # ══════════════════════════════════════════════════════
    # DOCUMENT MANAGEMENT
    # ══════════════════════════════════════════════════════

    async def list_documents(
        self,
        category: str = None,
        limit: int = 20,
    ) -> dict:
        """List all imported documents."""
        documents = []

        for path in sorted(self._storage_path.glob("*.json"), reverse=True)[:limit]:
            try:
                doc = json.loads(path.read_text())
                if category and doc.get("category") != category:
                    continue
                documents.append({
                    "id": doc.get("id"),
                    "title": doc.get("title"),
                    "category": doc.get("category"),
                    "tags": doc.get("tags", []),
                    "imported_at": doc.get("imported_at"),
                    "word_count": doc.get("word_count"),
                })
            except Exception:
                continue

        return {
            "documents": documents,
            "total": len(documents),
        }

    async def get_document(self, doc_id: str) -> dict:
        """Get a specific document."""
        path = self._storage_path / f"{doc_id}.json"
        if path.exists():
            return json.loads(path.read_text())
        return {"error": "Document not found"}

    async def delete_document(self, doc_id: str) -> dict:
        """Delete a document."""
        path = self._storage_path / f"{doc_id}.json"
        if path.exists():
            path.unlink()
            log.info(f"Deleted document: {doc_id}")
            return {"deleted": True}
        return {"error": "Document not found"}

    async def search_documents(self, query: str, limit: int = 10) -> dict:
        """Search within imported documents."""
        results = []

        for path in self._storage_path.glob("*.json"):
            try:
                doc = json.loads(path.read_text())
                content = doc.get("content", "").lower()
                title = doc.get("title", "").lower()

                if query.lower() in content or query.lower() in title:
                    results.append({
                        "id": doc.get("id"),
                        "title": doc.get("title"),
                        "snippet": content[content.find(query.lower()):content.find(query.lower()) + 200] if query.lower() in content else content[:200],
                    })
            except Exception:
                continue

        return {
            "query": query,
            "results": results[:limit],
            "total": len(results),
        }

    # ══════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ══════════════════════════════════════════════════════

    async def _save_document(self, doc_id: str, document: dict):
        """Save document to disk."""
        path = self._storage_path / f"{doc_id}.json"
        path.write_text(json.dumps(document, indent=2))

    def _extract_text_from_html(self, html: str) -> str:
        """Extract readable text from HTML."""
        # Remove script and style
        text = re.sub(r'<script.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Replace common tags with newlines
        text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)

        # Remove remaining tags
        text = re.sub(r'<[^>]+>', '', text)

        # Clean up whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = text.strip()

        return text[:50000]  # Limit to 50k chars

    def _extract_key_points(self, content: str) -> list:
        """Extract key points from content for memory."""
        # Simple extraction - split by sentences and find important ones
        sentences = re.split(r'[.!?]+', content)
        key_points = []

        for sentence in sentences[:20]:  # First 20 sentences
            sentence = sentence.strip()
            if len(sentence) > 20 and len(sentence) < 200:
                # Look for sentences with key words
                key_words = ["important", "key", "remember", "note", "main", "critical", "essential"]
                if any(word in sentence.lower() for word in key_words):
                    key_points.append(sentence)

        return key_points[:5]  # Return top 5

    async def shutdown(self):
        log.info("DocumentAgent shut down")