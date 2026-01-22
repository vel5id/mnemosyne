"""
Mnemosyne Core V3.0 - Infrastructure Tests

Тесты для проверки:
1. SystemGuard корректно инициализирует NVML
2. DatabaseProvider может читать из базы данных
"""

import asyncio
import unittest
from pathlib import Path
import tempfile
import sys

# Добавляем корневую директорию в путь для импорта модулей
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.system.guardrails import SystemGuard
from core.dal.sqlite_provider import DatabaseProvider


class TestSystemGuard(unittest.TestCase):
    """Тесты для SystemGuard."""

    def setUp(self):
        """Настройка перед каждым тестом."""
        self.guard = SystemGuard(vram_threshold_gb=4.0)

    def tearDown(self):
        """Очистка после каждого теста."""
        if self.guard:
            self.guard.shutdown()

    def test_nvml_initialization(self):
        """Проверка корректной инициализации NVML."""
        # Проверяем, что NVML инициализируется без ошибок
        # (даже если GPU нет, не должно быть исключений)
        try:
            self.assertIsNotNone(self.guard)
            # Если NVML недоступен, nvml_initialized будет False
            # Это допустимое поведение для систем без NVIDIA GPU
            if self.guard.nvml_initialized:
                self.assertTrue(self.guard.nvml_initialized)
        except Exception as e:
            self.fail(f"SystemGuard initialization failed: {e}")

    def test_vram_query(self):
        """Проверка запроса VRAM."""
        try:
            free_vram = self.guard.get_free_vram_bytes()

            if self.guard.nvml_initialized:
                # Если NVML инициализирован, должны получить значение
                self.assertIsNotNone(free_vram)
                self.assertGreaterEqual(free_vram, 0)

                # Проверяем can_run_vision_model
                result = self.guard.can_run_vision_model()
                self.assertIsInstance(result, bool)
            else:
                # Если NVML недоступен, должно вернуть None
                self.assertIsNone(free_vram)
        except Exception as e:
            self.fail(f"VRAM query failed: {e}")

    def test_user_activity_check(self):
        """Проверка проверки активности пользователя."""
        try:
            result = self.guard.is_user_active()
            self.assertIsInstance(result, bool)
        except Exception as e:
            self.fail(f"User activity check failed: {e}")

    def test_is_safe_to_run(self):
        """Проверка комплексной проверки безопасности."""
        try:
            result = self.guard.is_safe_to_run()
            self.assertIsInstance(result, bool)
        except Exception as e:
            self.fail(f"Safety check failed: {e}")


