"""
RasoSpeak AI OS — World Model Service
====================================
Unified world model containing:
- User model (identity, preferences, personality, goals)
- Knowledge graph (concepts, facts, entities, relationships)
- Temporal model (timelines, events, projects)
- Relationship model (people, teams, organizations)
- Emotional/contextual state tracking

This is the SINGLE SOURCE OF TRUTH for all cognitive subsystems.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger("rasospeak.world_model")


# ──────────────────────────────────────────────────────────────────────────────
# World Model Types
# ──────────────────────────────────────────────────────────────────────────────

class EntityType(Enum):
    PERSON = "person"
    PROJECT = "project"
    GOAL = "goal"
    TASK = "task"
    DOCUMENT = "document"
    CONCEPT = "concept"
    EVENT = "event"
    PLACE = "place"
    ORGANIZATION = "organization"


class RelationshipType(Enum):
    KNOWS = "knows"
    COLLABORATES = "collaborates"
    REPORTS_TO = "reports_to"
    PART_OF = "part_of"
    WORKS_ON = "works_on"
    INTERESTS_IN = "interests_in"
    CONTRADICTS = "contradicts"
    SUPPORTS = "supports"
    RELATES_TO = "relates_to"


@dataclass
class Entity:
    """A node in the knowledge graph."""
    entity_id: str
    entity_type: EntityType
    name: str
    properties: dict[str, Any] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)
    confidence: float = 1.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Relationship:
    """An edge in the knowledge graph."""
    relationship_id: str
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Timeline:
    """Timeline of events."""
    timeline_id: str
    user_id: str
    name: str
    events: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class UserModel:
    """The evolving model of the user."""
    user_id: str
    name: str
    preferences: dict[str, Any] = field(default_factory=dict)
    personality_traits: dict[str, float] = field(default_factory=dict)
    communication_style: str = "neutral"
    coaching_adaptations: dict[str, Any] = field(default_factory=dict)
    current_mood: str = "neutral"
    stress_level: float = 0.5
    energy_level: float = 0.5


@dataclass
class Goal:
    """A user goal or objective."""
    goal_id: str
    user_id: str
    title: str
    description: str
    status: str  # active, achieved, abandoned, paused
    priority: int = 0
    deadline: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    progress: float = 0.0
    milestones: list[dict] = field(default_factory=list)


@dataclass
class Person:
    """Person with relationship tracking."""
    person_id: str
    user_id: str  # The user who knows this person
    name: str
    relationship_type: str  # friend, colleague, mentor, etc.
    how_met: Optional[str] = None
    first_met: Optional[datetime] = None
    last_contact: Optional[datetime] = None
    contact_frequency: float = 0.0
    topics_discussed: list[str] = field(default_factory=list)
    communication_style: str = "neutral"
    expertise_areas: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class Project:
    """A project tracked by the system."""
    project_id: str
    user_id: str
    name: str
    description: str
    status: str  # active, completed, on_hold
    start_date: Optional[datetime] = None
    deadline: Optional[datetime] = None
    goals: list[str] = field(default_factory=list)  # goal_ids
    tasks: list[dict] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)  # person_ids
    documents: list[str] = field(default_factory=list)


@dataclass
class Memory:
    """Unified memory entry."""
    memory_id: str
    memory_type: str  # episodic, semantic, procedural, working
    user_id: str
    content: Any
    embedding: Optional[list[float]] = None
    importance: float = 0.5
    confidence: float = 1.0
    source: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0
    tags: list[str] = field(default_factory=list)
    linked_memories: list[str] = field(default_factory=list)
    linked_entities: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Knowledge Graph
# ──────────────────────────────────────────────────────────────────────────────

class KnowledgeGraph:
    """Graph of concepts, facts, and relationships."""

    def __init__(self):
        self._entities: dict[str, Entity] = {}
        self._relationships: list[Relationship] = []
        self._index: dict[EntityType, list[str]] = {}  # entity_type -> entity_ids

    async def add_entity(self, entity: Entity) -> Entity:
        """Add entity to graph."""
        self._entities[entity.entity_id] = entity

        # Update index
        if entity.entity_type not in self._index:
            self._index[entity.entity_type] = []
        self._index[entity.entity_type].append(entity.entity_id)

        logger.info("entity_added", entity_id=entity.entity_id, type=entity.entity_type.value)
        return entity

    async def add_relationship(self, relationship: Relationship) -> Relationship:
        """Add relationship to graph."""
        self._relationships.append(relationship)
        logger.info(
            "relationship_added",
            source=relationship.source_id,
            target=relationship.target_id,
            type=relationship.relationship_type.value,
        )
        return relationship

    async def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID."""
        return self._entities.get(entity_id)

    async def find_entities(
        self,
        entity_type: Optional[EntityType] = None,
        name_contains: Optional[str] = None,
    ) -> list[Entity]:
        """Find entities matching criteria."""
        results = list(self._entities.values())

        if entity_type:
            results = [e for e in results if e.entity_type == entity_type]

        if name_contains:
            name_lower = name_contains.lower()
            results = [e for e in results if name_lower in e.name.lower()]

        return results

    async def get_relationships(self, entity_id: str) -> list[Relationship]:
        """Get all relationships for an entity."""
        return [
            r for r in self._relationships
            if r.source_id == entity_id or r.target_id == entity_id
        ]

    async def find_contradictions(self, fact: str) -> list[Entity]:
        """Find entities that might contradict this fact."""
        # Simplified: return entities with contradicting relationships
        return []

    async def query(self, query: str) -> list[Entity]:
        """Natural language query on knowledge graph."""
        # In production, use graph query or embedding search
        return await self.find_entities(name_contains=query)


