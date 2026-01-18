# Python Requirements (requirements.txt)

Содержимое для `requirements.txt`:

```txt
# Python 3.12.7

# Database
aiosqlite>=0.19.0

# System & VRAM Guard
pynvml>=11.5.0
psutil>=5.9.8

# UI Automation
uiautomation>=2.0.20

# OCR
pytesseract>=0.3.10
# Optional GPU OCR (install if VRAM available)
# easyocr>=1.7.1

# Vision & AI
torch>=2.1.0
torchvision>=0.16.0
transformers>=4.36.0
accelerate>=0.25.0
bitsandbytes>=0.41.0

# Image Processing
pillow>=10.2.0

# Security
# (Standard library re module is sufficient for PII sanitization)

# Obsidian Integration (optional, for direct file access)
# pywin32>=306 (Windows specific)
```

**Категории зависимостей:**
- **Database:** `aiosqlite` - асинхронный драйвер SQLite
- **System:** `pynvml` - NVML bindings для VRAM Guard, `psutil` - мониторинг процессов
- **UI Automation:** `uiautomation` - доступ к Windows UI Automation API
- **OCR:** `pytesseract` - CPU-based OCR, `easyocr` - GPU-based OCR (опционально)
- **Vision & AI:** `torch`, `transformers`, `accelerate`, `bitsandbytes` - PyTorch экосистема для VLM (MiniCPM-V Int4)
- **Image Processing:** `pillow` - обработка изображений (crop, convert)
