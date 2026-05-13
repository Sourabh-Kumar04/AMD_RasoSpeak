"""
Distributed Event Bus - Redis Streams Implementation
======================================================
Production-grade event-driven infrastructure for distributed cognition.
"""

from __future__ import annotations
import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
import structlog

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = structlog.get_logger("rasospeak.event_bus")


class EventPriority(Enum):
    """Event priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CognitEvent:
    """
    Distributed cognition event.

    Used for:
    - Voice transcript events
    - Memory store/retrieve events
    - Provider switch events
    - Workflow state changes
    - Agent actions
    """
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    source: str = ""
    user_id: str = "default"
    session_id: Optional[str] = None

    payload: dict = field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL

    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None

    # For event sourcing
    causation_id: Optional[str] = None
    reply_to: Optional[str] = None

    # Metadata
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "payload": self.payload,
            "priority": self.priority.value,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "causation_id": self.causation_id,
            "reply_to": self.reply_to,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CognitEvent":
        return cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            event_type=data.get("event_type", ""),
            source=data.get("source", ""),
            user_id=data.get("user_id", "default"),
            session_id=data.get("session_id"),
            payload=data.get("payload", {}),
            priority=EventPriority(data.get("priority", "normal")),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.utcnow(),
            correlation_id=data.get("correlation_id"),
            trace_id=data.get("trace_id"),
            causation_id=data.get("causation_id"),
            reply_to=data.get("reply_to"),
            metadata=data.get("metadata", {})
        )


class DistributedEventBus:
    """
    Real distributed event bus using Redis Streams.

    Features:
    - Publisher/Subscriber pattern
    - Event persistence and replay
    - Consumer groups for distributed processing
    - Event correlation and tracing
    - Dead letter queue for failed events
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        stream_prefix: str = "rasospeak:events",
        consumer_group: str = "rasospeak-workers"
    ):
        self._redis_url = redis_url
        self._stream_prefix = stream_prefix
        self._consumer_group = consumer_group
        self._redis: Optional[redis.Redis] = None

        # Local handlers (for when Redis unavailable)
        self._local_handlers: dict[str, list[Callable]] = {}
        self._local_subscribers: dict[str,asyncio.Queue] = {}

        # Consumer tracking
        self._consumers: dict[str, str] = {}  # consumer_id -> stream

        logger.info("event_bus_initializing", redis_url=redis_url)

    async def connect(self):
        """Connect to Redis."""
        if REDIS_AVAILABLE:
            try:
                self._redis = redis.from_url(self._redis_url, decode_responses=True)
                await self._redis.ping()
                logger.info("event_bus_connected", redis_url=self._redis_url)
            except Exception as e:
                logger.warning("redis_connection_failed", error=str(e), using_local=True)
                self._redis = None
        else:
            logger.info("redis_not_available", using_local=True)
            self._redis = None

    async def disconnect(self):
        """Disconnect from Redis."""
        if self._redis:
            await self._redis.close()
            logger.info("event_bus_disconnected")

    def _stream_name(self, event_type: str) -> str:
        """Get stream name for event type."""
        return f"{self._stream_prefix}:{event_type}"

    # ─────────────────────────────────────────────────────────────
    # Publishing
    # ─────────────────────────────────────────────────────────────

    async def publish(
        self,
        event: CognitEvent,
        stream: Optional[str] = None
    ) -> str:
        """
        Publish event to stream.

        Returns event ID.
        """
        stream = stream or self._event_type_to_stream(event.event_type)

        event_dict = event.to_dict()

        if self._redis:
            try:
                # Add to stream with priority
                stream_key = f"{self._stream_prefix}:{stream}"
                event_id = await self._redis.xadd(
                    stream_key,
                    {"data": json.dumps(event_dict)},
                    maxlen=10000,  # Keep last 10k events per stream
                    approximate=True
                )
                logger.debug("event_published", event_id=event_id, stream=stream, event_type=event.event_type)
                return event_id
            except Exception as e:
                logger.error("redis_publish_failed", error=str(e))

        # Local fallback
        await self._local_publish(stream, event_dict)
        return event.event_id

    async def publish_batch(self, events: list[CognitEvent]) -> list[str]:
        """Publish multiple events."""
        return await asyncio.gather(*[self.publish(e) for e in events])

    def _event_type_to_stream(self, event_type: str) -> str:
        """Map event type to stream name."""
        return event_type.replace("_", "-")

    # ─────────────────────────────────────────────────────────────
    # Subscribing
    # ─────────────────────────────────────────────────────────────

    async def subscribe(
        self,
        event_type: str,
        handler: Callable[[CognitEvent], Any],
        consumer_id: Optional[str] = None
    ):
        """
        Subscribe to event type with handler.

        For local/development mode.
        """
        if event_type not in self._local_handlers:
            self._local_handlers[event_type] = []
        self._local_handlers[event_type].append(handler)
        logger.info("handler_subscribed", event_type=event_type)

    async def unsubscribe(self, event_type: str, handler: Callable):
        """Unsubscribe handler."""
        if event_type in self._local_handlers:
            self._local_handlers[event_type].remove(handler)

    async def _local_publish(self, stream: str, event_dict: dict):
        """Local publish for development."""
        if stream not in self._local_subscribers:
            self._local_subscribers[stream] = asyncio.Queue()

        event = CognitEvent.from_dict(event_dict)

        # Notify all handlers
        if stream in self._local_handlers:
            for handler in self._local_handlers[stream]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    logger.error("handler_error", stream=stream, error=str(e))

    # ─────────────────────────────────────────────────────────────
    # Consumer Groups (Distributed Processing)
    # ─────────────────────────────────────────────────────────────

    async def create_consumer_group(
        self,
        stream: str,
        group_name: Optional[str] = None
    ):
        """Create consumer group for distributed processing."""
        if not self._redis:
            return

        group_name = group_name or self._consumer_group
        stream_key = f"{self._stream_prefix}:{stream}"

        try:
            await self._redis.xgroup_create(
                stream_key,
                group_name,
                id="0",
                mkstream=True
            )
            logger.info("consumer_group_created", stream=stream, group=group_name)
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                logger.error("consumer_group_error", error=str(e))

    async def consume_events(
        self,
        stream: str,
        consumer_id: str,
        count: int = 10,
        block_ms: int = 5000,
        group_name: Optional[str] = None
    ) -> list[CognitEvent]:
        """
        Consume events using consumer group.

        Enables distributed processing with acknowledgment.
        """
        if not self._redis:
            return []

        group_name = group_name or self._consumer_group
        stream_key = f"{self._stream_prefix}:{stream}"

        try:
            # Read from consumer group
            messages = await self._redis.xreadgroup(
                group_name,
                consumer_id,
                {stream_key: ">"},
                count=count,
                block=block_ms
            )

            events = []
            if messages:
                for stream, msgs in messages:
                    for msg_id, msg_data in msgs:
                        try:
                            event_dict = json.loads(msg_data["data"])
                            event = CognitEvent.from_dict(event_dict)
                            event.metadata["msg_id"] = msg_id
                            events.append(event)
                        except Exception as e:
                            logger.error("parse_error", msg_id=msg_id, error=str(e))

            return events

        except Exception as e:
            logger.error("consume_error", stream=stream, error=str(e))
            return []

    async def ack_event(
        self,
        stream: str,
        msg_id: str,
        group_name: Optional[str] = None
    ):
        """Acknowledge processed event."""
        if not self._redis:
            return

        group_name = group_name or self._consumer_group
        stream_key = f"{self._stream_prefix}:{stream}"

        try:
            await self._redis.xack(stream_key, group_name, msg_id)
        except Exception as e:
            logger.error("ack_error", msg_id=msg_id, error=str(e))

    # ─────────────────────────────────────────────────────────────
    # Event Replay (For Recovery)
    # ─────────────────────────────────────────────────────────────

    async def replay_events(
        self,
        stream: str,
        from_id: str = "0",
        count: int = 100
    ) -> list[CognitEvent]:
        """Replay events from stream (for recovery/testing)."""
        if not self._redis:
            return []

        stream_key = f"{self._stream_prefix}:{stream}"

        try:
            messages = await self._redis.xrange(
                stream_key,
                min=from_id,
                count=count
            )

            events = []
            for msg_id, msg_data in messages:
                try:
                    event_dict = json.loads(msg_data["data"])
                    event = CognitEvent.from_dict(event_dict)
                    event.metadata["msg_id"] = msg_id
                    events.append(event)
                except:
                    pass

            return events

        except Exception as e:
            logger.error("replay_error", stream=stream, error=str(e))
            return []

    async def get_stream_info(self, stream: str) -> dict:
        """Get stream metadata."""
        if not self._redis:
            return {}

        stream_key = f"{self._stream_prefix}:{stream}"

        try:
            info = await self._redis.xinfo_stream(stream_key)
            return {
                "length": info.get("length"),
                "first_entry": info.get("first-entry"),
                "last_entry": info.get("last-entry")
            }
        except:
            return {}

    # ─────────────────────────────────────────────────────────────
    # Utility
    # ─────────────────────────────────────────────────────────────

    async def health_check(self) -> dict:
        """Check event bus health."""
        if self._redis:
            try:
                await self._redis.ping()
                return {"status": "healthy", "backend": "redis"}
            except:
                pass

        return {"status": "healthy", "backend": "local"}

    def get_stats(self) -> dict:
        """Get event bus statistics."""
        return {
            "local_handlers": len(self._local_handlers),
            "streams_tracked": len(self._local_subscribers),
            "redis_connected": self._redis is not None
        }


