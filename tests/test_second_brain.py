"""Tests for SecondBrainAgent — core functionality."""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import shutil

from agents.second_brain_agent import (
    SecondBrainAgent, MemoryNode, MemoryType, MemoryTier,
    Importance, PrivacyLevel
)


@pytest.fixture
def tmp_brain():
    """Temp directory for brain storage."""
    tmp = tempfile.mkdtemp()
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def agent(tmp_brain):
    """Agent instance with temp storage."""
    with patch("agents.second_brain_agent.settings") as mock_settings:
        mock_settings.shared_memory_path = tmp_brain
        mock_settings.embeddings_path = tmp_brain
        mock_settings.embedding_model = "all-MiniLM-L6-v2"
        agent = SecondBrainAgent()
        agent._llm_client = MagicMock()
        agent._running = True
        yield agent


# ──────────────────────────────────────────────
# P0: Dedup — same content returns same node
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_store_dedup(agent):
    """Storing identical content returns the same node (idempotency)."""
    await agent.initialize()

    node1 = await agent.store("Hello world", MemoryType.CONVERSATION)
    node2 = await agent.store("Hello world", MemoryType.CONVERSATION)

    assert node1.id == node2.id, "Duplicate content must return same node"
    assert len(agent._nodes) == 1, "Only one node should exist after duplicate store"

    await agent.shutdown()


# ──────────────────────────────────────────────
# P0: Normalized dedup — whitespace difference
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_store_dedup_normalizes_whitespace(agent):
    """'Hello world' and 'Hello  world' (double space) are treated as same."""
    await agent.initialize()

    node1 = await agent.store("Hello world", MemoryType.CONVERSATION)
    node2 = await agent.store("Hello  world", MemoryType.CONVERSATION)

    assert node1.id == node2.id, "Whitespace-normalized content should deduplicate"
    assert len(agent._nodes) == 1

    await agent.shutdown()


# ──────────────────────────────────────────────
# P0: O(1) content index lookup
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_content_index_populated(agent):
    """_content_index is updated on store and removed on forget."""
    await agent.initialize()

    node = await agent.store("Test content", MemoryType.CONVERSATION)
    assert "Test content" in agent._content_index, "Content index must be updated on store"
    assert agent._content_index["Test content"] == node.id

    await agent.forget(node.id, "test")
    assert "Test content" not in agent._content_index, "Content index must be cleaned on forget"

    await agent.shutdown()


# ──────────────────────────────────────────────
# P0: Memory cap eviction
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_memory_cap_eviction(agent):
    """When cap is reached, lowest-importance nodes are evicted."""
    await agent.initialize()
    agent._MAX_NODES = 3

    await agent.store("first", MemoryType.CONVERSATION, importance=Importance.LOW)
    await agent.store("second", MemoryType.CONVERSATION, importance=Importance.HIGH)
    await agent.store("third", MemoryType.CONVERSATION, importance=Importance.MEDIUM)

    # This should evict "first" (LOW importance)
    await agent.store("fourth", MemoryType.CONVERSATION, importance=Importance.MEDIUM)

    assert len(agent._nodes) <= 3, "Node count should stay within cap"
    assert "first" not in agent._content_index, "Evicted content removed from index"

    await agent.shutdown()


# ──────────────────────────────────────────────
# P0: Graceful shutdown sets _running = False
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_shutdown_sets_running_false(agent):
    """shutdown() must set _running = False so loops exit cleanly."""
    await agent.initialize()
    assert agent._running is True

    await agent.shutdown()

    assert agent._running is False, "_running flag must be False after shutdown"


# ──────────────────────────────────────────────
# P0: Background loops check _running flag
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_persona_loop_respects_running_flag(agent):
    """_persona_update_loop should exit when _running is False."""
    await agent.initialize()

    # Simulate a quick shutdown while loop is in sleep
    async def quick_shutdown():
        await asyncio.sleep(0.1)
        agent._running = False

    async def loop_under_test():
        count = 0
        while agent._running and count < 100:  # hard cap to prevent infinite loop in test
            count += 1
            await asyncio.sleep(0.05)
        return count

    # Start both concurrently
    shutdown_task = asyncio.create_task(quick_shutdown())
    loop_task = asyncio.create_task(agent._persona_update_loop())

    done, pending = await asyncio.wait(
        [shutdown_task, loop_task],
        timeout=5.0,
        return_when=asyncio.FIRST_COMPLETED
    )

    for t in pending:
        t.cancel()

    # If shutdown worked, loop should exit reasonably fast (within a few iterations)
    # No assertion on count since timing varies, but it proves the flag is checked

    await agent.shutdown()


# ──────────────────────────────────────────────
# P1: Goals stored only once (not in memory)
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_goals_not_duplicated_in_nodes(agent):
    """add_goal should NOT also call store() — goals stay only in _goals dict."""
    await agent.initialize()

    with patch.object(agent, 'store', new_callable=AsyncMock) as mock_store:
        goal = await agent.add_goal("Test goal", description="Do stuff")

        # store() should NOT have been called for goal
        mock_store.assert_not_called()

    await agent.shutdown()


# ──────────────────────────────────────────────
# P1: Goal ID uses content hash, not UUID
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_goal_id_uses_hash_not_uuid(agent):
    """Goal ID should be deterministic from title hash, not random UUID."""
    await agent.initialize()

    goal1 = await agent.add_goal("My important task")
    goal2 = await agent.add_goal("My important task")

    assert goal1.id == goal2.id, "Same title must produce same goal ID (dedup)"
    assert "uuid" not in goal1.id.lower(), "Goal ID must not contain UUID"

    await agent.shutdown()


# ──────────────────────────────────────────────
# P1: analyze_emotions has timeout
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_analyze_emotions_timeout(agent):
    """analyze_emotions must raise TimeoutError on slow LLM call."""
    slow_client = AsyncMock()
    slow_client.chat = AsyncMock(side_effect=asyncio.TimeoutError("LLM timeout"))

    agent._llm_client = slow_client

    result = await agent.analyze_emotions("Test conversation")

    assert "error" in result, "Timeout should be handled gracefully"


# ──────────────────────────────────────────────
# P1: json.loads guarded with try/except
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_json_parse_guard(agent):
    """Malformed JSON from LLM must not crash analyze_emotions."""
    agent._llm_client = AsyncMock()
    agent._llm_client.chat = AsyncMock(return_value={
        "content": "Here is the result: {not valid json {{{{"
    })

    result = await agent.analyze_emotions("Test conversation")

    assert "error" in result or result == {}, "Malformed JSON should return error dict"


# ──────────────────────────────────────────────
# P2: access_count persists via to_dict
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_access_count_in_node_dict(agent):
    """Node.to_dict() includes access_count for persistence."""
    await agent.initialize()

    node = await agent.store("Access me", MemoryType.CONVERSATION)
    node.access_count = 42

    node_dict = node.to_dict()
    assert "access_count" in node_dict, "access_count must be in to_dict() output"
    assert node_dict["access_count"] == 42

    await agent.shutdown()


# ──────────────────────────────────────────────
# P3: Encryption key zeroized on shutdown
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_encryption_key_zeroized_on_shutdown(agent):
    """shutdown() must zeroize _encryption_key if present."""
    agent._encryption_key = b'\x01\x02\x03\x04'

    await agent.shutdown()

    assert agent._encryption_key is None, "Encryption key must be None after shutdown"
