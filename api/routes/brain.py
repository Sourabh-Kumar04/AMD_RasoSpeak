"""
Brain routes — all /brain/* endpoints.
Complete memory system: store, recall, persona, goals, skills, compression,
emotions, versioning, quality, predictive, backup/restore, export/import,
encryption, visualization, patterns, sync.
"""

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from api.state import agents

router = APIRouter(prefix="/brain", tags=["🧠 Brain"])


# ── REQUEST MODELS ──────────────────────────────────────

class BrainStoreRequest(BaseModel):
    content: str
    memory_type: str = "conversation"
    tier: str = "long_term"
    importance: int = 3
    tags: list = []
    source: str = "unknown"


class BrainConversationRequest(BaseModel):
    user_input: str
    ai_response: str
    ai_provider: str
    context: str = None


class BrainDocumentRequest(BaseModel):
    content: str
    title: str
    doc_type: str = "document"
    tags: list = []


class BrainFactRequest(BaseModel):
    fact: str
    category: str = "general"
    importance: int = 3


class BrainAudioRequest(BaseModel):
    session_id: str
    transcription: str
    speakers: list = []
    duration: float = 0


class BrainRelationshipRequest(BaseModel):
    source_id: str
    target_id: str
    relation_type: str
    weight: float = 1.0


class BrainRecallRequest(BaseModel):
    query: str = None
    memory_type: str = None
    tier: str = None
    limit: int = 20
    time_range: str = None


class UnifiedRAGRequest(BaseModel):
    query: str
    memory_top_k: int = 5
    doc_top_k: int = 5
    use_memory: bool = True
    use_docs: bool = True
    use_llm: bool = True


# ── CORE STORE / RECALL ─────────────────────────────────

@router.post("/store")
async def brain_store(req: BrainStoreRequest):
    """Store a memory node in the second brain."""
    from agents.second_brain_agent import MemoryType, MemoryTier, Importance
    brain = agents.get("brain")
    if not brain:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Second Brain not available")
    return await brain.store(
        content=req.content,
        memory_type=MemoryType(req.memory_type),
        tier=MemoryTier(req.tier),
        importance=Importance(req.importance),
        tags=req.tags,
        source=req.source,
    )


@router.post("/conversation")
async def brain_add_conversation(req: BrainConversationRequest):
    """Add a conversation to second brain."""
    return await agents["brain"].add_conversation(
        user_input=req.user_input,
        ai_response=req.ai_response,
        ai_provider=req.ai_provider,
        context=req.context,
    )


@router.post("/document")
async def brain_add_document(req: BrainDocumentRequest):
    """Add a document to second brain."""
    return await agents["brain"].add_document(
        content=req.content,
        title=req.title,
        doc_type=req.doc_type,
        tags=req.tags,
    )


@router.post("/fact")
async def brain_add_fact(req: BrainFactRequest):
    """Add a fact about the user."""
    from agents.second_brain_agent import Importance
    return await agents["brain"].add_user_fact(
        fact=req.fact,
        category=req.category,
        importance=Importance(req.importance),
    )


@router.post("/audio")
async def brain_add_audio(req: BrainAudioRequest):
    """Store an audio conversation with full processing."""
    return await agents["brain"].store_audio_conversation(
        session_id=req.session_id,
        transcription=req.transcription,
        speakers=req.speakers,
        duration=req.duration,
    )


@router.post("/relationship")
async def brain_add_relationship(req: BrainRelationshipRequest):
    """Add a relationship edge between nodes."""
    return await agents["brain"].add_relationship(
        source_id=req.source_id,
        target_id=req.target_id,
        relation_type=req.relation_type,
        weight=req.weight,
    )


@router.post("/recall")
async def brain_recall(req: BrainRecallRequest):
    """Recall memories with hybrid search."""
    from agents.second_brain_agent import MemoryType, MemoryTier
    return await agents["brain"].recall(
        query=req.query,
        memory_type=MemoryType(req.memory_type) if req.memory_type else None,
        tier=MemoryTier(req.tier) if req.tier else None,
        limit=req.limit,
        time_range=req.time_range,
    )


