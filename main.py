"""
Mnemosyne Core V5.0 - Main Entry Point (Tier 2: Brain)

Асинхронный аналитический конвейер для обработки событий от Watcher.
Реализует "Smart Full Stop" для защиты ресурсов системы.

Usage:
    python main.py
"""

import asyncio
import logging
import os
import sys
from typing import Optional

from core.brain import Brain

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('brain.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)


async def main(obsidian_vault_path: Optional[str] = None) -> None:
    """Точка входа."""
    brain = Brain(
        db_path=os.environ.get("MNEMOSYNE_DB_PATH", ".mnemosyne/activity.db"),
        obsidian_vault_path=obsidian_vault_path
    )

    try:
        await brain.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except asyncio.CancelledError:
        logger.info("Task cancelled")
    finally:
        await brain.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
        sys.exit(0)
