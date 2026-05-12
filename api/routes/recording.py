"""
Recording routes — /recordings/* endpoints.
Audio/conversation storage and management.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from api.state import agents, generate_ws_token as _generate_ws_token

router = APIRouter(prefix="/recordings", tags=["🎙️ Recording"])


class StartRecordingRequest(BaseModel):
    metadata: dict = {}


class AudioRecordRequest(BaseModel):
    audio_b64: str
    audio_type: str = "user_speech"
    metadata: dict = {}


@router.post("/{session_id}/start")
async def start_recording(session_id: str, req: StartRecordingRequest = None):
    """Start recording a session and issue a WebSocket token."""
    metadata = req.metadata if req else {}
    result = await agents["recording"].start_session_recording(session_id, metadata)
    await agents["memory"].create_session(session_id)
    ws_token = _generate_ws_token(session_id)
    return {**result, "ws_token": ws_token}


@router.post("/{session_id}/stop")
async def stop_recording(session_id: str):
    """Stop recording a session."""
    return await agents["recording"].stop_session_recording(session_id)


@router.post("/{session_id}/audio")
async def record_audio(session_id: str, req: AudioRecordRequest):
    """Record an audio chunk."""
    return await agents["recording"].record_audio(
        session_id=session_id,
        audio_b64=req.audio_b64,
        audio_type=req.audio_type,
        metadata=req.metadata,
    )


@router.get("")
async def list_recordings(limit: int = 50):
    """List all recorded sessions."""
    return await agents["recording"].get_all_recordings(limit)


@router.get("/{session_id}")
async def get_recording(session_id: str):
    """Get recording data for a specific session."""
    return await agents["recording"].get_session_record(session_id)
