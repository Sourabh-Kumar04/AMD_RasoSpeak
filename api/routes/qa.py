"""
QA & Search routes — /qa/* and /search/* endpoints.
Real-time AI question answering and web search.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from api.state import agents, limiter

router = APIRouter(tags=["💬 Q&A & Search"])


# ── REQUEST MODELS ──────────────────────────────────────

class QARequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2_000)
    provider: str | None = Field(default=None)
    context: str | None = Field(default=None, max_length=10_000)
    stream_to_earpiece: bool = True


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    num_results: int = Field(default=5, ge=1, le=20)
    include_summary: bool = True


# ── Q&A ─────────────────────────────────────────────────

@router.post("/qa")
@limiter.limit("10/minute")
async def ask_question(request: Request, req: QARequest, session_id: str = None):
    """Ask a question to AI and get answer (streams to earpiece)."""
    result = await agents["qa"].ask(
        question=req.question,
        provider=req.provider,
        context=req.context,
        stream_to_earpiece=req.stream_to_earpiece,
        session_id=session_id,
    )
    return result


@router.get("/qa/providers")
async def get_qa_providers():
    """Get available AI providers."""
    from config.settings import settings
    available = []
    for provider in ["google", "nvidia", "openai", "anthropic", "huggingface", "openrouter", "opencode", "xai", "deepseek"]:
        config = settings.get_provider_config(provider)
        if config.get("api_key"):
            available.append(provider)
    return {"available": available, "default": settings.default_provider}


# ── SEARCH ─────────────────────────────────────────────

@router.post("/search")
@limiter.limit("30/minute")
async def web_search(request: Request, req: SearchRequest):
    """Search the web for real-time information."""
    result = await agents["search"].search(
        query=req.query,
        num_results=req.num_results,
        include_summary=req.include_summary,
    )
    return result