# ──────────────────────────────────────────────────────────────────────────────
# Temporal Model
# ──────────────────────────────────────────────────────────────────────────────

class TemporalModel:
    """Timeline understanding and reasoning."""

    def __init__(self):
        self._timelines: dict[str, Timeline] = {}
        self._events: dict[str, list[dict]] = {}  # user_id -> events

    async def add_event(
        self,
        user_id: str,
        event_type: str,
        content: Any,
        timestamp: datetime,
        metadata: dict = None,
    ) -> dict:
        """Add event to timeline."""
        event = {
            "event_id": str(uuid.uuid4()),
            "type": event_type,
            "content": content,
            "timestamp": timestamp.isoformat(),
            "metadata": metadata or {},
        }

        if user_id not in self._events:
            self._events[user_id] = []
        self._events[user_id].append(event)

        logger.info("event_added", user_id=user_id, event_type=event_type)
        return event

    async def get_events(
        self,
        user_id: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        event_type: Optional[str] = None,
    ) -> list[dict]:
        """Get events within time range."""
        events = self._events.get(user_id, [])

        filtered = []
        for event in events:
            event_time = datetime.fromisoformat(event["timestamp"])

            if since and event_time < since:
                continue
            if until and event_time > until:
                continue
            if event_type and event["type"] != event_type:
                continue

            filtered.append(event)

        return filtered

    async def reconstruct_timeline(
        self,
        user_id: str,
        topic: str,
        since: Optional[datetime] = None,
    ) -> Timeline:
        """Reconstruct timeline for a topic."""
        events = await self.get_events(user_id, since=since)

        # Filter events related to topic (simplified)
        relevant_events = [
            e for e in events
            if topic.lower() in str(e.get("content", "")).lower()
        ]

        timeline = Timeline(
            timeline_id=str(uuid.uuid4()),
            user_id=user_id,
            name=f"Timeline: {topic}",
            events=relevant_events,
        )

        return timeline

    async def predict_next_event(self, user_id: str, event_type: str) -> Optional[datetime]:
        """Predict when event will recur."""
        events = await self.get_events(user_id, event_type=event_type)

        if len(events) < 2:
            return None

        # Calculate average interval
        timestamps = sorted([datetime.fromisoformat(e["timestamp"]) for e in events])
        intervals = [
            (timestamps[i+1] - timestamps[i]).total_seconds()
            for i in range(len(timestamps) - 1)
        ]

        avg_interval = sum(intervals) / len(intervals)
        next_time = timestamps[-1] + timedelta(seconds=avg_interval)

        return next_time


# ──────────────────────────────────────────────────────────────────────────────
# User Model Manager
# ──────────────────────────────────────────────────────────────────────────────