@router.get("/recall/graph")
async def brain_recall_graph(entity: str, depth: int = 2):
    """Recall related nodes through the knowledge graph."""
    return await agents["brain"].recall_graph(entity=entity, depth=depth)


@router.get("/recall/temporal")
async def brain_recall_temporal(query: str, start_date: str = None, end_date: str = None):
    """Recall memories within a time range."""
    return await agents["brain"].recall_temporal(
        query=query, start_date=start_date, end_date=end_date,
    )


@router.get("/recall/conversation")
async def brain_recall_conversation(query: str = None, limit: int = 10):
    """Recall past conversations."""
    return await agents["brain"].recall_conversation(query=query, limit=limit)


@router.get("/recall/entity/{entity_name}")
async def brain_recall_entity(entity_name: str, limit: int = 10):
    """Recall all memories related to an entity."""
    return await agents["brain"].recall_entity(entity_name=entity_name, limit=limit)


@router.get("/recall/topic/{topic}")
async def brain_recall_topic(topic: str, limit: int = 20):
    """Recall all memories related to a topic."""
    return await agents["brain"].recall_by_topic(topic=topic, limit=limit)


@router.get("/recall/audio")
async def brain_recall_audio(query: str = None, session_id: str = None, limit: int = 10):
    """Recall audio conversations."""
    return await agents["brain"].recall_audio_conversations(
        query=query, session_id=session_id, limit=limit,
    )


@router.get("/related/{node_id}")
async def brain_find_related(node_id: str, relation_type: str = None, depth: int = 1):
    """Find nodes related to a given node."""
    return await agents["brain"].find_related(node_id=node_id, relation_type=relation_type, depth=depth)


# ── WORKING MEMORY ─────────────────────────────────────

@router.get("/working-memory")
async def brain_get_working_memory():
    """Get current working memory contents."""
    return await agents["brain"].get_working_memory()


@router.post("/working-memory/clear")
async def brain_clear_working_memory():
    """Clear working memory."""
    await agents["brain"].clear_working_memory()
    return {"status": "cleared"}


# ── CONTEXT ─────────────────────────────────────────────

@router.get("/context")
async def brain_get_context(ai_name: str = None, max_tokens: int = 4000):
    """Get formatted context for AI prompts."""
    return await agents["brain"].get_context_for_ai(ai_name=ai_name, max_tokens=max_tokens)


# ── REVISE / FORGET ────────────────────────────────────

@router.post("/revise/{node_id}")
async def brain_revise_memory(node_id: str, new_content: Any):
    """Revise an existing memory."""
    return await agents["brain"].revise_memory(node_id=node_id, new_content=new_content)


@router.post("/forget/{node_id}")
async def brain_forget(node_id: str, reason: str = "user_request"):
    """Forget a memory."""
    return await agents["brain"].forget(node_id=node_id, reason=reason)


@router.post("/auto-forget")
async def brain_auto_forget(threshold: float = 0.2):
    """Automatically forget low-importance memories."""
    return await agents["brain"].auto_forget_low_importance(threshold=threshold)


# ── WEAK WORDS ─────────────────────────────────────────

@router.get("/weak-words")
async def brain_get_weak_words(limit: int = 20):
    """Get all weak words."""
    return await agents["brain"].get_weak_words(limit=limit)


@router.post("/weak-word")
async def brain_add_weak_word(word: str, context: str = None, session_id: str = None):
    """Add a weak word."""
    return await agents["brain"].add_weak_word(word=word, context=context, session_id=session_id)


# ── SESSIONS ───────────────────────────────────────────

@router.get("/sessions")
async def brain_get_recent_sessions(limit: int = 10):
    """Get recent session summaries."""
    return await agents["brain"].get_recent_sessions(limit=limit)


