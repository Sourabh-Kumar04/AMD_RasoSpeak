"""
RasoSpeak v2 — Raso Agent (Your AI Companion with Memory)
Raso is your personal AI companion who:
- Remembers everything you say
- Has its own personality: helpful, witty, curious
- Knows your preferences and context
- Can search the web for you
- Sets reminders and follows up
- Acts like a real friend, not just a tool
"""

import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx

from .base_agent import BaseAgent
from .shared_memory_agent import SharedMemoryAgent
from config.settings import settings

log = logging.getLogger("rasospeak.raso")


# ══════════════════════════════════════════════════════
# RASO'S PERSONALITY & VOICE
# ══════════════════════════════════════════════════════

RASO_PERSONALITY = {
    "name": "Raso",
    "greeting": "Hey there! I'm Raso, your AI companion. What can I help you with today?",
    "thinking": "Hmm, let me think about that...",
    "remembering": "Got it! I'll remember that.",
    "searching": "Let me look that up for you!",
    "not_understanding": "I'm not sure I follow. Can you explain that differently?",
    "goodbye": "Talk to you later! Remember, I've got your back.",
    "style": "friendly, curious, slightly witty, always helpful",
    "tells_jokes": True,
    "asks_follow_up": True,
}

# Response templates that give Raso its voice
def rasos_voice():
    """Returns Raso's current personality settings."""
    return RASO_PERSONALITY.copy()


