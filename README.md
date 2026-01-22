<p align="center">
  <img src="https://raw.githubusercontent.com/vel5id/mnemosyne/main/docs/assets/logo.png" alt="Mnemosyne" width="200"/>
</p>

<h1 align="center">Mnemosyne Core V5.0</h1>

<p align="center">
  <strong>🧠 Local Digital Twin — Enterprise-grade personal analytics with complete data privacy</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#usage">Usage</a> •
  <a href="#roadmap">Roadmap</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Go-1.25-00ADD8?style=flat&logo=go" alt="Go"/>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python" alt="Python"/>
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=flat&logo=docker" alt="Docker"/>
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat" alt="License"/>
</p>

---

## What is Mnemosyne?

Mnemosyne is an **autonomous activity tracking system** that captures, analyzes, and visualizes your digital workflow — completely offline and private. 

Think of it as a **local Rewind.ai** but with Graph RAG, semantic search, and Obsidian integration.

### Key Differentiators

| Feature | Mnemosyne | Cloud Alternatives |
|---------|-----------|-------------------|
| **Data Location** | 100% Local | Cloud servers |
| **AI Processing** | Local LLM (Ollama) | API calls |
| **Privacy** | Air-gap ready | PII concerns |
| **Cost** | Free forever | Subscription |
| **Customization** | Full source access | Limited |

---

## Features

### 🎯 Core Capabilities

- **High-Frequency Capture** — 5Hz activity monitoring via Win32 API
- **AI-Powered Analysis** — Local VLM (MiniCPM-V) + LLM (DeepSeek R1) for intent inference
- **Session Aggregation** — Automatic grouping of activities into meaningful sessions
- **Graph RAG** — Semantic search across your entire activity history
- **Obsidian Integration** — WikiLinks, tags, and Daily Notes export

### 🔐 Privacy First

- **Air-Gap Architecture** — Zero cloud dependencies
- **PII Sanitization** — Automatic redaction of emails, IPs, API keys
- **Local LLMs** — All AI runs on your GPU via Ollama

### ⚡ Performance

- **Go Watcher**: <0.1% CPU, <20MB RAM
- **Write-Behind Pattern**: Redis buffer protects SSD from write amplification
- **VRAM Guard**: Dynamic model loading based on available GPU memory

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MNEMOSYNE CORE V5.0                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌─────────────┐    ┌─────────────────────────────────────────┐   │
│   │   WATCHER   │    │              REDIS STACK                │   │
│   │    (Go)     │───>│  ┌────────┐ ┌────────┐ ┌────────────┐  │   │
│   │   5Hz Poll  │    │  │ Stream │ │ Vector │ │  DocStore  │  │   │
│   └─────────────┘    │  │ Buffer │ │ Store  │ │            │  │   │
│                      │  └────────┘ └────────┘ └────────────┘  │   │
│                      └──────────────────┬──────────────────────┘   │
│                                         │                          │
│   ┌─────────────────────────────────────▼──────────────────────┐   │
│   │                         BRAIN (Python)                      │   │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │   │
│   │  │ Session  │ │  Intent  │ │  Graph   │ │   LlamaIndex │   │   │
│   │  │ Tracker  │ │ Inference│ │   RAG    │ │  VectorStore │   │   │
│   │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │   │
│   └──────────────────────────────────────────────────────────────┘   │
│                                         │                          │
│   ┌─────────────┐    ┌─────────────┐    ▼                          │
│   │   OLLAMA    │    │   SQLite    │  ┌─────────────┐              │
│   │  VLM + LLM  │    │   Archive   │  │  Obsidian   │              │
│   └─────────────┘    └─────────────┘  │  WikiLinks  │              │
│                                        └─────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Watcher** | Go 1.25 | High-frequency capture, Win32 API |
| **Brain** | Python 3.12 | AI analysis, session tracking, RAG |
| **VectorDB** | Redis Stack | Embeddings, semantic search |
| **LLM** | Ollama (DeepSeek R1) | Intent inference, summarization |
| **VLM** | Ollama (MiniCPM-V) | Screenshot analysis |
| **Graph** | NetworkX | Knowledge graph, related concept discovery |
| **Archive** | SQLite WAL | Persistent storage |

