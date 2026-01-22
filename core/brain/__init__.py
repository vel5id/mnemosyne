"""
Mnemosyne Core V5.0 - Brain Package

Provides the Brain orchestration system for event processing, 
session management, and Graph RAG integration.

Usage:
    from core.brain import Brain
    
    brain = Brain(db_path=".mnemosyne/activity.db")
    await brain.run()
"""

from core.brain.orchestrator import BrainOrchestrator as Brain
from core.brain.event_processor import EventProcessor
from core.brain.session_manager import SessionManager

__all__ = [
    "Brain",
    "EventProcessor",
    "SessionManager",
]
