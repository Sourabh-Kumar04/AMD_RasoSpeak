"""
Raso routes — /raso/*, /partner/* (aliases), and /voice/* endpoints.
Your AI companion with memory, wake word detection, and reminders.
"""

from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel, Field

from api.state import agents
from api.middleware.auth import verify_api_key

router = APIRouter(prefix="", tags=["🤖 Raso"])


# ── REQUEST MODELS ──────────────────────────────────────

class PartnerAskRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4_000)
    provider: str | None = None


class ReminderRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    remind_at: str | None = None


class WakeAudioRequest(BaseModel):
    audio_b64: str
    transcript: str = None


class WakeAskRequest(BaseModel):
    transcript: str = Field(..., min_length=1, max_length=2000)
    audio_b64: str = None


# ── RASO CORE ──────────────────────────────────────────

@router.post("/raso/start")
async def start_partner_mode(session_id: str = None):
    """Start continuous Raso mode — your AI companion is always listening for your commands."""
    return await agents["raso"].start_continuous_mode(session_id)


@router.post("/raso/stop")
async def stop_partner_mode():
    """Stop continuous Raso mode."""
    return await agents["raso"].stop_continuous_mode()


@router.get("/raso/status")
async def get_partner_status():
    """Get Raso companion status."""
    current_provider = await agents["raso"].get_current_provider()
    prefs = await agents["shared_memory"].get_user_preferences()
    return {
        "continuous_mode": agents["raso"].is_continuous_mode(),
        "current_provider": current_provider,
        "default_provider": prefs.get("preferred_ai_provider", "qwen_local"),
        "temporary_provider": prefs.get("temporary_ai_provider"),
    }


@router.post("/raso/provider")
async def set_partner_provider(provider: str, temporary: bool = False):
    """Set the AI provider for Raso."""
    if temporary:
        await agents["shared_memory"].set_user_preference("temporary_ai_provider", provider)
    else:
        await agents["shared_memory"].set_user_preference("preferred_ai_provider", provider)
        await agents["shared_memory"].set_user_preference("temporary_ai_provider", None)
    provider_names = {
        "openai": "ChatGPT", "anthropic": "Claude", "google": "Gemini",
        "xai": "Grok", "qwen_local": "Local Qwen",
    }
    return {
        "provider": provider,
        "display_name": provider_names.get(provider, provider),
        "temporary": temporary,
        "message": f"Switched to {provider_names.get(provider, provider)}" + (" for this question" if temporary else ""),
    }


@router.post("/raso/ask")
async def ask_partner(request: Request, req: PartnerAskRequest):
    """Ask your AI partner anything. Uses past conversations + web search + knowledge."""
    return await agents["raso"].ask_partner(req.message, req.provider)


@router.post("/raso/listen")
async def partner_listen(user_input: str, audio_b64: str = None):
    """In continuous mode, let partner listen and remember."""
    return await agents["raso"].listen_and_remember(user_input, audio_b64)


@router.get("/raso/query")
async def query_past_conversations(query: str):
    """Query past conversations."""
    return await agents["raso"].query_past(query)


@router.post("/raso/reminder")
async def set_partner_reminder(req: ReminderRequest):
    """Set a reminder."""
    return await agents["raso"].set_reminder(req.message, req.remind_at)


@router.get("/raso/reminders")
async def get_partner_reminders():
    """Get all reminders."""
    return await agents["raso"].get_reminders()


@router.delete("/raso/reminder/{reminder_id}")
async def delete_partner_reminder(reminder_id: str):
    """Delete a reminder."""
    return await agents["raso"].delete_reminder(reminder_id)


@router.get("/raso/summarize")
async def summarize_partner_conversations(days: int = 7):
    """Summarize conversations over past N days."""
    return await agents["raso"].summarize_conversations(days)


@router.post("/raso/wake")
async def partner_wake_request(message: str):
    """Alternative endpoint for 'Hey Raso' style queries via REST API."""
    from agents.wake_word_agent import check_for_wake_word, extract_command_after_wake

    if not check_for_wake_word(message):
        return {"wake_detected": False, "answer": None, "message": "Wake word 'Hey Raso' not detected."}

    command = extract_command_after_wake(message)
    if not command:
        result = await agents["raso"].start_continuous_mode()
        return {"wake_detected": True, "answer": "I'm here! What would you like to know?", "message": result.get("message")}

    result = await agents["raso"].ask_partner(command)
    return {"wake_detected": True, "command": command, "answer": result.get("answer", ""), "processing_ms": result.get("processing_ms", 0)}


# ── VOICE / WAKE WORD ──────────────────────────────────