@router.post("/session-summary")
async def brain_save_session_summary(session_id: str, summary: dict):
    """Save a session summary."""
    return await agents["brain"].save_session_summary(session_id=session_id, summary=summary)


# ── STATS / SIZE / CLEAR ───────────────────────────────

@router.get("/stats")
async def brain_get_stats():
    """Get comprehensive memory statistics."""
    return await agents["brain"].get_memory_stats()


@router.get("/size")
async def brain_get_size():
    """Get memory size in MB."""
    size = await agents["brain"].get_memory_size_mb()
    return {"size_mb": round(size, 2)}


@router.post("/clear")
async def brain_clear_all():
    """Clear all second brain memory."""
    return await agents["brain"].clear_all()


# ── PERSONA ─────────────────────────────────────────────

@router.get("/persona")
async def brain_get_persona():
    """Get the current user persona profile."""
    return await agents["brain"].get_persona()


@router.put("/persona/{field}")
async def brain_update_persona(field: str, value: str = None, values: list[str] = None):
    """Update a specific field in the user persona."""
    if values is not None:
        return await agents["brain"].update_persona_field(field, values)
    elif value is not None:
        return await agents["brain"].update_persona_field(field, value)
    return {"error": "Provide 'value' or 'values' parameter"}


@router.post("/persona/extract")
async def brain_extract_persona(conversation: str = None):
    """Extract persona from recent conversations."""
    return await agents["brain"].extract_and_update_persona(conversation)


# ── GOALS ───────────────────────────────────────────────

@router.post("/goals")
async def brain_add_goal(
    title: str, description: str = None, deadline: str = None,
    priority: int = 3, category: str = "general"
):
    """Add a new goal."""
    return await agents["brain"].add_goal(title, description, deadline, priority, category)


@router.put("/goals/{goal_id}/progress")
async def brain_update_goal_progress(goal_id: str, progress: float, note: str = None):
    """Update progress on a goal."""
    return await agents["brain"].update_goal_progress(goal_id, progress, note)


@router.put("/goals/{goal_id}/status")
async def brain_set_goal_status(goal_id: str, status: str):
    """Set goal status (active, completed, paused, abandoned)."""
    from agents.second_brain_agent import GoalStatus
    return await agents["brain"].set_goal_status(goal_id, GoalStatus(status))


@router.post("/goals/{goal_id}/blocker")
async def brain_add_goal_blocker(goal_id: str, blocker: str):
    """Add a blocker to a goal."""
    return await agents["brain"].add_goal_blocker(goal_id, blocker)


@router.get("/goals/active")
async def brain_get_active_goals():
    """Get all active goals."""
    return {"goals": await agents["brain"].get_active_goals()}


@router.get("/goals")
async def brain_get_all_goals():
    """Get all goals."""
    return {"goals": await agents["brain"].get_all_goals()}


@router.post("/goals/extract")
async def brain_extract_goals(conversation: str):
    """Extract goals from conversation text."""
    goals = await agents["brain"].extract_goals_from_conversation(conversation)
    return {"goals": [g.to_dict() for g in goals]}


# ── SKILLS ──────────────────────────────────────────────

@router.post("/skills")
async def brain_add_skill(
    name: str, level: str = "beginner", category: str = "general", description: str = None
):
    """Add a skill to track."""
    from agents.second_brain_agent import SkillLevel
    return await agents["brain"].add_skill(name, SkillLevel(level), category, description)


@router.put("/skills/{skill_name}/level")
async def brain_update_skill_level(skill_name: str, level: str):
    """Update skill level."""
    from agents.second_brain_agent import SkillLevel
    return await agents["brain"].update_skill_level(skill_name, SkillLevel(level))


@router.get("/skills")
async def brain_get_all_skills():
    """Get all tracked skills."""
    return {"skills": await agents["brain"].get_all_skills()}


@router.get("/skills/{category}")
async def brain_get_skills_by_category(category: str):
    """Get skills in a specific category."""
    return {"skills": await agents["brain"].get_skills_by_category(category)}