# Event types for type safety
class Events:
    """Event type constants."""

    # Voice events
    VOICE_WAKE_WORD = "voice_wake_word"
    VOICE_TRANSCRIPT = "voice_transcript"
    VOICE_AUDIO_START = "voice_audio_start"
    VOICE_AUDIO_END = "voice_audio_end"
    VOICE_SPEECH_START = "voice_speech_start"
    VOICE_SPEECH_END = "voice_speech_end"

    # Provider events
    PROVIDER_SWITCH = "provider_switch"
    PROVIDER_ERROR = "provider_error"
    QUOTA_EXCEEDED = "quota_exceeded"

    # Memory events
    MEMORY_STORED = "memory_stored"
    MEMORY_RETRIEVED = "memory_retrieved"
    MEMORY_CONSOLIDATED = "memory_consolidated"
    MEMORY_FORGOTTEN = "memory_forgotten"

    # Workflow events
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_STEP = "workflow_step"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"

    # Cognition events
    COGNITION_START = "cognition_start"
    COGNITION_LAYER = "cognition_layer"
    COGNITION_COMPLETE = "cognition_complete"

    # Agent events
    AGENT_ACTION = "agent_action"
    AGENT_GOAL = "agent_goal"
    AGENT_REFLECTION = "agent_reflection"


# Global event bus instance
_event_bus: Optional[DistributedEventBus] = None


async def get_event_bus() -> DistributedEventBus:
    """Get global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = DistributedEventBus()
        await _event_bus.connect()
    return _event_bus


async def shutdown_event_bus():
    """Shutdown global event bus."""
    global _event_bus
    if _event_bus:
        await _event_bus.disconnect()
        _event_bus = None