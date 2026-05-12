"""
Analytics routes — /analytics/* endpoints.
Session & user performance insights.
"""

from fastapi import APIRouter

from api.state import agents

router = APIRouter(prefix="/analytics", tags=["📊 Analytics"])


@router.get("/session/{session_id}")
async def get_session_analytics(session_id: str):
    """Get comprehensive analytics for a session."""
    return await agents["analytics"].generate_session_analytics(session_id)


@router.get("/user/{user_id}")
async def get_user_analytics(user_id: str, days: int = 30):
    """Get analytics across multiple sessions for a user."""
    return await agents["analytics"].generate_user_analytics(user_id, days)


@router.get("/improvement/{user_id}")
async def get_improvement_report(user_id: str):
    """Get speech improvement report over time."""
    return await agents["analytics"].get_speech_improvement_report(user_id)


@router.get("/qa-topics/{user_id}")
async def get_qa_topics(user_id: str):
    """Analyze what topics user asks about most."""
    return await agents["analytics"].get_qa_topics_analysis(user_id)
