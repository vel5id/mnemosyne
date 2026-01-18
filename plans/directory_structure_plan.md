# Project Directory Structure Plan

## Полная структура проекта Mnemosyne Core V3.0

```
mnemosyne-core/
│
├── .clinerules                    # Правила проекта
├── ROADMAP.md                     # Основной план реализации
├── README.md                      # Обзор проекта (создать)
├── go.mod                         # Go модуль (создать)
├── requirements.txt                 # Python зависимости (создать)
├── .gitignore                     # Git исключения (создать)
│
├── cmd/                           # Go исполняемые файлы
│   └── watcher/
│       └── main.go                # Точка входа Watcher
│
├── internal/                       # Внутренние пакеты Go
│   ├── win32/                   # Win32 API обертки
│   │   ├── api.go               # Основные syscall функции
│   │   ├── window.go            # Функции работы с окнами
│   │   └── process.go           # Функции работы с процессами
│   │
│   ├── monitor/                 # Основной цикл 5Hz
│   │   ├── ticker.go            # Ticker Loop
│   │   └── watcher.go          # Основной класс Watcher
│   │
│   ├── sensors/                 # Сбор метрик
│   │   ├── window.go            # Данные окна
│   │   ├── input.go             # Input Intensity
│   │   └── geometry.go          # ROI координаты
│   │
│   ├── heuristics/              # Анализ состояния
│   │   ├── game.go              # Game Detection
│   │   ├── idle.go              # Idle Detection
│   │   └── intensity.go         # Input Intensity расчет
│   │
│   ├── buffer/                  # Управление RAM
│   │   ├── ring.go              # Ring Buffer
│   │   └── flush.go             # Flush Policy
│   │
│   └── storage/                 # SQLite взаимодействие
│       ├── db.go                # Соединение с БД
│       ├── transaction.go         # Транзакции
│       └── batch.go              # Batch Insert
│
├── pkg/                          # Публичные пакеты Go
│   └── models/                 # Общие структуры
│       ├── log.go                # LogEntry структура
│       ├── config.go             # Config структура
│       └── metrics.go            # Metrics структура
│
├── scripts/                       # Python модули
│   ├── main.py                  # Точка входа Brain
│   │
│   └── core/
│       ├── dal/                  # Data Access Layer
│       │   ├── sqlite_provider.py  # SQLite провайдер
│       │   └── models.py          # SQLAlchemy модели
│       │
│       ├── perception/            # Слой восприятия
│       │   ├── text_engine.py      # UI Automation
│       │   ├── ocr.py            # OCR (Tesseract/EasyOCR)
│       │   └── vision_agent.py    # VLM (MiniCPM-V)
│       │
│       ├── cognition/             # Когнитивный анализ
│       │   ├── inference.py       # Intent Inference
│       │   └── prompt.py          # Prompt templates
│       │
│       ├── security/              # Безопасность
│       │   └── sanitizer.py       # PII Sanitization
│       │
│       ├── system/                # Управление ресурсами
│       │   └── guardrails.py      # VRAM Guard
│       │
│       └── export/                # Экспорт данных
│           └── obsidian_bridge.py # Obsidian интеграция
│
│   └── Mnemosyne/                # JS скрипты для Obsidian
│       ├── mnemosyne_core.js      # Библиотека ядра
│       ├── mnemosyne_data_connector.js  # Data Ingestion
│       ├── mnemosyne_renderer.js        # Renderer
│       ├── mnemosyne_interact.js        # Interactive UI
│       ├── mnemosyne_dashboard.js       # Dashboard
│       │
│       └── actions/
│           └── flag_entry.js     # Экшен флагирования
│
├── db/                            # SQL схемы
│   ├── init_schema.sql          # Инициализация БД
│   ├── migrations/              # Миграции
│   └── seed_data.sql            # Тестовые данные
│
├── config/                        # Конфигурационные файлы
│   ├── watcher.yaml.example     # Шаблон конфига Watcher
│   ├── brain.yaml.example       # Шаблон конфига Brain
│   └── .env.example            # Переменные окружения
│
├── docs/                          # Документация
│   ├── 01_Watcher_Go_Arch.md   # Архитектура Watcher
│   ├── 02_Brain_Python_Arch.md  # Архитектура Brain
│   ├── 03_View_JS_Arch.md       # Архитектура View
│   ├── 04_SQL_Schema.md         # Схема БД
│   └── 05_Telemetry_Overview.md # Обзор телеметрии
│
├── tests/                         # Тесты
│   ├── go/                     # Go тесты
│   │   ├── buffer_test.go
│   │   ├── storage_test.go
│   │   └── win32_test.go
│   │
│   └── python/                  # Python тесты
│       ├── test_sanitizer.py
│       └── test_guardrails.py
│
└── .mnemosyne/                    # Скрытые данные (в .gitignore)
    ├── activity.db             # SQLite база данных
    ├── activity.db-wal          # WAL файл
    ├── activity.db-shm          # Shared memory файл
    ├── logs/                   # Логи
    │   ├── watcher.log
    │   ├── brain.log
    │   └── raw_activity_stream.csv
    └── screenshots/             # Скриншоты
        └── [timestamp]_[hash].png
```

## Статус директорий

| Директория | Статус | Описание |
|-----------|---------|-----------|
| `cmd/watcher/` | ✅ Создана | Точка входа Watcher |
| `internal/win32/` | ✅ Создана | Win32 API обертки |
| `internal/monitor/` | ✅ Создана | Основной цикл |
| `internal/sensors/` | ✅ Создана | Сбор метрик |
| `internal/heuristics/` | ✅ Создана | Анализ состояния |
| `internal/buffer/` | ✅ Создана | Управление RAM |
| `internal/storage/` | ✅ Создана | SQLite взаимодействие |
| `scripts/core/dal/` | ✅ Создана | Data Access Layer |
| `scripts/core/perception/` | ✅ Создана | Слой восприятия |
| `scripts/core/cognition/` | ✅ Создана | Когнитивный анализ |
| `scripts/core/security/` | ✅ Создана | Безопасность |
| `scripts/core/system/` | ✅ Создана | Управление ресурсами |
| `scripts/core/export/` | ✅ Создана | Экспорт данных |
| `scripts/Mnemosyne/` | ✅ Создана | JS скрипты |
| `scripts/Mnemosyne/actions/` | ✅ Создана | JS экшены |
| `scripts/Mnemosyne/views/` | ✅ Создана | JS вьюхи |
| `db/` | ✅ Создана | SQL схемы |
| `config/` | ❌ Создать | Конфигурационные файлы |
| `pkg/models/` | ❌ Создать | Go структуры |
| `tests/` | ❌ Создать | Тесты |
| `.mnemosyne/` | ❌ Создать | Скрытые данные |

## Задачи по структуре

- [ ] Создать директорию `config/`
- [ ] Создать директорию `pkg/models/`
- [ ] Создать директорию `tests/`
- [ ] Создать директорию `tests/go/`
- [ ] Создать директорию `tests/python/`
- [ ] Создать директорию `.mnemosyne/`
- [ ] Создать директорию `.mnemosyne/logs/`
- [ ] Создать директорию `.mnemosyne/screenshots/`
