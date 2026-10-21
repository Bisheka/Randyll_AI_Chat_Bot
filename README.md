# Randyll Overseas — AI Student Counselling Agent

Answers students' questions about Korean university admissions **only** from the
already-categorized university guideline PDFs (UNI-01 … UNI-12 per university),
with citations to the categorized PDF page and the original guideline pages.
It never invents fees, deadlines, scholarships, TOPIK/IELTS or bank-balance
figures, and never promises admission, visa or scholarship outcomes.

> The separate PDF categorizer that produced those PDFs is unchanged — this
> project consumes its output, it does not regenerate or rearrange it.

## Architecture

```
categorized PDFs ──► ingestion (PyMuPDF: text+tables, header metadata,
                     semantic chunks, SHA-256 idempotency, needs_review flags)
                  ──► JSON knowledge store ──► embeddings (OpenAI, cached;
                     local hash fallback for offline dev/tests)
                  ──► Qdrant `randyll_university_knowledge` (metadata filters
                     applied BEFORE vector search; local store fallback)
student ──► Next.js chat ──► FastAPI agent (intent/university/intake detection
                     → filtered retrieval → Claude/OpenAI answer grounded in
                     retrieved chunks only, else fixed counsellor fallback)
admin ──► Next.js /admin ──► API-key-protected ingest / review / reindex APIs
```

- **LLM:** provider chain with automatic fallback — Gemini
  (`GEMINI_API_KEY`, default `gemini-flash-lite-latest`) → Anthropic Claude
  (`ANTHROPIC_API_KEY`) → OpenAI (`OPENAI_API_KEY`) → offline extractive
  answers (quotes chunks). A provider timeout/error falls through to the next.
- **Embeddings:** OpenAI when keyed, otherwise a clearly-labelled local hash
  embedder for offline development/tests (lexical, weaker than real embeddings).
- **SQL Server:** external and not invented. `backend/app/database/sqlserver.py`
  is the integration boundary; until its real schema/credentials are supplied,
  structured lookups return `None` and answers come from guideline chunks only.
  Sessions use a local SQLite store with configurable retention.

## Quick start (Windows, local dev)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item .env.example .env   # add ANTHROPIC_API_KEY (and/or OPENAI_API_KEY)

# 1) Ingest + index the categorized PDFs (pending review unless --approve)
.\.venv\Scripts\python.exe scripts\ingest.py --dir "D:\Randyll\Randyll_Data" --approve --index

# 2) API
$env:PYTHONPATH="backend"; .\.venv\Scripts\python.exe -m uvicorn app.api.main:app --port 8000

# 3) Frontend (second terminal)
cd frontend; npm install; npm run dev   # http://localhost:3000  (admin: /admin)
```

## Run without Docker (Windows, recommended for local dev)

No Docker or Qdrant server needed — with `QDRANT_URL` empty the backend uses
its built-in local vector store with identical filtering semantics:

```powershell
.\scripts\run-local.ps1          # backend :8000 + frontend :3000, logs in .local-run\
.\scripts\run-local.ps1 -Stop
```

Prefer a real Qdrant without Docker? Either download the standalone Qdrant
Windows binary from its GitHub releases and run `qdrant.exe`, or create a free
Qdrant Cloud cluster — then set `QDRANT_URL` (and `QDRANT_API_KEY` for Cloud)
in `.env`. Nothing else changes.

## Docker (optional)

Start Docker Desktop first, then:

```powershell
$env:KNOWLEDGE_HOST_DIR="D:\Randyll\Randyll_Data"
docker compose up --build   # qdrant :6333, backend :8000, frontend :3000
```

## API

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /api/health` | – | store/LLM/SQL-Server configuration status |
| `GET /api/universities` | – | universities present in approved knowledge |
| `POST /api/chat/sessions`, `GET /api/chat/sessions/{id}` | – | conversation sessions |
| `POST /api/chat/messages` | rate-limited | grounded answer + sources + follow-ups |
| `POST /api/chat/feedback` | – | helpful / not helpful |
| `POST /api/admin/knowledge/ingest` · `/upload` · `/reindex` | `x-admin-key` | ingestion pipeline |
| `GET /api/admin/knowledge/status` · `/documents/{id}/chunks` | `x-admin-key` | review queue, chunk-vs-source inspection, retrieval failures |
| `POST /api/admin/knowledge/documents/{id}/review` | `x-admin-key` | approve / reject (only approved content is student-visible) |

## Tests & evaluation

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
.\.venv\Scripts\python.exe scripts\evaluate.py --university gachon-university
```

Tests are deterministic and offline (conftest clears all API keys): metadata
parsing, chunking, cached/mocked embeddings, mocked Claude responses, Qdrant
filter semantics, wrong-university / wrong-intake adversarial cases, session
context priority, rate limiting and admin authorization.

## Verified example (one university, 12 PDFs)

Ingesting `D:\Randyll\Randyll_Data` processed **36 documents / 149 chunks**
across Gachon, Hannam (Graduate) and Yeungnam; all parsed headers matched
their filenames, Yeungnam was flagged `missing degree_level` for admin review
instead of being guessed. Live answers verified over HTTP, e.g. Gachon tuition
“Engineering KRW 5,718,800 per semester” cited to UNI-08 (original guideline
p.12), a 2028-Fall question correctly falling back to a counsellor, and a
Hannam question never answered from Gachon sources.

## Security

Secrets live only in `.env` (git-ignored) / environment variables; keys are
never sent to the frontend or logged. Admin APIs require `x-admin-key`, chat
is rate-limited, uploads are size/type/magic-byte validated, and retrieved
PDF text is treated as data, never as instructions.
