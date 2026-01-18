# Configuration Files

## 1. Watcher Configuration (config/watcher.yaml)

```yaml
# Mnemosyne Core - Watcher Configuration
# Tier 1: The Watcher (Go)

# Polling Settings
polling:
  frequency_hz: 5  # 5Hz = 200ms interval
  tick_interval_ms: 200

# Buffer Settings
buffer:
  capacity: 1500  # Max events in RAM buffer
  flush_threshold: 500  # Flush when 500 events accumulated
  flush_timeout_minutes: 5  # Flush every 5 minutes

# Database Settings
database:
  path: ".mnemosyne/activity.db"
  wal_mode: true
  synchronous: "NORMAL"
  temp_store: "MEMORY"
  mmap_size: 268435456  # 256MB
  busy_timeout: 5000  # 5 seconds

# CSV Logging (Parallel Channel)
csv_logging:
  enabled: true
  path: ".mnemosyne/logs/raw_activity_stream.csv"
  max_size_mb: 10
  max_backups: 10
  max_age_days: 28
  compress: true

# Game Detection (Smart Full Stop)
game_detection:
  enabled: true
  check_fullscreen: true
  blacklist_processes:
    - "cs2.exe"
    - "dota2.exe"
    - "valorant.exe"
    - "eldenring.exe"
    - "blender.exe"  # When rendering

# Idle Detection
idle:
  enabled: true
  threshold_seconds: 60  # Consider idle after 60s

# Logging
logging:
  level: "INFO"  # DEBUG, INFO, WARN, ERROR
  path: ".mnemosyne/logs/watcher.log"
```

## 2. Brain Configuration (config/brain.yaml)

```yaml
# Mnemosyne Core - Brain Configuration
# Tier 2: The Brain (Python)

# Database Connection
database:
  path: ".mnemosyne/activity.db"
  batch_size: 100  # Max events per batch

# VRAM Guard (Critical for RTX 5060 Ti)
vram_guard:
  enabled: true
  free_threshold_mb: 4096  # Require 4GB+ free VRAM
  check_interval_seconds: 30
  model_unload_delay_seconds: 300  # Unload after 5min idle

# Processing Settings
processing:
  poll_interval_seconds: 5
  batch_processing: true
  batch_size: 50  # Process 50 events at once

# Context Layer Cake
context:
  priority_ui_automation: true  # Use Accessibility Tree first
  ocr_fallback: true
  ocr_engine: "tesseract"  # tesseract or easyocr
  vlm_enabled: true
  vlm_model: "openbmb/MiniCPM-V-2_6-int4"
  vlm_batch_size: 10  # Process 10 images per batch

# PII Sanitization
sanitization:
  enabled: true
  patterns:
    email: true
    ip_address: true
    credit_card: true
    api_keys: true

# Obsidian Integration
obsidian:
  enabled: true
  vault_path: ""  # Auto-detect or specify
  daily_note_format: "YYYY-MM-DD.md"
  daily_note_folder: "Mnemosyne/Logs"

# Logging
logging:
  level: "INFO"
  path: ".mnemosyne/logs/brain.log"
```

## 3. Environment Variables (.env.example)

```env
# Mnemosyne Core - Environment Variables

# Database
MNEMOSYNE_DB_PATH=.mnemosyne/activity.db

# Obsidian Vault
OBSIDIAN_VAULT_PATH=
OBSIDIAN_DAILY_NOTE_FOLDER=Mnemosyne/Logs

# VRAM Guard
VRAM_FREE_THRESHOLD_MB=4096

# Processing
BATCH_SIZE=100
POLL_INTERVAL_SECONDS=5

# Logging
LOG_LEVEL=INFO

# Security (Optional - SQLCipher)
# DB_ENCRYPTION_KEY=

# Model Paths (Optional - for offline models)
# VLM_MODEL_PATH=
# LLM_MODEL_PATH=
```

## 4. Directory Structure

```
config/
├── watcher.yaml      # Watcher (Go) configuration
├── brain.yaml        # Brain (Python) configuration
└── .env.example     # Environment variables template
```
