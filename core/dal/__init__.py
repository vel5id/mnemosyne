"""
Mnemosyne Core V5.0 - Data Access Layer Module

Provides unified access to database providers:
    - DatabaseProvider: SQLite async operations (facade)
    - RedisProvider: Redis streams and cache
    - run_maintenance: Database maintenance utilities

Repository modules (internal):
    - BaseRepository: Connection management
    - EventRepository: Raw events CRUD
    - ContextRepository: Context enrichment
    - SessionRepository: Session aggregation
    - StatsRepository: Analytics queries
"""

from core.dal.sqlite_provider import DatabaseProvider
from core.dal.redis_provider import RedisProvider
from core.dal.maintenance import run_full_maintenance as run_maintenance

__all__ = [
    "DatabaseProvider",
    "RedisProvider",
    "run_maintenance",
]