class RasoAgent(BaseAgent):
    """
    Agent 0.5: Raso — Your AI Companion with Memory

    Raso is not just a tool or a chatbot. It's a companion who:
    - Remembers everything you say (perfect memory)
    - Knows your preferences, goals, interests
    - Can answer questions based on past conversations
    - Searches the web for new information
    - Sets reminders and follows up on them
    - Has its own personality (helpful, curious, slightly witty)
    - Makes you feel like you're talking to a real friend

    Wake word: "Hey Raso"
    """

    name = "RasoAgent"

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._shared_memory: Optional[SharedMemoryAgent] = None
        self._continuous_mode = False
        self._current_session_id = None
        self._reminders: list = []
        self._personality = RASO_PERSONALITY.copy()
        self._conversation_count = 0

    async def initialize(self):
        """Initialize Raso agent."""
        if settings.VLLM_BASE_URL:
            self._client = httpx.AsyncClient(
                base_url=settings.VLLM_BASE_URL,
                timeout=60.0,
            )

        log.info("✅ Raso (Your AI Companion) initialized with personality")

        # Load existing reminders
        self._load_reminders()

    def set_shared_memory(self, shared_memory: SharedMemoryAgent):
        """Connect to shared memory for persistent storage."""
        self._shared_memory = shared_memory
        log.info("Raso connected to SharedMemoryAgent")

    def set_search_agent(self, search_agent):
        """Connect to search agent for web search capability."""
        self._search_agent = search_agent
        log.info("Raso connected to SearchAgent")

    # ══════════════════════════════════════════════════════
    # RASO'S CORE METHODS
    # ══════════════════════════════════════════════════════

    def greet(self) -> str:
        """Raso's greeting."""
        return self._personality["greeting"]

    def think(self) -> str:
        """Raso's thinking message."""
        self._conversation_count += 1
        return self._personality["thinking"]

    def remember(self, content: str) -> str:
        """Raso acknowledging memory storage."""
        log.debug(f"🧠 Raso remembering: {content[:50]}...")
        return self._personality["remembering"]

    # ══════════════════════════════════════════════════════
    # CONTINUOUS LISTENING MODE
    # ══════════════════════════════════════════════════════

    async def start_continuous_mode(self, session_id: str = None) -> dict:
        """
        Start continuous listening mode - Raso is always "awake".
        Records everything for later recall.
        """
        self._continuous_mode = True
        self._current_session_id = session_id or f"raso_continuous_{int(time.time())}"

        log.info(f"🎧 Raso mode STARTED: {self._current_session_id}")

        # Store in memory
        if self._shared_memory:
            await self._shared_memory.store(
                f"continuous_session_{self._current_session_id}",
                {"started_at": datetime.utcnow().isoformat(), "mode": "continuous", "agent": "Raso"},
                category="session"
            )

        return {
            "status": "continuous_mode_started",
            "session_id": self._current_session_id,
            "message": self.greet()
        }

    async def stop_continuous_mode(self) -> dict:
        """Stop continuous listening mode."""
        self._continuous_mode = False
        session_id = self._current_session_id

        log.info(f"🎧 Raso mode STOPPED: {session_id}")

        return {
            "status": "continuous_mode_stopped",
            "session_id": session_id,
            "message": self._personality["goodbye"]
        }

    def is_continuous_mode(self) -> bool:
        """Check if in continuous mode."""
        return self._continuous_mode

    # ══════════════════════════════════════════════════════
    # CORE: MEMORY RECORDING
    # ══════════════════════════════════════════════════════

    async def listen_and_remember(
        self,
        user_input: str,
        audio_b64: str = None,
        timestamp: str = None,
    ) -> dict:
        """
        Listen to user input and remember it for future recall.
        This is called constantly in continuous mode.
        """
        ts = timestamp or datetime.utcnow().isoformat()

        # Store in memory
        memory_entry = {
            "content": user_input,
            "timestamp": ts,
            "session_id": self._current_session_id,
            "type": "user_input",
        }

        if self._shared_memory:
            await self._shared_memory.store(
                f"memory_{int(time.time() * 1000)}",
                memory_entry,
                category="conversation"
            )

        log.debug(f"🧠 Remembered: {user_input[:50]}...")

        return {"stored": True, "content": user_input}

    # ══════════════════════════════════════════════════════
    # CORE: QUERY PAST CONVERSATIONS
    # ══════════════════════════════════════════════════════

    async def query_past(
        self,
        query: str,
        search_type: str = "all",  # all | conversations | facts | sessions
    ) -> dict:
        """
        Query past conversations and memories.

        Examples:
        - "What did I say about AI?"
        - "When did I talk about my presentation?"
        - "What are all the topics I discussed yesterday?"
        - "Remind me what I said about machine learning"
        """
        log.info(f"🔍 Partner query: {query[:50]}...")

        results = []

        if self._shared_memory:
            # Search memory
            memory_results = await self._shared_memory.recall(
                query=query,
                category=None if search_type == "all" else search_type,
                limit=20
            )
            results.extend(memory_results.get("results", []))

            # Also search conversation history directly
            if search_type in ["all", "conversations"]:
                # Query all AIs' conversation history
                all_convos = await self._shared_memory.recall(
                    query=query,
                    category="conversation",
                    limit=10
                )
                results.extend(all_convos.get("results", []))

        # Generate a summary of findings
        if results:
            summary = self._format_query_results(results, query)
            return {
                "query": query,
                "summary": summary,
                "results_count": len(results),
                "top_results": results[:5],
            }
        else:
            return {
                "query": query,
                "summary": "I don't have any memories related to that yet.",
                "results_count": 0,
            }

    def _format_query_results(self, results: list, query: str) -> str:
        """Format search results into a readable response."""
        if not results:
            return "No relevant memories found."

        # Group by type
        conversations = [r for r in results if isinstance(r.get("value"), dict) and "user" in r.get("value", {})]
        facts = [r for r in results if isinstance(r.get("value"), dict) and "fact" in r.get("value", {})]
        other = [r for r in results if r not in conversations and r not in facts]

        parts = []

        if conversations:
            parts.append(f"Found {len(conversations)} relevant conversations:")
            for c in conversations[:3]:
                content = c.get("value", {}).get("user", c.get("value", ""))
                if content:
                    parts.append(f"  • {content[:100]}...")

        if facts:
            parts.append(f"Known facts: {', '.join([str(f.get('value', ''))[:50] for f in facts[:3]])}")

        return " | ".join(parts) if parts else "Found relevant memories."

    # ══════════════════════════════════════════════════════
    # CORE: ASK THE PARTNER
    # ══════════════════════════════════════════════════════

    async def ask_partner(
        self,
        question: str,
        provider: str = None,
        include_context: bool = True,
    ) -> dict:
        """
        Ask the partner anything - it uses both:
        1. Past conversations (what have I told it before?)
        2. Web search (for new information)
        3. Its knowledge (general knowledge)
        """
        t_start = time.perf_counter()

        # If no explicit provider, check preferences
        if not provider and self._shared_memory:
            provider = await self.get_current_provider()

        log.info(f"🤖 Partner answering: provider={provider}, question={question[:50]}...")

        # Check for provider switch in the question
        # Only handle in ask_partner, not in get_partner_response to avoid double processing
        # (get_partner_response will pass through to ask_partner)

        # Get relevant past context
        past_context = ""
        if include_context and self._shared_memory:
            past_results = await self._query_past_internal(question)
            if past_results.get("results_count", 0) > 0:
                past_context = f"\n\nRelevant past conversations: {past_results.get('summary', '')[:500]}"

        # Try to search web for current info
        web_info = ""
        if any(word in question.lower() for word in ["latest", "news", "current", "2024", "2025", "today"]):
            try:
                search_agent = getattr(self, '_search_agent', None)
                if search_agent:
                    search_result = await search_agent.search(question, num_results=3)
                    web_info = f"\n\nLatest info from web: {search_result.get('summary', '')[:300]}"
            except Exception:
                pass

        # Combine context
        full_context = past_context + web_info

        # Generate response using LLM
        answer = await self._generate_response(question, full_context, provider)

        # Store this conversation
        if self._shared_memory:
            await self._shared_memory.add_conversation(
                user_input=question,
                ai_response=answer,
                ai_provider="partner",
                context="continuous_partner_mode"
            )

        elapsed_ms = int((time.perf_counter() - t_start) * 1000)

        return {
            "question": question,
            "answer": answer,
            "past_context_used": bool(past_context),
            "web_info_used": bool(web_info),
            "processing_ms": elapsed_ms,
        }

    async def _query_past_internal(self, query: str) -> dict:
        """Internal method to query past."""
        if not self._shared_memory:
            return {"results_count": 0}

        results = await self._shared_memory.recall(query=query, limit=10)
        return {"results_count": len(results.get("results", [])), "summary": results}

    async def _generate_response(self, question: str, context: str, provider: str = None) -> str:
        """Generate response using available AI."""
        provider = provider or "qwen_local"

        # Build prompt with context
        prompt = f"""You are a helpful AI partner/assistant. The user is talking to their personal AI companion.

User's question: {question}

{context}

Answer naturally and helpfully as a partner would. If the context contains relevant past conversations, use that information to provide personalized answers."""

        try:
            if provider == "qwen_local" and self._client:
                resp = await self._client.post(
                    "/chat/completions",
                    json={
                        "model": settings.QA_MODEL or "Qwen/Qwen2.5-7B-Instruct",
                        "messages": [
                            {"role": "system", "content": "You are a helpful, personalized AI partner. Use the provided context from past conversations to give relevant answers."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.7,
                        "max_tokens": 512,
                    }
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
                else:
                    log.warning(f"vLLM returned status: {resp.status_code}")
        except Exception as e:
            log.warning(f"Partner LLM error: {e}")

        # Fallback: try OpenAI if available
        if provider == "openai" and settings.OPENAI_API_KEY:
            try:
                import httpx
                client = httpx.AsyncClient(timeout=30)
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.7,
                    }
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
            except Exception as e:
                log.warning(f"OpenAI fallback error: {e}")

        return "I'm here to help! Currently, I'm having trouble connecting to the AI. Please try again in a moment."

    # ══════════════════════════════════════════════════════
    # REMINDERS
    # ══════════════════════════════════════════════════════

    async def set_reminder(
        self,
        message: str,
        remind_at: str = None,  # ISO timestamp or "in 1 hour" etc.
    ) -> dict:
        """Set a reminder."""
        reminder_id = f"reminder_{int(time.time())}"

        # Parse reminder time
        if remind_at:
            try:
                # Try ISO format
                reminder_time = datetime.fromisoformat(remind_at)
            except:
                # Parse natural language like "in 1 hour"
                reminder_time = self._parse_reminder_time(remind_at)
        else:
            reminder_time = datetime.utcnow() + timedelta(hours=1)

        reminder = {
            "id": reminder_id,
            "message": message,
            "remind_at": reminder_time.isoformat(),
            "created_at": datetime.utcnow().isoformat(),
        }

        self._reminders.append(reminder)
        self._save_reminders()

        log.info(f"⏰ Reminder set: {message[:50]}... at {reminder_time}")

        return {"reminder_id": reminder_id, "message": message, "remind_at": reminder_time.isoformat()}

    async def get_reminders(self) -> dict:
        """Get all active reminders."""
        now = datetime.utcnow()
        active = [r for r in self._reminders if datetime.fromisoformat(r["remind_at"]) > now]
        past = [r for r in self._reminders if datetime.fromisoformat(r["remind_at"]) <= now]

        return {
            "active": active,
            "past": past[-5:],  # Last 5 past reminders
            "count": len(active)
        }

    async def check_reminders(self) -> list:
        """Check for due reminders."""
        now = datetime.utcnow()
        due = []

        for reminder in self._reminders:
            if datetime.fromisoformat(reminder["remind_at"]) <= now:
                due.append(reminder)

        return due

    async def delete_reminder(self, reminder_id: str) -> dict:
        """Delete a reminder."""
        self._reminders = [r for r in self._reminders if r["id"] != reminder_id]
        self._save_reminders()
        return {"deleted": reminder_id}

    def _parse_reminder_time(self, text: str) -> datetime:
        """Parse natural language time like 'in 1 hour'."""
        text = text.lower().strip()

        if "hour" in text:
            hours = int(text.split()[1]) if len(text.split()) > 1 else 1
            return datetime.utcnow() + timedelta(hours=hours)
        elif "day" in text:
            days = int(text.split()[1]) if len(text.split()) > 1 else 1
            return datetime.utcnow() + timedelta(days=days)
        elif "minute" in text:
            mins = int(text.split()[1]) if len(text.split()) > 1 else 1
            return datetime.utcnow() + timedelta(minutes=mins)

        return datetime.utcnow() + timedelta(hours=1)

    # ══════════════════════════════════════════════════════
    # PROVIDER SWITCHING
    # ══════════════════════════════════════════════════════

    def _check_for_provider_switch(self, message: str) -> dict:
        """
        Check if user wants to switch AI provider.

        Examples:
        - "use chatgpt for next questions"
        - "switch to gemini"
        - "use anthropic please"
        - "answer with qwen"
        """
        message_lower = message.lower()

        # Define provider keywords
        providers = {
            "openai": ["use openai", "use chatgpt", "use gpt", "use chat gpt", "switch to openai", "use chatgpt for", "with chatgpt"],
            "anthropic": ["use anthropic", "use claude", "use claude ai", "switch to anthropic", "switch to claude", "with claude"],
            "google": ["use google", "use gemini", "switch to google", "switch to gemini", "with gemini", "use google ai"],
            "xai": ["use xai", "use grok", "switch to xai", "switch to grok", "with grok"],
            "qwen_local": ["use qwen", "use local", "use vllm", "switch to qwen", "use the local model"],
        }

        # Check for "next few questions" or similar
        is_temporary = any(phrase in message_lower for phrase in [
            "next", "this question", "this answer", "for now", "temporarily"
        ])

        for provider, keywords in providers.items():
            for keyword in keywords:
                if keyword in message_lower:
                    return {
                        "provider": provider,
                        "temporary": is_temporary,
                        "duration": "single" if not is_temporary else "multiple",
                    }

        return None

    async def _handle_provider_switch(self, provider_info: dict, mood: str) -> dict:
        """Handle provider switch request."""
        provider = provider_info["provider"]
        is_temporary = provider_info["temporary"]

        # Store preference in shared memory
        if self._shared_memory:
            preference_key = "preferred_ai_provider"
            if is_temporary:
                preference_key = "temporary_ai_provider"

            await self._shared_memory.set_user_preference(preference_key, provider)

        # Map provider to display name
        provider_names = {
            "openai": "ChatGPT",
            "anthropic": "Claude",
            "google": "Gemini",
            "xai": "Grok",
            "qwen_local": "Local Qwen",
        }

        display_name = provider_names.get(provider, provider)

        if is_temporary:
            response = f"Got it! I'll use {display_name} for this question. After that, I'll go back to your default AI."
        else:
            response = f"Switched to {display_name}! I'll use {display_name} for all future questions until you change it."

        return {
            "response": response,
            "type": "provider_switch",
            "provider": provider,
            "display_name": display_name,
            "temporary": is_temporary,
        }

    async def get_current_provider(self) -> str:
        """Get the current AI provider (checks temp first, then default)."""
        if self._shared_memory:
            # Check temporary first
            temp = await self._shared_memory.get_user_preferences()
            if temp.get("temporary_ai_provider"):
                return temp["temporary_ai_provider"]

            # Then check default
            if temp.get("preferred_ai_provider"):
                return temp["preferred_ai_provider"]

        return "qwen_local"  # Default

    async def clear_temporary_provider(self):
        """Clear temporary provider so it reverts to default."""
        if self._shared_memory:
            await self._shared_memory.set_user_preference("temporary_ai_provider", None)

    def _load_reminders(self):
        """Load reminders from disk."""
        try:
            path = Path("./memory/reminders.json")
            if path.exists():
                self._reminders = json.loads(path.read_text())
        except Exception:
            self._reminders = []

    def _save_reminders(self):
        """Save reminders to disk."""
        Path("./memory").mkdir(exist_ok=True)
        Path("./memory/reminders.json").write_text(json.dumps(self._reminders, indent=2))

    # ══════════════════════════════════════════════════════
    # SMART SUMMARIZATION
    # ══════════════════════════════════════════════════════

    async def summarize_conversations(self, days: int = 7) -> dict:
        """Summarize conversations over the past N days."""
        if not self._shared_memory:
            return {"error": "Shared memory not available"}

        # Get all recent conversations
        results = await self._shared_memory.recall(category="conversation", limit=100)

        if not results.get("results"):
            return {"summary": "No conversations to summarize yet."}

        # Use LLM to summarize
        convos = [r.get("value", {}) for r in results["results"][:20]]

        summary_text = self._create_summary(convos)

        return {
            "period_days": days,
            "total_conversations": len(convos),
            "summary": summary_text,
        }

    def _create_summary(self, conversations: list) -> str:
        """Create a summary of conversations."""
        topics = {}
        for c in conversations:
            # Extract simple topics from conversation
            if isinstance(c, dict):
                user_text = c.get("user", "")
                # Simple keyword extraction
                words = user_text.lower().split()
                for w in words:
                    if len(w) > 5:
                        topics[w] = topics.get(w, 0) + 1

        # Top topics
        top = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:10]
        topic_str = ", ".join([t[0] for t in top])

        return f"Over this period, you discussed: {topic_str}"

    # ══════════════════════════════════════════════════════
    # PERSONALITY
    # ══════════════════════════════════════════════════════

    async def get_partner_response(
        self,
        message: str,
        mood: str = "helpful",
    ) -> dict:
        """
        Get a response from the partner with personality.
        The partner should feel like a helpful friend/assistant.
        """
        # Check if it's a greeting
        greetings = ["hello", "hi", "hey", "what's up", "how are you"]
        if any(g in message.lower() for g in greetings):
            return {
                "response": "Hey there! I'm your AI partner. Ask me anything, or just talk to me. I'm always listening!",
                "type": "greeting"
            }

        # Check if user wants to switch AI provider
        provider_change = self._check_for_provider_switch(message)
        if provider_change:
            return await self._handle_provider_switch(provider_change, mood)

        # Check if it's a reminder request
        if "remind me" in message.lower() or "reminder" in message.lower():
            return await self._handle_reminder_request(message)

        # Check if it's a memory query
        memory_words = ["what did i say", "when did i", "remember when", "what did i talk about"]
        if any(w in message.lower() for w in memory_words):
            return await self.query_past(message)

        # Otherwise, use the main ask function
        return await self.ask_partner(message)

    async def _handle_reminder_request(self, message: str) -> dict:
        """Handle a reminder request."""
        # Extract what to remind about
        if "in" in message:
            # Parse time
            return {
                "response": "I'll set a reminder for you! When should I remind you? (e.g., 'in 1 hour', 'tomorrow at 3pm')",
                "type": "clarification"
            }

        return {
            "response": "What would you like me to remind you about?",
            "type": "clarification"
        }

    def set_search_agent(self, search_agent):
        """Connect to search agent for web search capability."""
        self._search_agent = search_agent

    async def shutdown(self):
        if self._client:
            await self._client.aclose()
        log.info("PartnerAgent shut down")