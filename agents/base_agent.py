"""
RasoSpeak v2 — BaseAgent
Abstract base class for all agents.
"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseAgent(ABC):
    """Base class for all RasoSpeak agents."""

    name: str

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the agent. Called on startup."""
        pass