@router.post("/skills/extract")
async def brain_extract_skills(conversation: str):
    """Extract skills from conversation text."""
    skills = await agents["brain"].extract_skills_from_conversation(conversation)
    return {"skills": [s.to_dict() for s in skills]}


# ── COMPRESSION ─────────────────────────────────────────

@router.post("/compress")
async def brain_compress_memories(days_old: int = 30):
    """Compress memories older than specified days into summaries."""
    return await agents["brain"].compress_old_memories(days_old)


@router.get("/summaries/{summary_id}")
async def brain_get_summary(summary_id: str):
    """Get a specific memory summary."""
    return await agents["brain"].get_summary(summary_id)


@router.get("/summaries")
async def brain_search_summaries(query: str):
    """Search through memory summaries."""
    return {"summaries": await agents["brain"].search_summaries(query)}


# ── AUTO-LINKING ────────────────────────────────────────

@router.post("/links/auto")
async def brain_auto_link():
    """Automatically link related memories."""
    return await agents["brain"].auto_link_memories()


# ── EMOTIONS ───────────────────────────────────────────

@router.post("/emotions/analyze")
async def brain_analyze_emotions(conversation: str):
    """Analyze emotions in a conversation."""
    return await agents["brain"].analyze_emotions(conversation)


@router.post("/emotions")
async def brain_store_emotional(conversation: str, emotion_type: str, intensity: float = 0.5, topic: str = None):
    """Store emotional memory from conversation."""
    return await agents["brain"].store_emotional_memory(conversation, emotion_type, intensity, topic)


# ── VERSIONING ──────────────────────────────────────────

@router.get("/versions/{node_id}")
async def brain_get_node_versions(node_id: str):
    """Get all versions of a memory node."""
    return {"versions": await agents["brain"].get_node_versions(node_id)}


@router.post("/versions/{node_id}")
async def brain_revert_to_version(node_id: str, version: int):
    """Revert a memory node to a previous version."""
    return await agents["brain"].revert_to_version(node_id, version)


# ── QUALITY ─────────────────────────────────────────────

@router.get("/quality/{node_id}")
async def brain_score_quality(node_id: str):
    """Get quality score for a specific memory."""
    score = await agents["brain"].score_memory_quality(node_id)
    return {"node_id": node_id, "quality_score": score}


@router.get("/quality")
async def brain_quality_report():
    """Get comprehensive memory quality report."""
    return await agents["brain"].get_quality_report()


# ── PREDICTIVE ─────────────────────────────────────────

@router.get("/suggest/{node_id}")
async def brain_suggest_related(node_id: str):
    """Suggest memories related to a given memory."""
    return {"suggestions": await agents["brain"].suggest_related_memories(node_id)}


@router.get("/predict")
async def brain_predict_next():
    """Predict the next likely memory based on patterns."""
    return await agents["brain"].predict_next_memory()


# ── BACKUP & RESTORE ────────────────────────────────────

@router.post("/backup")
async def brain_create_backup(description: str = "", tags: list[str] = None):
    """Create a full backup snapshot."""
    return await agents["brain"].create_backup(description, tags)


@router.get("/backups")
async def brain_list_backups():
    """List all available backups."""
    return {"backups": await agents["brain"].list_backups()}


@router.post("/restore/{backup_id}")
async def brain_restore_backup(backup_id: str):
    """Restore from a backup."""
    return await agents["brain"].restore_backup(backup_id)


@router.delete("/backup/{backup_id}")
async def brain_delete_backup(backup_id: str):
    """Delete a backup."""
    return await agents["brain"].delete_backup(backup_id)


# ── EXPORT & IMPORT ────────────────────────────────────

@router.get("/export")
async def brain_export_memory(
    format: str = "json", include_private: bool = False, include_sensitive: bool = False
):
    """Export memory in various formats (json, markdown, obsidian)."""
    return await agents["brain"].export_memory(format, include_private, include_sensitive)


