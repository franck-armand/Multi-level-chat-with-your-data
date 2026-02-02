# ChatWithDocs

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-36%20passing-brightgreen.svg)]()
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

> **Chat with your documents using AI. Upload PDFs, Word docs, CSVs, and text files, then ask questions in natural language.**

ChatWithDocs is a production-ready RAG (Retrieval-Augmented Generation) system that brings the power of AI to your documents. Whether you're analyzing research papers, reviewing contracts, or exploring datasets, simply upload your files and start a conversation.

<img width="1521" height="991" alt="Image" src="https://github.com/user-attachments/assets/a6f0abca-6634-40e8-b26f-87253869b604" />

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

```bash
# Clone the repository
git clone <repository-url>
cd chatwithdocs

# Start all services
docker-compose up -d

# Access the web interface
open http://localhost:8501
```

### Option 2: Local Installation (Development)

```bash
# Clone and install
git clone <repository-url>
cd chatwithdocs
uv sync

# Configure AI provider
export LLM_PROVIDER=ollama
export OLLAMA_MODEL=llama3.2

# Start the web interface
uv run streamlit run app/streamlit_app_v2.py
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
# 1. Clone the repository
git clone <repository-url>
cd chatwithdocs

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
uv run streamlit run app/streamlit_app_v2.py
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
chatwithdocs conversations                    # List all
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
| `GET` | `/api/conversations/{user_id}` | List conversations |
| `GET` | `/api/health` | Health check |

**Example API Usage:**

```bash
# Chat via API
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Summarize the document",
    "user_id": "user_123",
    "thread_id": null
  }'

# Upload via API
curl -X POST http://localhost:8000/api/upload \
  -F "file=@document.pdf" \
  -F "user_id=user_123"
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

### Project Structure

```
chatwithdocs/
├── src/chatwithdocs/          # Main package
│   ├── chat/                  # Chat system (models, engine, persistence)
│   ├── config/                # Configuration management
│   ├── embedding/             # Embedding providers (OpenAI, local)
│   ├── ingestion/             # File processing pipeline
│   ├── llm/                   # LLM clients (Ollama, OpenAI, etc.)
│   ├── retrieval/             # Search (hybrid, reranker, citations)
│   ├── security/              # Security (injection, PII, sandbox)
│   └── storage/               # Vector and data storage
├── app/
│   └── streamlit_app_v2.py    # Web interface
├── api/
│   └── main.py                # FastAPI server
├── tests/                     # Test suite (36 tests)
├── Dockerfile                 # Docker image
├── docker-compose.yml         # Docker orchestration
└── README.md                  # This file
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

- **Issues**: Report bugs at https://github.com/franck-armand/Multi-level-chat-with-your-data/issues
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