class UserModelManager:
    """Manages evolving user model."""

    def __init__(self):
        self._models: dict[str, UserModel] = {}
        self._goals: dict[str, Goal] = {}

    async def get_user_model(self, user_id: str) -> UserModel:
        """Get or create user model."""
        if user_id not in self._models:
            self._models[user_id] = UserModel(user_id=user_id, name="User")
            logger.info("user_model_created", user_id=user_id)

        return self._models[user_id]

    async def update_user_model(self, user_id: str, updates: dict[str, Any]):
        """Update user model properties."""
        model = await self.get_user_model(user_id)

        for key, value in updates.items():
            if hasattr(model, key):
                setattr(model, key, value)

        logger.info("user_model_updated", user_id=user_id, keys=list(updates.keys()))

    async def adapt_coaching_style(self, user_id: str, effectiveness: float):
        """Adapt coaching based on effectiveness feedback."""
        model = await self.get_user_model(user_id)

        # Simple adaptation: increase effectiveness of current style
        if "coaching_history" not in model.coaching_adaptations:
            model.coaching_adaptations["coaching_history"] = []

        model.coaching_adaptations["coaching_history"].append({
            "timestamp": datetime.utcnow().isoformat(),
            "effectiveness": effectiveness,
        })

        # Adjust communication style based on recent interactions
        if effectiveness < 0.5:
            model.communication_style = "more_explanatory"
        elif effectiveness > 0.8:
            model.communication_style = "more_direct"

        logger.info("coaching_style_adapted", user_id=user_id, effectiveness=effectiveness)

    # Goal management
    async def create_goal(self, user_id: str, title: str, description: str, deadline: datetime = None) -> Goal:
        """Create a new goal."""
        goal = Goal(
            goal_id=str(uuid.uuid4()),
            user_id=user_id,
            title=title,
            description=description,
            status="active",
            deadline=deadline,
        )
        self._goals[goal.goal_id] = goal

        logger.info("goal_created", user_id=user_id, goal_id=goal.goal_id, title=title)
        return goal

    async def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Get goal by ID."""
        return self._goals.get(goal_id)

    async def get_user_goals(self, user_id: str, status: Optional[str] = None) -> list[Goal]:
        """Get all goals for user."""
        goals = [g for g in self._goals.values() if g.user_id == user_id]

        if status:
            goals = [g for g in goals if g.status == status]

        return goals

    async def update_goal_progress(self, goal_id: str, progress: float):
        """Update goal progress."""
        goal = self._goals.get(goal_id)
        if goal:
            goal.progress = progress
            goal.updated_at = datetime.utcnow()

            if progress >= 1.0:
                goal.status = "achieved"

            logger.info("goal_progress_updated", goal_id=goal_id, progress=progress)


# ──────────────────────────────────────────────────────────────────────────────
# Relationship Manager
# ──────────────────────────────────────────────────────────────────────────────

class RelationshipManager:
    """Manages people and relationships."""

    def __init__(self):
        self._people: dict[str, Person] = {}

    async def add_person(self, person: Person) -> Person:
        """Add or update person."""
        self._people[person.person_id] = person
        logger.info("person_added", person_id=person.person_id, name=person.name)
        return person

    async def get_person(self, person_id: str) -> Optional[Person]:
        """Get person by ID."""
        return self._people.get(person_id)

    async def find_person(self, name: str) -> Optional[Person]:
        """Find person by name."""
        name_lower = name.lower()
        for person in self._people.values():
            if name_lower in person.name.lower():
                return person
            if any(name_lower in alias.lower() for alias in person.aliases):
                return person
        return None

    async def get_all_people(self, user_id: str) -> list[Person]:
        """Get all people known by user."""
        return [p for p in self._people.values() if p.user_id == user_id]

    async def update_interaction(
        self,
        person_id: str,
        topics: list[str] = None,
        outcome: str = None,
    ) -> Optional[Person]:
        """Update interaction history with person."""
        person = self._people.get(person_id)
        if not person:
            return None

        person.last_contact = datetime.utcnow()

        if topics:
            for topic in topics:
                if topic not in person.topics_discussed:
                    person.topics_discussed.append(topic)

        if outcome:
            if "interactions" not in person.notes:
                person.notes += f"\nInteraction: {outcome}"

        logger.info("interaction_updated", person_id=person_id, topics=topics)
        return person


# ──────────────────────────────────────────────────────────────────────────────
# Project Manager
# ──────────────────────────────────────────────────────────────────────────────

class ProjectManager:
    """Manages projects."""

    def __init__(self):
        self._projects: dict[str, Project] = {}

    async def create_project(
        self,
        user_id: str,
        name: str,
        description: str,
        deadline: datetime = None,
    ) -> Project:
        """Create new project."""
        project = Project(
            project_id=str(uuid.uuid4()),
            user_id=user_id,
            name=name,
            description=description,
            status="active",
            deadline=deadline,
        )
        self._projects[project.project_id] = project

        logger.info("project_created", project_id=project.project_id, name=name)
        return project

    async def get_project(self, project_id: str) -> Optional[Project]:
        """Get project by ID."""
        return self._projects.get(project_id)

    async def get_user_projects(self, user_id: str, status: Optional[str] = None) -> list[Project]:
        """Get all projects for user."""
        projects = [p for p in self._projects.values() if p.user_id == user_id]

        if status:
            projects = [p for p in projects if p.status == status]

        return projects


# ──────────────────────────────────────────────────────────────────────────────
# Unified World Model
# ──────────────────────────────────────────────────────────────────────────────

class WorldModel:
    """
    Unified world model - the single source of truth for all cognitive subsystems.

    All subsystems read from and write to this model.
    """

    def __init__(self):
        self.knowledge_graph = KnowledgeGraph()
        self.temporal_model = TemporalModel()
        self.user_model = UserModelManager()
        self.relationships = RelationshipManager()
        self.projects = ProjectManager()

        logger.info("world_model_initialized")

    # ─────────────────────────────────────────────────────────────────────────
    # Unified entity/relationship management
    # ─────────────────────────────────────────────────────────────────────────

    async def add_entity(
        self,
        user_id: str,
        entity_type: EntityType,
        name: str,
        properties: dict = None,
    ) -> Entity:
        """Add entity to world model."""
        entity = Entity(
            entity_id=str(uuid.uuid4()),
            entity_type=entity_type,
            name=name,
            properties=properties or {},
        )

        return await self.knowledge_graph.add_entity(entity)

    async def relate_entities(
        self,
        source_name: str,
        target_name: str,
        relationship_type: RelationshipType,
    ) -> Optional[Relationship]:
        """Create relationship between entities."""
        source = await self.knowledge_graph.find_entities(name_contains=source_name)
        target = await self.knowledge_graph.find_entities(name_contains=target_name)

        if not source or not target:
            logger.warning("relate_entities_not_found", source=source_name, target=target_name)
            return None

        relationship = Relationship(
            relationship_id=str(uuid.uuid4()),
            source_id=source[0].entity_id,
            target_id=target[0].entity_id,
            relationship_type=relationship_type,
        )

        return await self.knowledge_graph.add_relationship(relationship)

    # ─────────────────────────────────────────────────────────────────────────
    # Temporal reasoning
    # ─────────────────────────────────────────────────────────────────────────

    async def record_event(
        self,
        user_id: str,
        event_type: str,
        content: Any,
        metadata: dict = None,
    ):
        """Record event in timeline."""
        await self.temporal_model.add_event(
            user_id=user_id,
            event_type=event_type,
            content=content,
            timestamp=datetime.utcnow(),
            metadata=metadata,
        )

    async def get_conversation_history(
        self,
        user_id: str,
        person_name: str = None,
        topic: str = None,
        days_back: int = 30,
    ) -> list[dict]:
        """Get conversation history with filters."""
        since = datetime.utcnow() - timedelta(days=days_back)

        events = await self.temporal_model.get_events(user_id, since=since, event_type="conversation")

        if person_name:
            events = [e for e in events if person_name.lower() in str(e.get("content", "")).lower()]

        if topic:
            events = [e for e in events if topic.lower() in str(e.get("content", "")).lower()]

        return events

    # ─────────────────────────────────────────────────────────────────────────
    # User understanding
    # ─────────────────────────────────────────────────────────────────────────

    async def update_user_preferences(self, user_id: str, preferences: dict):
        """Update user preferences."""
        await self.user_model.update_user_model(user_id, {"preferences": preferences})

    async def get_user_context(self, user_id: str) -> dict:
        """Get comprehensive user context for cognition."""
        user_model = await self.user_model.get_user_model(user_id)
        goals = await self.user_model.get_user_goals(user_id, status="active")
        projects = await self.projects.get_user_projects(user_id, status="active")

        return {
            "user_model": user_model,
            "active_goals": goals,
            "active_projects": projects,
        }


def create_world_model() -> WorldModel:
    """Factory function to create world model."""
    return WorldModel()