@router.post("/import")
async def brain_import_memory(request: Request, merge: bool = True):
    """Import memory from exported data."""
    data = await request.json()
    return await agents["brain"].import_memory(data, merge)


# ── ENCRYPTION & PRIVACY ───────────────────────────────

@router.post("/encrypt/key")
async def brain_set_encryption_key(key: str):
    """Set encryption key for sensitive memories."""
    return agents["brain"].set_encryption_key(key)


@router.delete("/encrypt/key")
async def brain_clear_encryption_key():
    """Clear encryption key."""
    return agents["brain"].clear_encryption_key()


@router.post("/encrypt/{node_id}")
async def brain_encrypt_node(node_id: str, privacy: str = "private"):
    """Encrypt and protect a node."""
    from agents.second_brain_agent import PrivacyLevel
    return await agents["brain"].encrypt_node(node_id, PrivacyLevel(privacy))


@router.post("/decrypt/{node_id}")
async def brain_decrypt_node(node_id: str):
    """Decrypt a protected node."""
    return await agents["brain"].decrypt_node(node_id)


@router.put("/privacy/{node_id}")
async def brain_set_node_privacy(node_id: str, privacy: str):
    """Set privacy level for a node."""
    from agents.second_brain_agent import PrivacyLevel
    return agents["brain"].set_node_privacy(node_id, PrivacyLevel(privacy))


@router.get("/privacy/{node_id}")
async def brain_get_node_privacy(node_id: str):
    """Get privacy level for a node."""
    level = agents["brain"].get_node_privacy(node_id)
    return {"node_id": node_id, "privacy": level.value}


# ── VISUALIZATION ────────────────────────────────────────

@router.get("/graph")
async def brain_get_graph(max_nodes: int = 200):
    """Get graph data for visualization."""
    return agents["brain"].get_graph_data(max_nodes)


@router.get("/timeline")
async def brain_get_timeline(days: int = 30):
    """Get timeline data for memory visualization."""
    return agents["brain"].get_timeline_data(days)


@router.get("/entity-map")
async def brain_get_entity_map():
    """Get entity relationship map."""
    return agents["brain"].get_entity_map()


# ── SEMANTIC SEARCH ──────────────────────────────────────

@router.get("/semantic")
async def brain_semantic_search(query: str, limit: int = 10):
    """Pure semantic search using vector embeddings."""
    return {"results": await agents["brain"].semantic_search(query, limit)}


# ── PATTERNS & PROACTIVE ────────────────────────────────

@router.get("/proactive")
async def brain_get_proactive():
    """Get memories surfaced proactively."""
    return {"memories": agents["brain"].get_proactive_memories()}


@router.get("/patterns")
async def brain_get_patterns(pattern_type: str = None):
    """Get detected patterns (temporal, sequential, topical)."""
    return {"patterns": agents["brain"].get_patterns(pattern_type)}


# ── SYNC ────────────────────────────────────────────────

@router.get("/sync")
async def brain_get_sync_status():
    """Get sync status of all nodes."""
    return agents["brain"].get_sync_status()


@router.post("/sync")
async def brain_mark_synced(node_ids: list[str]):
    """Mark nodes as synced."""
    return agents["brain"].mark_synced(node_ids)


# ── UNIFIED RAG ────────────────────────────────────────