---

## Quick Start

### Prerequisites

- **OS**: Windows 10/11
- **GPU**: NVIDIA RTX (8GB+ VRAM recommended)
- **RAM**: 16GB+ (80GB recommended for aggressive caching)
- **Software**: Docker, Go 1.22+, Python 3.12, Ollama

### Installation

```powershell
# 1. Clone repository
git clone https://github.com/vel5id/mnemosyne.git
cd mnemosyne

# 2. Setup Python environment
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 3. Build Go Watcher
scripts\build_watcher.bat

# 4. Start Redis Stack
docker-compose up -d redis

# 5. Pull Ollama models
ollama pull minicpm-v
ollama pull deepseek-r1:1.5b
ollama pull nomic-embed-text

# 6. Initialize database
scripts\reset_db.bat
```

---

## Usage

### Start the System

```powershell
# Terminal 1: Start Watcher (captures activity)
scripts\run_watcher.bat

# Terminal 2: Start Brain (processes activity)
scripts\brain_v4.bat
```

### Query Your History

```powershell
# Semantic search
python scripts\query_rag.py "What was I debugging yesterday?"

# Find related concepts
python scripts\query_rag.py --related redis

# View sessions
python scripts\view_sessions.py
```

### Maintenance

```powershell
# Database cleanup (prune old data, VACUUM)
scripts\maintain_db.bat

# Complete reset
scripts\reset_db.bat
```

---

## Configuration

Copy `.env.example` to `.env` and configure:

```env
# Paths
MNEMOSYNE_DB_PATH=.mnemosyne/activity.db
OBSIDIAN_VAULT_PATH=C:/Users/your_vault

# AI Models
VLM_MODEL=minicpm-v
LLM_MODEL_HEAVY=deepseek-r1:1.5b

# Redis
MNEMOSYNE_REDIS_HOST=localhost
```

---

## Project Structure

```
mnemosyne/
├── cmd/watcher/           # Go entry point
├── internal/              # Go modules
│   ├── monitor/          # 5Hz polling loop
│   ├── buffer/           # RAM buffer
│   ├── storage/          # Redis + SQLite writers
│   └── heuristics/       # Game detection, idle tracking
├── core/                  # Python modules
│   ├── aggregation/      # Session tracking
│   ├── cognition/        # LLM intent inference
│   ├── perception/       # OCR, VLM, UI automation
│   ├── rag/              # LlamaIndex + NetworkX
│   ├── dal/              # Database access layer
│   └── security/         # PII sanitization
├── scripts/              # CLI utilities
├── docker/               # Container definitions
├── db/                   # SQL schemas
└── docs/                 # Architecture documentation
```

---

## Roadmap

- [x] **Phase 1-5**: Core Watcher + Brain pipeline
- [x] **Phase 6**: Session Aggregation with LLM summarization
- [x] **Phase 7**: Storage Optimization (VACUUM, pruning)
- [x] **Phase 8**: Graph RAG (LlamaIndex + NetworkX)
- [ ] **Phase 9**: Obsidian Plugin for real-time dashboard
- [ ] **Phase 10**: Cross-platform support (Linux, macOS)

---

## Documentation

- [Watcher Architecture](docs/01_Watcher_Go_Arch.md)
- [Brain Architecture](docs/02_Brain_Python_Arch.md)
- [SQL Schema](docs/04_SQL_Schema.md)
- [ROADMAP](ROADMAP.md)

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing`)
5. Open a Pull Request

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>Built with 🧠 by <a href="https://github.com/vel5id">vel5id</a></strong>
</p>
