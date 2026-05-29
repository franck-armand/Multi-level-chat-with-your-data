# ChatWithDocs

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-36%20passing-brightgreen.svg)]()
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

> **Repo:** `https://github.com/franck-armand/Multi-level-chat-with-your-data` — replace this URL with your fork if you've renamed the repository.

> **Chat with your documents using AI. Upload PDFs, Word docs, CSVs, and text files, then ask questions in natural language.**

ChatWithDocs is a production-ready RAG (Retrieval-Augmented Generation) system that brings the power of AI to your documents. Whether you're analyzing research papers, reviewing contracts, or exploring datasets, simply upload your files and start a conversation.

<img width="1573" height="983" alt="Image" src="https://github.com/user-attachments/assets/cbf7e074-f889-4374-9bed-48b3d1831bcd" />

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
  - [Web Interface](#web-interface)
  - [Command Line](#command-line)
  - [REST API](#rest-api)
- [AI Providers](#ai-providers)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

---

## Features

### Core Capabilities

| Feature | Description |
|---------|-------------|
| **Multi-format Support** | PDF, DOCX, CSV, XLSX, TXT, Markdown |
| **Hybrid Search** | Combines BM25 keyword + semantic vector search |
| **AI Chat** | Natural language Q&A with source citations |
| **Conversation History** | Persistent chat threads with SQLite |
| **Multiple AI Models** | OpenAI, DeepSeek, Kimi, or local Ollama |
| **Security** | Prompt injection detection, PII redaction, file sandboxing |

### Supported File Types

- **Documents**: PDF, DOCX, TXT, Markdown
- **Data**: CSV, XLSX/XLS (spreadsheets)
- **Size**: Up to 50MB per file
- **Processing**: Automatic text extraction, chunking, and embedding

---

## Quick Start

### Option 1: Docker (Recommended for Production)

#### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

#### Quick Start with Ollama (Local LLM)

For free, privacy-focused AI running entirely on your machine:

```bash
# Clone the repository (replace URL with your fork if renamed)
git clone https://github.com/franck-armand/Multi-level-chat-with-your-data.git
cd Multi-level-chat-with-your-data

# Start with Ollama profile (includes local LLM)
docker-compose --profile ollama up -d

# Wait for Ollama to download the model (first run, ~2GB)
docker-compose logs -f ollama

# Access the web interface
open http://localhost:8501  # macOS
# Or visit: http://localhost:8501
```

**Note:** If you see `port is already allocated` on port 11434, Ollama is already running on your host machine. You can either:
1. Stop host Ollama: `pkill ollama`, then re-run the docker-compose command
2. Use the Docker Ollama alongside your host Ollama (see Configuration section)

#### Quick Start with API Keys (Cloud AI)

For users with OpenAI, DeepSeek, or Kimi API keys:

```bash
# Clone the repository (same URL as above — update if repo was renamed)
git clone https://github.com/franck-armand/Multi-level-chat-with-your-data.git
cd Multi-level-chat-with-your-data

# Create .env file with your API key
cat > .env << 'EOF'
# OpenAI
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini

# Or DeepSeek (use OPENAI_API_KEY variable)
# OPENAI_API_KEY=your-deepseek-key
# OPENAI_BASE_URL=https://api.deepseek.com/v1
# OPENAI_MODEL=deepseek-chat

# Or Kimi
# KIMI_API_KEY=your-kimi-key
# LLM_PROVIDER=kimi
# KIMI_MODEL=kimi-k2.5
EOF

# Start without Ollama profile
docker-compose up -d

# Access the web interface
open http://localhost:8501
```

#### Configuration Options

**Using Local Ollama (host machine, not Docker)**

If you already have Ollama installed on your computer:

```bash
# Create .env file
cat > .env << 'EOF'
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2
OLLAMA_BASE_URL=http://host.docker.internal:11434
EOF

# Start without Ollama service
docker-compose up -d
```

**Using Docker Ollama**

For Docker-managed Ollama with automatic model downloads:

```bash
# Add to .env file
cat > .env << 'EOF'
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2
OLLAMA_BASE_URL=http://ollama:11434
EOF

# Start with Ollama profile
docker-compose --profile ollama up -d
```

**Environment Variables Reference**

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_PROVIDER` | AI provider: `ollama`, `openai`, `kimi` | `ollama` |
| `OPENAI_API_KEY` | API key for OpenAI or DeepSeek | `sk-...` |
| `OPENAI_MODEL` | OpenAI model name | `gpt-4o-mini` |
| `OPENAI_BASE_URL` | Custom API base URL (for DeepSeek) | `https://api.deepseek.com/v1` |
| `KIMI_API_KEY` | API key for Kimi | - |
| `KIMI_MODEL` | Kimi model name | `kimi-k2.5` |
| `OLLAMA_MODEL` | Ollama model to use | `llama3.2` |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://ollama:11434` |

#### Troubleshooting

**Port 11434 already in use (Ollama conflict)**

```bash
# Check if Ollama is running on your host machine
curl http://localhost:11434/api/tags

# Option 1: Stop host Ollama and use Docker Ollama
pkill ollama
docker-compose --profile ollama up -d

# Option 2: Keep host Ollama, use it from Docker
# Update .env: OLLAMA_BASE_URL=http://host.docker.internal:11434
docker-compose up -d

# Option 3: Use a different port for Docker Ollama
# In docker-compose.yml, change: 11435:11434
docker-compose --profile ollama up -d
```

**Windows-Specific Tips**

```powershell
# Use host.docker.internal for local Ollama on Windows
cat > .env << 'EOF'
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2
OLLAMA_BASE_URL=http://host.docker.internal:11434
EOF

# PowerShell alternative for host networking
# Start Ollama on your host machine first: ollama serve
# Then use the .env configuration above
docker-compose up -d
```

**Memory Requirements for Ollama**

| Model | RAM Required | GPU (Optional) |
|-------|--------------|----------------|
| `llama3.2` | 4GB | 2GB VRAM |
| `mistral` | 8GB | 4GB VRAM |
| `qwen2.5` | 8GB | 4GB VRAM |

```bash
# If Ollama is slow or crashes, try a smaller model
# Edit .env: OLLAMA_MODEL=llama3.2
# Or pull a smaller model in the container:
docker exec -it chatwithdocs-ollama-1 ollama pull llama3.2:1b
```

**Stopping and Restarting Containers**

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes all data)
docker-compose down -v

# Restart with fresh state
docker-compose down -v
docker-compose --profile ollama up -d

# View logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f app
```

**Container Won't Start**

```bash
# Check for errors
docker-compose logs app

# Common issues:
# 1. Port 8501 already in use
lsof -i :8501  # Find process using port
# Then either stop it or use different port in docker-compose.yml

# 2. Permission denied on data directory (Linux/Mac)
sudo chown -R $USER:$USER data/

# 3. Model download failed
# Re-pull the model:
docker exec -it chatwithdocs-ollama-1 ollama pull llama3.2
```

#### Production Deployment

**Persistent Volumes**

Data is stored in Docker volumes that persist across restarts:

```bash
# View volumes
docker volume ls
# - chatwithdocs_data
# - chatwithdocs_chromadb

# Backup data
docker run --rm -v chatwithdocs_data:/data -v $(pwd):/backup alpine tar czf /backup/data-backup.tar.gz -C /data .

# Restore data
docker run --rm -v chatwithdocs_data:/data -v $(pwd):/backup alpine tar xzf /backup/data-backup.tar.gz -C /data
```

**Production Environment Variables**

Create a `production.env` file:

```bash
cat > production.env << 'EOF'
# AI Provider (choose one)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-production-key
OPENAI_MODEL=gpt-4o

# Security (change these!)
SECRET_KEY=$(openssl rand -hex 32)
ENABLE_AUTH=true

# Storage paths (Docker internal paths)
DATA_DIR=/app/data
VECTOR_STORE_DIR=/app/data/vectors
CHAT_HISTORY_DB=/app/data/chat_history.db
EOF
```

**Health Checks**

```bash
# Check if services are healthy
docker-compose ps

# Health check endpoints
curl http://localhost:8501  # Streamlit UI
curl http://localhost:8000/api/health  # API (if running)

# Check Ollama health
curl http://localhost:11434/api/tags  # If exposed
```

**Docker Compose for Production**

```bash
# Use production environment
docker-compose --env-file production.env -f docker-compose.yml up -d

# With Ollama (if using local AI)
docker-compose --env-file production.env -f docker-compose.yml --profile ollama up -d

# Update without downtime
docker-compose pull
docker-compose up -d
```

### Option 2: Local Installation (Development)

```bash
# Clone and install (update URL if repo was renamed)
git clone https://github.com/franck-armand/Multi-level-chat-with-your-data.git
cd Multi-level-chat-with-your-data

# Install dependencies
uv sync

# For development (includes pytest, ruff)
uv sync --extra dev

# Note: `uv sync` installs runtime dependencies only (enough to run the app).
# `uv sync --extra dev` includes development dependencies needed for tests and linting.
# uv run pytest tests/ -q

# Configure AI provider
export LLM_PROVIDER=ollama
export OLLAMA_MODEL=llama3.2

# Start the web interface
uv run streamlit run app/streamlit_app.py
```

### Option 3: Command Line Only

```bash
# Upload a document
chatwithdocs upload research-paper.pdf

# Ask questions
chatwithdocs chat "What are the main findings?"

# Start API server
chatwithdocs server --api
```

---

## Installation

### Prerequisites

- **Python**: 3.10 or higher
- **UV**: Modern Python package manager
- **Docker** (optional): For containerized deployment

### Step-by-Step Installation

```bash
# 1. Clone the repository (update URL if repo was renamed)
git clone https://github.com/franck-armand/Multi-level-chat-with-your-data.git
cd Multi-level-chat-with-your-data

# 2. Install dependencies
uv sync

# 3. Install development dependencies (optional)
uv sync --extra dev

# 4. Verify installation
uv run pytest tests/ -q
```

### Docker Installation

```bash
# Build image
docker-compose build

# Run with Docker Compose
docker-compose up -d

# With Ollama for local AI (optional)
docker-compose --profile ollama up -d
```

---

## Usage

### Web Interface

The Streamlit-based web interface provides the most user-friendly experience:

```bash
# Start the UI server
chatwithdocs server --ui --port 8501

# Or with uv
uv run streamlit run app/streamlit_app.py
```

**Features:**
- Drag-and-drop file upload
- Real-time document indexing
- Chat with conversation history
- AI model configuration panel
- Dark/light mode support

### Command Line

The CLI provides powerful automation capabilities:

```bash
# Upload documents
chatwithdocs upload contract.pdf --user legal-team
chatwithdocs upload data.csv annual-report.docx

# List uploaded documents
chatwithdocs list

# Chat with documents
chatwithdocs chat "What are the key terms?" --user legal-team
chatwithdocs chat --interactive  # Interactive mode

# Manage conversations
chatwithdocs conversations  # List all
chatwithdocs conversations --delete <thread-id>  # Delete one

# Configure AI
chatwithdocs config --show  # Show current
chatwithdocs config --provider openai --api-key sk-...  # Set OpenAI

# Clear all data
chatwithdocs clear --force  # Warning: deletes everything!
```

### REST API

For integration with other applications:

```bash
# Start API server
chatwithdocs server --api --port 8000

# Or with uvicorn
uv run uvicorn api.main:app --reload --port 8000
```

**API Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/chat` | Send chat message |
| `POST` | `/api/upload` | Upload document |
| `GET` | `/api/conversations` | List conversations (requires `X-User-Id` header) |
| `GET` | `/api/conversations/{thread_id}` | Get conversation history |
| `DELETE` | `/api/conversations/{thread_id}` | Delete a conversation |
| `GET` | `/api/export/conversation/{thread_id}` | Export as markdown or PDF |
| `GET` | `/api/health` | Health check |

**Example API Usage:**

```bash
# Chat via API
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user_123" \
  -d '{"message": "Summarize the document", "thread_id": null}'

# Upload via API
curl -X POST http://localhost:8000/api/upload \
  -H "X-User-Id: user_123" \
  -F "file=@document.pdf"

# Export conversation as markdown
curl -H "X-User-Id: user_123" \
  "http://localhost:8000/api/export/conversation/<thread_id>?format=markdown"

# Export conversation as PDF
curl -H "X-User-Id: user_123" \
  "http://localhost:8000/api/export/conversation/<thread_id>?format=pdf" \
  -o conversation.pdf
```

---

## AI Providers

ChatWithDocs supports multiple AI providers. Choose the one that fits your needs:

### Ollama (Local - Free)

Best for privacy and cost-conscious users.

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start server
ollama serve

# Pull a model
ollama pull llama3.2

# Configure
chatwithdocs config --provider ollama
```

**Models:** llama3.2, mistral, qwen2.5, gemma2

### OpenAI

Best for reliability and performance.

```bash
# Get API key from https://platform.openai.com
export OPENAI_API_KEY="sk-..."

# Configure
chatwithdocs config --provider openai --api-key "$OPENAI_API_KEY"
```

**Models:** gpt-4o-mini, gpt-4o, gpt-3.5-turbo

### DeepSeek

Best value for API-based usage.

```bash
# Get API key from https://deepseek.com
export OPENAI_API_KEY="your-deepseek-key"

# Configure
chatwithdocs config --provider deepseek --api-key "$OPENAI_API_KEY"
```

**Models:** deepseek-chat

### Kimi (Moonshot AI)

Alternative Chinese LLM provider.

```bash
# Get API key from https://platform.moonshot.cn
export KIMI_API_KEY="your-kimi-key"

# Configure
chatwithdocs config --provider kimi --api-key "$KIMI_API_KEY"
```

**Models:** kimi-k2.5, kimi-k1.5

---

## Configuration

Configuration is managed via environment variables or a `.env` file:

```bash
# Create .env file
cat > .env << 'EOF'
# AI Provider
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2
OLLAMA_BASE_URL=http://localhost:11434

# Or use cloud provider
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-...
# OPENAI_MODEL=gpt-4o-mini

# Storage
DATA_DIR=./data
VECTOR_STORE_DIR=./data/vectors
CHAT_HISTORY_DB=./data/chat_history.db

# Security (change in production)
SECRET_KEY=change-this-in-production
ENABLE_AUTH=false
EOF
```

**Environment Variables:**

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | AI provider: ollama, openai, deepseek, kimi | `ollama` |
| `OPENAI_API_KEY` | API key for OpenAI/DeepSeek | - |
| `KIMI_API_KEY` | API key for Kimi | - |
| `OLLAMA_MODEL` | Ollama model name | `llama3.2` |
| `DATA_DIR` | Data storage directory | `./data` |
| `VECTOR_STORE_DIR` | Vector database directory | `./data/vectors` |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        ChatWithDocs                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐     ┌──────────────┐     ┌──────────────┐  │
│  │  Streamlit  │────▶│ Chat Engine  │────▶│ LLM Router   │  │
│  │   UI (8501) │     │              │     │ (Ollama/     │  │
│  └─────────────┘     └──────────────┘     │  OpenAI)     │  │
│                          │                └──────────────┘  │
│                          ▼                                  │
│                   ┌──────────────┐                          │
│                   │ Hybrid Search│                          │
│                   │ BM25 + Vector│                          │
│                   └──────────────┘                          │
│                         │                                   │
│  ┌─────────────┐     ┌──┴───────────┐     ┌──────────────┐  │
│  │  Document   │────▶│   Ingestion  │────▶│  ChromaDB    │  │
│  │   Upload    │     │   Pipeline   │     │ Vector Store │  │
│  └─────────────┘     └──────────────┘     └──────────────┘  │
│                                                             │
│  ┌─────────────┐     ┌──────────────┐     ┌──────────────┐  │
│  │   SQLite    │     │   Security   │     │   FastAPI    │  │
│  │  (History)  │     │Sandbox/PII/  │     │   (8000)     │  │
│  └─────────────┘     │Injection     │     └──────────────┘  │
│                      └──────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Upload**: Documents are sandboxed and scanned for security
2. **Extraction**: Text is extracted based on file type (PDF, DOCX, etc.)
3. **Chunking**: Content is split into semantic chunks
4. **Embedding**: Chunks are converted to vector embeddings
5. **Storage**: Vectors stored in ChromaDB, metadata in SQLite
6. **Retrieval**: Hybrid search combines BM25 + vector similarity
7. **Generation**: LLM generates answers with context

---

## Development

### Setup Development Environment

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests
uv run pytest tests/ -v

# Run specific test
uv run pytest tests/test_chat_persistence.py -v

# Run linting
uv run ruff check .

# Auto-fix linting issues
uv run ruff check --fix .

# Format code
uv run ruff format .
```

### Running Tests

```bash
# All tests
uv run pytest tests/ -q

# With coverage
uv run pytest tests/ --cov=chatwithdocs --cov-report=html

# End-to-end test
uv run python test_e2e_full.py
```

---

## Troubleshooting

### Common Issues

**1. "No module named 'chatwithdocs'"**
```bash
# Reinstall package
uv sync
```

**2. "Ollama not running"**
```bash
# Start Ollama
ollama serve

# Verify
curl http://localhost:11434/api/tags
```

**3. "API key not configured"**
```bash
# Check configuration
chatwithdocs config --show

# Set provider
chatwithdocs config --provider ollama
```

**4. Port already in use**
```bash
# Use different port
chatwithdocs server --ui --port 8502
```

**5. Permission denied on data directory**
```bash
# Fix permissions
chmod 755 data/
```

### Getting Help

- **Issues**: Report bugs at the repository URL above + `/issues` (update if repo was renamed)
- **Documentation**: This README and inline code docs
- **CLI Help**: `chatwithdocs --help` or `chatwithdocs <command> --help`

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- [ChromaDB](https://www.trychroma.com/) - Vector database
- [Streamlit](https://streamlit.io/) - Web interface framework
- [Ollama](https://ollama.com/) - Local LLM hosting
- [FastAPI](https://fastapi.tiangolo.com/) - API framework
- [Sentence Transformers](https://www.sbert.net/) - Embeddings

---

**Built with Python and love for document intelligence.**