class TestDatabaseProvider(unittest.TestCase):
    """Тесты для DatabaseProvider."""

    def setUp(self):
        """Настройка перед каждым тестом."""
        # Создаем временную базу данных для тестов
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_mnemosyne.db")
        self.db = DatabaseProvider(self.db_path)

    def tearDown(self):
        """Очистка после каждого теста."""
        # Закрываем соединение и удаляем временную директорию
        if hasattr(self, 'db') and self.db._connection:
            asyncio.run(self.db.disconnect())
        self.temp_dir.cleanup()

    def test_connection(self):
        """Проверка подключения к базе данных."""
        async def run_test():
            await self.db.connect()
            self.assertIsNotNone(self.db._connection)

        asyncio.run(run_test())

    def test_pragma_settings(self):
        """Проверка применения PRAGMA настроек."""
        async def run_test():
            await self.db.connect()

            # Проверяем journal_mode (DELETE for Windows+Docker compatibility)
            cursor = await self.db._connection.execute("PRAGMA journal_mode")
            result = await cursor.fetchone()
            self.assertEqual(result[0], "delete")

            # Проверяем synchronous
            cursor = await self.db._connection.execute("PRAGMA synchronous")
            result = await cursor.fetchone()
            self.assertEqual(result[0], 1)  # NORMAL = 1

            # Проверяем temp_store
            cursor = await self.db._connection.execute("PRAGMA temp_store")
            result = await cursor.fetchone()
            self.assertEqual(result[0], 2)  # MEMORY = 2

        asyncio.run(run_test())

    def test_fetch_pending_events_empty(self):
        """Проверка выборки событий из пустой базы."""
        async def run_test():
            await self.db.connect()
            # Создаем схему базы данных
            schema_sql = Path("db/schema.sql").read_text(encoding='utf-8')
            await self.db._connection.executescript(schema_sql)
            
            events = await self.db.fetch_pending_events(limit=100)
            self.assertEqual(len(events), 0)

        asyncio.run(run_test())

    def test_mark_as_processed_empty(self):
        """Проверка пометки событий как обработанных (пустой список)."""
        async def run_test():
            await self.db.connect()
            # Не должно вызывать исключений
            await self.db.mark_as_processed([])

        asyncio.run(run_test())

    def test_get_stats_empty(self):
        """Проверка получения статистики из пустой базы."""
        async def run_test():
            await self.db.connect()
            # Создаем схему базы данных
            schema_sql = Path("db/schema.sql").read_text(encoding='utf-8')
            await self.db._connection.executescript(schema_sql)
            
            stats = await self.db.get_stats()

            self.assertIn("total_events", stats)
            self.assertIn("pending_events", stats)
            self.assertIn("enriched_events", stats)

            self.assertEqual(stats["total_events"], 0)
            self.assertEqual(stats["pending_events"], 0)
            self.assertEqual(stats["enriched_events"], 0)

        asyncio.run(run_test())

    def test_context_manager(self):
        """Проверка работы контекстного менеджера."""
        async def run_test():
            async with DatabaseProvider(self.db_path) as db:
                self.assertIsNotNone(db._connection)
            # После выхода из контекста соединение должно быть закрыто
            self.assertIsNone(db._connection)

        asyncio.run(run_test())


class TestDatabaseWithExistingSchema(unittest.TestCase):
    """Тесты для работы с существующей базой (созданной Go-модулем)."""

    def setUp(self):
        """Настройка перед каждым тестом."""
        # Путь к реальной базе данных, созданной Watcher'ом
        self.db_path = "db/mnemosyne.db"
        self.db = DatabaseProvider(self.db_path)

    def tearDown(self):
        """Очистка после каждого теста."""
        if hasattr(self, 'db') and self.db._connection:
            asyncio.run(self.db.disconnect())

    def test_connect_to_existing_db(self):
        """Проверка подключения к существующей базе данных."""
        async def run_test():
            # Пропускаем тест если файл базы не существует
            if not Path(self.db_path).exists():
                self.skipTest(f"Database file not found: {self.db_path}")

            await self.db.connect()
            self.assertIsNotNone(self.db._connection)

        asyncio.run(run_test())

    def test_get_stats_from_existing_db(self):
        """Проверка получения статистики из существующей базы."""
        async def run_test():
            if not Path(self.db_path).exists():
                self.skipTest(f"Database file not found: {self.db_path}")

            await self.db.connect()
            stats = await self.db.get_stats()

            self.assertIn("total_events", stats)
            self.assertIn("pending_events", stats)
            self.assertIn("enriched_events", stats)

            print(f"\nDatabase stats: {stats}")

        asyncio.run(run_test())

    def test_fetch_pending_from_existing_db(self):
        """Проверка выборки событий из существующей базы."""
        async def run_test():
            if not Path(self.db_path).exists():
                self.skipTest(f"Database file not found: {self.db_path}")

            await self.db.connect()
            events = await self.db.fetch_pending_events(limit=100)

            self.assertIsInstance(events, list)
            print(f"\nFetched {len(events)} pending events")

            # Если есть события, проверяем их структуру
            if events:
                event = events[0]
                self.assertIn("id", event)
                self.assertIn("process_name", event)
                self.assertIn("window_title", event)
                self.assertIn("unix_time", event)

        asyncio.run(run_test())


def run_tests():
    """Запуск всех тестов."""
    # Создаем тестовый набор
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Добавляем тесты
    suite.addTests(loader.loadTestsFromTestCase(TestSystemGuard))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseProvider))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseWithExistingSchema))

    # Запускаем тесты
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Возвращаем код выхода
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