@router.post("/voice/start")
async def start_wake_listening():
    """Start listening for 'Hey Raso' wake word."""
    return await agents["wake_word"].start_listening()


@router.post("/voice/stop")
async def stop_wake_listening():
    """Stop wake word listening."""
    return await agents["wake_word"].stop_listening()


@router.get("/voice/status")
async def get_wake_status():
    """Get wake word listening status."""
    return {"listening": agents["wake_word"].is_listening(), "wake_word": "Hey Raso"}


@router.post("/voice/process")
async def process_wake_audio(req: WakeAudioRequest):
    """Process audio for wake word detection."""
    result = await agents["wake_word"].process_audio(req.audio_b64)
    if req.transcript:
        from agents.wake_word_agent import check_for_wake_word, extract_command_after_wake
        if check_for_wake_word(req.transcript):
            activation = agents["wake_word"].activate_partner()
            command = extract_command_after_wake(req.transcript)
            return {"wake_detected": True, "activated": True, "command": command, **activation}
    return result


@router.post("/voice/ask")
async def wake_word_answer(req: WakeAskRequest):
    """Complete flow: 'Hey Raso, tell me what is AMD'."""
    from agents.wake_word_agent import check_for_wake_word, extract_command_after_wake
    import logging
    log = logging.getLogger("rasospeak")

    log.info(f"Wake/ask request: {req.transcript[:50]}...")
    if not check_for_wake_word(req.transcript):
        return {"wake_detected": False, "answer": None, "message": "Wake word not detected. Say 'Hey Raso' first."}

    command = extract_command_after_wake(req.transcript)
    if not command:
        result = await agents["raso"].start_continuous_mode()
        return {"wake_detected": True, "command": None, "answer": "I'm here! What would you like to know?", "message": result.get("message"), "activated": True}

    log.info(f"Processing command: {command[:50]}...")
    result = await agents["raso"].ask_partner(command)
    await agents["raso"].listen_and_remember(user_input=req.transcript, audio_b64=req.audio_b64, timestamp=None)
    return {
        "wake_detected": True, "command": command, "answer": result.get("answer", ""),
        "provider": result.get("provider", "unknown"), "processing_ms": result.get("processing_ms", 0),
        "web_info_used": result.get("web_info_used", False), "past_context_used": result.get("past_context_used", False),
    }


# ── PARTNER ALIASES (backward compat) ──────────────────
# These delegate to the raso agent directly.

@router.post("/partner/start")
async def partner_start_alias(session_id: str = None):
    """Alias for /raso/start (backward compatibility). DEPRECATED — use /raso/start."""
    return await agents["raso"].start_continuous_mode(session_id)


@router.post("/partner/stop")
async def partner_stop_alias():
    """Alias for /raso/stop (backward compatibility). DEPRECATED — use /raso/stop."""
    return await agents["raso"].stop_continuous_mode()


@router.get("/partner/status")
async def partner_status_alias():
    """Alias for /raso/status (backward compatibility)."""
    current_provider = await agents["raso"].get_current_provider()
    prefs = await agents["shared_memory"].get_user_preferences()
    return {
        "continuous_mode": agents["raso"].is_continuous_mode(),
        "current_provider": current_provider,
        "default_provider": prefs.get("preferred_ai_provider", "qwen_local"),
        "temporary_provider": prefs.get("temporary_ai_provider"),
    }


@router.post("/partner/ask")
async def partner_ask_alias(req: PartnerAskRequest):
    """Alias for /raso/ask (backward compatibility)."""
    return await agents["raso"].ask_partner(req.message, req.provider)


@router.get("/partner/query")
async def partner_query_alias(query: str):
    """Alias for /raso/query (backward compatibility)."""
    return await agents["raso"].query_past(query)


@router.post("/partner/reminder")
async def partner_reminder_alias(req: ReminderRequest):
    """Alias for /raso/reminder (backward compatibility)."""
    return await agents["raso"].set_reminder(req.message, req.remind_at)


@router.get("/partner/reminders")
async def partner_reminders_alias():
    """Alias for /raso/reminders (backward compatibility)."""
    return await agents["raso"].get_reminders()


@router.post("/partner/provider")
async def partner_provider_alias(provider: str, temporary: bool = False):
    """Alias for /raso/provider (backward compatibility)."""
    if temporary:
        await agents["shared_memory"].set_user_preference("temporary_ai_provider", provider)
    else:
        await agents["shared_memory"].set_user_preference("preferred_ai_provider", provider)
        await agents["shared_memory"].set_user_preference("temporary_ai_provider", None)
    return {"provider": provider, "temporary": temporary}