@router.post("/rag", tags=["🧠 Unified Search"])
async def unified_rag_query(req: UnifiedRAGRequest, request: Request):
    """
    Unified RAG search combining documents AND memory.
    Searches both the document knowledge base and personal memory,
    with optional LLM synthesis.
    """
    import time as time_module

    t_start = time_module.perf_counter()
    context_parts: list[dict] = []
    memory_sources: list[dict] = []
    doc_sources: list[dict] = []

    if req.use_memory and "brain" in agents:
        try:
            memory_results = await agents["brain"].recall(query=req.query, limit=req.memory_top_k)
            for r in memory_results.get("results", []):
                node_id = r.get("node_id") or r.get("id", "")
                memory_type = r.get("memory_type", "general")
                content = r.get("content", "") or str(r.get("value", ""))
                if content:
                    context_parts.append({
                        "source": "memory", "type": memory_type, "id": node_id,
                        "content": content[:500],
                        "relevance": r.get("relevance", r.get("score", 0)),
                    })
                    memory_sources.append({
                        "type": memory_type, "content_preview": content[:150],
                        "relevance": r.get("relevance", r.get("score", 0)),
                    })
        except Exception as e:
            import logging
            logging.getLogger("rasospeak.brain").warning(f"Memory retrieval failed: {e}")

    if req.use_docs and "rag" in agents:
        try:
            doc_results = await agents["rag"].retrieve(req.query, top_k=req.doc_top_k)
            for r in doc_results:
                context_parts.append({
                    "source": "document",
                    "type": r.get("metadata", {}).get("title", "Document"),
                    "id": r.get("id", ""),
                    "content": r.get("content", "")[:500],
                    "relevance": r.get("score", 0),
                })
                doc_sources.append({
                    "title": r.get("metadata", {}).get("title", "Document"),
                    "url": r.get("metadata", {}).get("url"),
                    "score": r.get("score", 0),
                })
        except Exception:
            pass

    if not context_parts:
        return {
            "answer": "No relevant results found. Try adding documents or memories first.",
            "memory_results": [], "doc_results": [],
            "context_used": False,
            "processing_ms": int((time_module.perf_counter() - t_start) * 1000),
        }

    context_parts.sort(key=lambda x: x.get("relevance", 0), reverse=True)
    memory_context = "\n".join(f"[Memory - {c['type']}]: {c['content']}" for c in context_parts if c["source"] == "memory")
    doc_context = "\n".join(f"[Document - {c['type']}]: {c['content']}" for c in context_parts if c["source"] == "document")

    answer = None
    if req.use_llm and "qa" in agents:
        try:
            result = await agents["qa"].ask(
                question=req.query,
                context=f"Personal Memory:\n{memory_context or '(no relevant memory found)'}\n\nDocument Knowledge:\n{doc_context or '(no relevant documents found)'}"
            )
            answer = result.get("answer") if isinstance(result, dict) else str(result)
            if result.get("error"):
                answer = None
        except Exception:
            answer = None

    elapsed_ms = int((time_module.perf_counter() - t_start) * 1000)
    return {
        "answer": answer or f"Found {len(memory_sources)} memory results and {len(doc_sources)} document results. See 'memory_results' and 'doc_results' for details.",
        "memory_results": memory_sources[:req.memory_top_k],
        "doc_results": doc_sources[:req.doc_top_k],
        "total_sources": len(context_parts),
        "context_used": True,
        "processing_ms": elapsed_ms,
    }


@router.get("/search", tags=["🧠 Unified Search"])
async def unified_search(query: str, limit: int = 10):
    """Search both memory and documents in one call."""
    results: dict[str, list] = {"memory": [], "documents": []}

    if "brain" in agents:
        try:
            mem = await agents["brain"].recall(query=query, limit=limit)
            results["memory"] = [
                {"id": r.get("node_id", r.get("id", "")),
                 "type": r.get("memory_type", "general"),
                 "content": (r.get("content", "") or str(r.get("value", "")))[:300],
                 "relevance": r.get("relevance", r.get("score", 0))}
                for r in mem.get("results", []) if r.get("content") or r.get("value")
            ]
        except Exception:
            pass

    if "rag" in agents:
        try:
            docs = await agents["rag"].retrieve(query=query, top_k=limit)
            results["documents"] = [
                {"id": r.get("id", ""),
                 "title": r.get("metadata", {}).get("title", "Document"),
                 "url": r.get("metadata", {}).get("url"),
                 "content": r.get("content", "")[:300],
                 "score": r.get("score", 0)}
                for r in docs
            ]
        except Exception:
            pass

    return results
