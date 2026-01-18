-- Mnemosyne Core V3.0 - Database Schema
-- SQLite WAL Mode Configuration
-- Документация: docs/04_SQL_Schema.md

-- ============================================================================
-- PRAGMA Настройки (применяются при инициализации соединения)
-- ============================================================================
-- journal_mode=WAL       - Позволяет одновременное чтение и запись
-- synchronous=NORMAL     - Буферизация записи для защиты SSD
-- temp_store=MEMORY     - Временные таблицы в RAM (80GB доступно)
-- mmap_size=268435456    - 256MB Memory-Mapped I/O
-- busy_timeout=5000      - Таймаут ожидания при блокировке (5 сек)
-- foreign_keys=ON       - Включаем внешние ключи
PRAGMA foreign_keys = ON;

-- ============================================================================
-- Таблица raw_events: Хроника Активности (Tier 1 - Watcher)
-- ============================================================================
CREATE TABLE IF NOT EXISTS raw_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Уникальный идентификатор события
    session_uuid TEXT NOT NULL,            -- ID сессии (от запуска до выключения Mnemosyne)
    timestamp_utc TEXT NOT NULL,           -- Время события в формате ISO8601 (для переносимости)
    unix_time INTEGER NOT NULL,            -- Время в Unix Epoch (для индексации и быстрого поиска)
    
    -- Tier 1 Metadata (Получено через Win32 API)
    process_name TEXT NOT NULL,            -- Имя исполняемого файла (напр., "chrome.exe")
    window_title TEXT,                     -- Заголовок окна (напр., "SQLite WAL optimization - Google Search")
    window_hwnd INTEGER NOT NULL,          -- Дескриптор окна (для идентификации уникальности окна)
    
    -- Region of Interest (ROI) - Координаты для VLM
    roi_left INTEGER,
    roi_top INTEGER,
    roi_right INTEGER,
    roi_bottom INTEGER,
    
    -- Input Telemetry (Поведенческий анализ)
    input_idle_ms INTEGER DEFAULT 0,       -- Время бездействия пользователя (мс)
    input_intensity REAL DEFAULT 0.0,      -- Вычисленный коэффициент активности ввода (0.0 - 1.0)
    
    -- System Flags
    is_processed BOOLEAN DEFAULT 0,        -- Флаг: обработано ли событие модулем Brain
    has_screenshot BOOLEAN DEFAULT 0,      -- Флаг: сохранен ли скриншот на диске
    screenshot_hash TEXT                   -- Хэш файла скриншота (для дедупликации)
);

-- Индексы для оптимизации raw_events
CREATE INDEX IF NOT EXISTS idx_raw_time ON raw_events(unix_time);
CREATE INDEX IF NOT EXISTS idx_raw_processed ON raw_events(is_processed) WHERE is_processed = 0; -- Частичный индекс для очереди обработки
CREATE INDEX IF NOT EXISTS idx_raw_session ON raw_events(session_uuid);
CREATE INDEX IF NOT EXISTS idx_raw_process ON raw_events(process_name);

-- ============================================================================
-- Таблица context_enrichment: Семантический Слой (Tier 2 - Brain)
-- ============================================================================
CREATE TABLE IF NOT EXISTS context_enrichment (
    event_id INTEGER PRIMARY KEY,
    
    -- Textual Signals (Tier 2 & 3)
    accessibility_tree_json TEXT,          -- Полный дамп структуры UI (кнопки, поля ввода)
    ocr_content TEXT,                      -- Текст, извлеченный via OCR (Tesseract/EasyOCR)
    
    -- Semantic Analysis (Tier 4 - AI)
    vlm_description TEXT,                  -- Описание визуальной сцены от MiniCPM-V
    user_intent TEXT,                      -- Интерпретация намерения пользователя (LLM)
    
    -- Knowledge Graph Integration
    generated_wikilinks TEXT,              -- JSON массив ссылок (напр., ["[[Project Alpha]]"])
    generated_tags TEXT,                   -- JSON массив тегов (напр., ["#research", "#urgent"])
    
    FOREIGN KEY(event_id) REFERENCES raw_events(id) ON DELETE CASCADE
);

-- ============================================================================
-- Виртуальная Таблица fts_search: Полнотекстовый Поиск (FTS5)
-- ============================================================================
CREATE VIRTUAL TABLE IF NOT EXISTS fts_search USING fts5(
    window_title,
    ocr_content,
    vlm_description,
    user_intent
);

-- Триггер для автоматической синхронизации при вставке
CREATE TRIGGER IF NOT EXISTS trg_fts_insert AFTER INSERT ON context_enrichment BEGIN
  INSERT INTO fts_search(window_title, ocr_content, vlm_description, user_intent)
  VALUES ((SELECT window_title FROM raw_events WHERE id = new.event_id),
          new.ocr_content,
          new.vlm_description,
          new.user_intent);
END;

-- Триггер для автоматической синхронизации при обновлении
CREATE TRIGGER IF NOT EXISTS trg_fts_update AFTER UPDATE ON context_enrichment BEGIN
  DELETE FROM fts_search WHERE rowid = new.event_id;
  INSERT INTO fts_search(window_title, ocr_content, vlm_description, user_intent)
  VALUES ((SELECT window_title FROM raw_events WHERE id = new.event_id),
          new.ocr_content,
          new.vlm_description,
          new.user_intent);
END;

-- Триггер для автоматической синхронизации при удалении
CREATE TRIGGER IF NOT EXISTS trg_fts_delete AFTER DELETE ON context_enrichment BEGIN
  DELETE FROM fts_search WHERE rowid = old.event_id;
END;

-- ============================================================================
-- Таблица sessions: Агрегированные Сессии (Phase 6 - Session Aggregation)
-- ============================================================================
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uuid TEXT UNIQUE NOT NULL,     -- Уникальный идентификатор сессии
    start_time INTEGER NOT NULL,           -- Unix timestamp начала
    end_time INTEGER NOT NULL,             -- Unix timestamp конца
    duration_seconds INTEGER NOT NULL,     -- Продолжительность в секундах
    
    -- Primary Context
    primary_process TEXT NOT NULL,         -- Основное приложение
    primary_window TEXT NOT NULL,          -- Основной заголовок окна
    
    -- Aggregated Data
    window_transitions TEXT,               -- JSON: ["app1:window", "app2:window", ...]
    event_count INTEGER DEFAULT 0,         -- Количество событий в сессии
    avg_input_intensity REAL,              -- Средняя интенсивность ввода (0-100)
    
    -- LLM Analysis
    activity_summary TEXT,                 -- LLM-суммаризация: "Debugging Redis..."
    generated_tags TEXT,                   -- JSON: ["coding", "debugging"]
    
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для sessions
CREATE INDEX IF NOT EXISTS idx_sessions_time ON sessions(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_sessions_process ON sessions(primary_process);
