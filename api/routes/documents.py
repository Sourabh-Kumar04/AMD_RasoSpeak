"""
Document & RAG routes — /documents/* and /rag/* endpoints.
Import files, notes, URLs; RAG knowledge base.
"""

from fastapi import APIRouter, Request, UploadFile, File
from pydantic import BaseModel, Field

from api.state import agents

router = APIRouter(tags=["📄 Documents & RAG"])


# ── DOCUMENT MODELS ─────────────────────────────────────

class ImportTextRequest(BaseModel):
    content: str
    title: str = None
    tags: list = []
    category: str = "note"


class ImportURLRequest(BaseModel):
    url: str
    title: str = None
    tags: list = []


class ImportSnippetRequest(BaseModel):
    content: str
    label: str = None


# ── DOCUMENTS ────────────────────────────────────────────

@router.post("/documents/text")
async def import_text_document(req: ImportTextRequest):
    """Import text content into memory."""
    return await agents["document"].import_text(
        content=req.content, title=req.title, tags=req.tags, category=req.category,
    )


@router.post("/documents/url")
async def import_url_document(req: ImportURLRequest):
    """Import content from a URL."""
    return await agents["document"].import_url(url=req.url, title=req.title, tags=req.tags)


@router.post("/documents/snippet")
async def import_snippet(req: ImportSnippetRequest):
    """Import a quick snippet/clipboard."""
    return await agents["document"].import_snippet(content=req.content, label=req.label)


@router.get("/documents")
async def list_documents(category: str = None, limit: int = 20):
    """List all imported documents."""
    return await agents["document"].list_documents(category, limit)


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    """Get a specific document."""
    return await agents["document"].get_document(doc_id)


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document."""
    return await agents["document"].delete_document(doc_id)


@router.get("/documents/search")
async def search_documents(query: str, limit: int = 10):
    """Search within imported documents."""
    return await agents["document"].search_documents(query, limit)


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...), title: str = "Untitled", category: str = "document"
):
    """Upload a document file."""
    content = await file.read()
    content_text = content.decode("utf-8", errors="ignore")
    return await agents["document"].add_document(
        title=title, content=content_text,
        doc_type=file.content_type or "text/plain", category=category,
    )


# ── RAG ─────────────────────────────────────────────────

class RAGQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    method: str = Field(default="hybrid", pattern="^(vector|bm25|hybrid)$")


_rag_agent = lambda: agents.get("rag")


@router.post("/rag/query")
async def rag_query(req: RAGQueryRequest):
    """Query with RAG context (vector, BM25, or hybrid)."""
    rag = _rag_agent()
    if not rag:
        return {"error": "RAG agent not available"}
    return await rag.query_with_context(query=req.query, top_k=req.top_k)


@router.post("/rag/wikipedia")
async def rag_wikipedia_search(query: str, max_results: int = 3):
    """Search Wikipedia and add to RAG knowledge base."""
    rag = _rag_agent()
    if not rag:
        return {"error": "RAG agent not available"}
    return await rag.wiki_qa(query, max_results)


@router.post("/rag/search")
async def rag_search(query: str, method: str = "hybrid", top_k: int = 5):
    """Direct RAG search without LLM synthesis."""
    rag = _rag_agent()
    if not rag:
        return {"error": "RAG agent not available"}
    results = await rag.retrieve(query=query, top_k=top_k, use_method=method)
    return {"results": results, "method": method}


@router.post("/rag/comprehensive")
async def rag_comprehensive_search(query: str):
    """Comprehensive search across all sources."""
    rag = _rag_agent()
    if not rag:
        return {"error": "RAG agent not available"}
    return await rag.comprehensive_search(query)


@router.get("/rag/stats")
async def rag_stats():
    """Get RAG system statistics."""
    rag = _rag_agent()
    if not rag:
        return {"error": "RAG agent not available"}
    return await rag.get_stats()


@router.post("/rag/add")
async def rag_add_document(request: Request):
    """Add a document to RAG knowledge base."""
    rag = _rag_agent()
    if not rag:
        return {"error": "RAG agent not available"}
    body = await request.json()
    return await rag.add_document(
        content=body.get("content", ""), title=body.get("title", "Untitled"),
        source=body.get("source", "text"), url=body.get("url"),
    )


@router.post("/rag/clear")
async def rag_clear():
    """Clear all documents from RAG."""
    rag = _rag_agent()
    if not rag:
        return {"error": "RAG agent not available"}
    await rag.clear()
    return {"status": "cleared"}
