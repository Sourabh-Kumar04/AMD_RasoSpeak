"""
Coaching routes — /segment, /sessions, and WebSocket endpoint.
Real-time speech coaching loop and script segmentation.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from pydantic import BaseModel

from api.state import agents, generate_ws_token, validate_ws_token
from models.schemas import WSMessage, WSMessageType, SessionConfig, AudioChunk

router = APIRouter(tags=["🎯 Coaching"])


class SegmentRequest(BaseModel):
    script: str
    target_chunk_size: int = 8
    style: str = "presentation"


@router.post("/segment")
async def segment_script(req: SegmentRequest):
    """Segment a raw script into LLM-optimized chunks."""
    return await agents["segmentation"].segment(
        script=req.script,
        target_chunk_size=req.target_chunk_size,
        style=req.style,
    )


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Retrieve session data for the stats dashboard."""
    session = await agents["memory"].get_session(session_id)
    if not session:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/sessions/{session_id}/insights")
async def get_session_insights(session_id: str):
    """Get AI-generated insights from a completed session."""
    session = await agents["memory"].get_session(session_id)
    if not session:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")
    return await agents["coaching"].generate_session_insights(session)


# ── WEBSOCKET ───────────────────────────────────────────

@router.websocket("/ws/{session_id}")
async def websocket_session(websocket: WebSocket, session_id: str):
    """Main WebSocket endpoint — drives the coaching loop in real time."""
    await websocket.accept()

    token = websocket.query_params.get("token")
    if not validate_ws_token(session_id, token):
        log.warning(f"WebSocket auth failed for session: {session_id}")
        await websocket.close(code=4001)
        return
    import json as json_module
    import logging

    log = logging.getLogger("rasospeak")

    log.info(f"WebSocket connected: {session_id}")
    await agents["memory"].create_session(session_id)

    async def send_ws(ws: WebSocket, msg_type: WSMessageType, data: dict):
        try:
            await ws.send_text(json_module.dumps({"type": msg_type.value, "data": data}))
        except Exception as e:
            log.warning(f"WebSocket send failed: {e}")

    try:
        async for raw_msg in websocket.iter_text():
            try:
                msg = WSMessage(**json_module.loads(raw_msg))
            except Exception as e:
                await send_ws(websocket, WSMessageType.ERROR, {"message": f"Bad message: {e}"})
                continue

            # ── SESSION_START ──────────────────────────
            if msg.type == WSMessageType.SESSION_START:
                config = SessionConfig(**msg.data.get("config", {}))
                await agents["memory"].update_config(session_id, config)
                await send_ws(websocket, WSMessageType.SESSION_READY, {
                    "session_id": session_id, "message": "Session initialized — agents ready"
                })
                log.info(f"Session {session_id} started | mode={config.mode} strict={config.strict}")

            # ── AUDIO_CHUNK ────────────────────────────
            elif msg.type == WSMessageType.AUDIO_CHUNK:
                chunk = AudioChunk(**msg.data)
                await _handle_audio_chunk(send_ws, websocket, session_id, chunk)

            # ── CHUNK_DONE ─────────────────────────────
            elif msg.type == WSMessageType.CHUNK_DONE:
                chunk_idx = msg.data.get("chunk_index", 0)
                await agents["memory"].record_skip(session_id, chunk_idx)
                log.info(f"Session {session_id} — chunk {chunk_idx} manually skipped")

            # ── SESSION_END ────────────────────────────
            elif msg.type == WSMessageType.SESSION_END:
                summary = await _handle_session_end(session_id)
                await send_ws(websocket, WSMessageType.SESSION_SUMMARY, summary)
                break

            # ── QUESTION ────────────────────────────────
            elif msg.type == WSMessageType.QUESTION:
                question = msg.data.get("question", "")
                provider = msg.data.get("provider")
                context = msg.data.get("context")
                session_data = await agents["memory"].get_session(session_id)
                script_context = None
                if session_data:
                    chunks = session_data.get("chunk_records", {})
                    if chunks:
                        script_context = " ".join(r.get("expected", "") for r in chunks.values())

                answer_result = await agents["qa"].ask(
                    question=question, provider=provider, context=context or script_context,
                    stream_to_earpiece=True, session_id=session_id,
                )
                await send_ws(websocket, WSMessageType.ANSWER, {
                    "question": question, "answer": answer_result["answer"],
                    "provider": answer_result.get("provider", "unknown"),
                    "stream_to_earpiece": True, "processing_ms": answer_result.get("processing_ms", 0),
                })
                await agents["recording"].record_qa_interaction(
                    session_id, question, answer_result["answer"], answer_result.get("provider", "unknown"))
                log.info(f"Answer sent to client: {answer_result['answer'][:50]}...")

            # ── SEARCH_QUERY ────────────────────────────
            elif msg.type == WSMessageType.SEARCH_QUERY:
                query = msg.data.get("query", "")
                num_results = msg.data.get("num_results", 5)
                search_result = await agents["search"].search(query=query, num_results=num_results, include_summary=True)
                await send_ws(websocket, WSMessageType.SEARCH_RESULTS, {
                    "query": query, "results": search_result.get("results", []),
                    "summary": search_result.get("summary", ""),
                    "processing_ms": search_result.get("processing_ms", 0),
                })
                log.info(f"Search complete: {len(search_result.get('results', []))} results")

            # ── PARTNER_START ───────────────────────────
            elif msg.type == WSMessageType.PARTNER_START:
                result = await agents["raso"].start_continuous_mode(session_id)
                await send_ws(websocket, WSMessageType.PARTNER_READY, {
                    "status": "active", "session_id": session_id,
                    "message": result.get("message", "Partner mode started"),
                })
                log.info(f"Partner mode started: {session_id}")

            # ── PARTNER_STOP ────────────────────────────
            elif msg.type == WSMessageType.PARTNER_STOP:
                result = await agents["raso"].stop_continuous_mode()
                await send_ws(websocket, WSMessageType.PARTNER_READY, {
                    "status": "stopped", "message": result.get("message", "Partner mode stopped"),
                })
                log.info(f"Partner mode stopped: {session_id}")

            # ── PARTNER_MESSAGE ────────────────────────
            elif msg.type == WSMessageType.PARTNER_MESSAGE:
                message_text = msg.data.get("message", "")
                provider = msg.data.get("provider")
                result = await agents["raso"].ask_partner(question=message_text, provider=provider)
                await send_ws(websocket, WSMessageType.PARTNER_RESPONSE, {
                    "message": message_text, "response": result.get("answer", ""),
                    "provider": result.get("provider", "unknown"), "processing_ms": result.get("processing_ms", 0),
                })
                await agents["raso"].listen_and_remember(user_input=message_text, timestamp=None)
                log.info(f"Partner response sent: {result.get('answer', '')[:50]}...")

            # ── WAKE_DETECTED ──────────────────────────
            elif msg.type == WSMessageType.WAKE_DETECTED:
                from agents.wake_word_agent import check_for_wake_word, extract_command_after_wake
                transcript = msg.data.get("transcript", "")
                log.info(f"Wake word detected: {transcript[:50]}...")

                if not check_for_wake_word(transcript):
                    await send_ws(websocket, WSMessageType.ERROR, {"message": "Wake word not detected. Say 'Hey Raso' first."})
                    continue

                await agents["raso"].start_continuous_mode(session_id)
                command = extract_command_after_wake(transcript)

                if not command:
                    await send_ws(websocket, WSMessageType.PARTNER_READY, {
                        "status": "active", "wake_detected": True, "message": "I'm here! What would you like to know?",
                    })
                    continue

                log.info(f"Processing command: {command[:50]}...")
                result = await agents["raso"].ask_partner(command)
                await send_ws(websocket, WSMessageType.PARTNER_RESPONSE, {
                    "wake_detected": True, "command": command, "response": result.get("answer", ""),
                    "provider": result.get("provider", "unknown"), "processing_ms": result.get("processing_ms", 0),
                    "tts_ready": True,
                })
                await agents["raso"].listen_and_remember(user_input=transcript, timestamp=None)
                await agents["recording"].record_qa_interaction(
                    session_id, command, result.get("answer", ""), result.get("provider", "unknown"))
                log.info(f"Wake word answer sent: {result.get('answer', '')[:50]}...")

            # ── IMPORT_DOCUMENT ────────────────────────
            elif msg.type == WSMessageType.IMPORT_DOCUMENT:
                content = msg.data.get("content", "")
                title = msg.data.get("title", "")
                doc_type = msg.data.get("type", "note")
                log.info(f"Import document: {title or 'Untitled'}")
                if doc_type == "url":
                    result = await agents["document"].import_url(content)
                elif doc_type == "snippet":
                    result = await agents["document"].import_snippet(content, title)
                else:
                    result = await agents["document"].import_text(content, title)
                await send_ws(websocket, WSMessageType.SESSION_READY, {
                    "message": f"Document imported: {result.get('title', 'Done')}",
                    "document_id": result.get("document_id"),
                })

    except WebSocketDisconnect:
        log.info(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        log.error(f"Session {session_id} error: {e}", exc_info=True)
        await send_ws(websocket, WSMessageType.ERROR, {"message": str(e)})
    finally:
        await agents["memory"].close_session(session_id)


# ── AUDIO HANDLING HELPERS ──────────────────────────────

async def _handle_audio_chunk(send_ws, websocket, session_id, chunk):
    """Full pipeline for one audio chunk: audio → transcription → scoring → coaching."""
    session = await agents["memory"].get_session(session_id)
    config = session.get("config", {})
    expected_text = chunk.expected_text

    transcript_result = await agents["transcription"].transcribe(
        audio_b64=chunk.audio_b64, sample_rate=chunk.sample_rate, language="en",
    )
    await send_ws(websocket, WSMessageType.TRANSCRIPT, {
        "text": transcript_result["transcript"], "is_final": transcript_result["is_final"],
        "confidence": transcript_result["confidence"], "words": transcript_result.get("words", []),
        "processing_ms": transcript_result["processing_ms"],
    })

    if not transcript_result["is_final"]:
        return

    spoken_text = transcript_result["transcript"]
    user_history = await agents["memory"].get_weak_words(session_id)
    score_result = await agents["scoring"].score(
        expected=expected_text, spoken=spoken_text,
        strict_level=config.get("strict", 3), user_weak_words=user_history,
    )

    await send_ws(websocket, WSMessageType.SCORE, {
        "chunk_index": chunk.chunk_index, "accuracy": score_result["accuracy"],
        "fluency": score_result["fluency"], "completeness": score_result["completeness"],
        "overall": score_result["overall"], "passed": score_result["passed"],
        "missing_concepts": score_result["missing_concepts"],
        "feedback_brief": score_result["feedback_brief"], "processing_ms": score_result["processing_ms"],
    })

    await agents["memory"].record_chunk_result(
        session_id, chunk.chunk_index, score_result, spoken_text, expected_text,
    )

    if score_result["passed"]:
        progress = await agents["memory"].get_progress(session_id)
        await send_ws(websocket, WSMessageType.ADVANCE, {
            "chunk_index": chunk.chunk_index, "next_index": chunk.chunk_index + 1,
            "progress_pct": progress["pct"], "segments_done": progress["done"],
        })
    else:
        attempts = await agents["memory"].get_attempts(session_id, chunk.chunk_index)
        coach_result = await agents["coaching"].coach(
            expected=expected_text, spoken=spoken_text, score=score_result,
            mode=config.get("mode", "hint"), attempt_number=attempts, user_weak_words=user_history,
        )
        await send_ws(websocket, WSMessageType.COACHING, {
            "chunk_index": chunk.chunk_index, "strategy": coach_result["strategy"],
            "tts_text": coach_result["tts_text"], "display_text": coach_result["display_text"],
            "missed_concepts": coach_result["missed_concepts"],
            "encouragement": coach_result["encouragement"],
            "auto_skip": coach_result.get("auto_skip", False), "processing_ms": coach_result["processing_ms"],
        })


async def _handle_session_end(session_id: str) -> dict:
    """Generate session summary with AI insights."""
    session = await agents["memory"].get_session(session_id)
    insights = await agents["coaching"].generate_session_insights(session)
    await agents["memory"].persist_session(session_id)
    return {
        "session_id": session_id, "stats": session.get("stats", {}),
        "insights": insights, "weak_words": session.get("weak_words", []),
    }
