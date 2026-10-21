import shutil
from pathlib import Path
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from ..config import settings
from ..models.schemas import (ChatMessageIn, ChatMessageOut, CreateSession, FeedbackIn, IngestIn, ReviewIn)
from ..ingestion.pipeline import ingest_directory, load_store, set_review
from ..embeddings.provider import get_provider
from ..retrieval.store import get_store, index_approved
from ..agent.service import Agent
from ..security.auth import require_admin, rate_limit, sanitize
from ..services import session_store as sessions

app = FastAPI(title="Randyll Overseas AI Counselling Agent", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])

_provider, _store = get_provider(), get_store()

def _universities():
    docs = load_store()["documents"].values()
    seen = {}
    for d in docs:
        if d.get("university_name"): seen[d["university_id"]] = d["university_name"]
    return [{"university_id": k, "university_name": v} for k, v in sorted(seen.items())]

def _agent(): return Agent(_store, _provider, _universities())

def _reindex():
    from ..models.schemas import Chunk
    chunks = [Chunk(**c) for c in load_store()["chunks"].values()]
    return index_approved(_store, _provider, chunks)

@app.get("/api/health")
def health():
    return {"status": "ok", "vector_store": _store.name, "embedding_model": _provider.model,
            "collection": settings.collection, "indexed_points": _store.count(),
            "llm_configured": settings.llm_provider != "extractive", "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
            "llm_fallbacks": [p for p, k in (("gemini", settings.gemini_api_key),
                                             ("anthropic", settings.anthropic_api_key),
                                             ("openai", settings.openai_api_key)) if k],
            "sqlserver_configured": bool(settings.sqlserver_dsn)}

@app.get("/api/universities")
def universities(): return {"universities": _universities()}

@app.post("/api/chat/sessions")
def create_session(body: CreateSession):
    return sessions.create(body.university_id)

@app.get("/api/chat/sessions/{sid}")
def get_session(sid: str):
    s = sessions.get(sid)
    if not s: raise HTTPException(404, "Session not found")
    return s

@app.post("/api/chat/messages", response_model=ChatMessageOut)
def chat(body: ChatMessageIn, request: Request):
    rate_limit(request.client.host if request.client else "anon")
    s = sessions.get(body.session_id)
    if not s: raise HTTPException(404, "Session not found — create one first")
    q = sanitize(body.message)
    sessions.add_message(body.session_id, "user", q)
    r = _agent().answer(s, q, body.university_id)
    sessions.add_message(body.session_id, "assistant", r["answer"], [x.model_dump() for x in r["sources"]])
    return ChatMessageOut(session_id=body.session_id, **r)

@app.post("/api/chat/feedback")
def feedback(body: FeedbackIn):
    if not sessions.get(body.session_id): raise HTTPException(404, "Session not found")
    sessions.add_feedback(body.session_id, body.helpful, body.comment); return {"ok": True}

# ---------------- Admin (API-key protected) ----------------
@app.post("/api/admin/knowledge/ingest", dependencies=[Depends(require_admin)])
def admin_ingest(body: IngestIn):
    report = ingest_directory(body.directory or settings.knowledge_dir, approve=body.approve)
    return {**report, "indexed": _reindex()}

@app.post("/api/admin/knowledge/upload", dependencies=[Depends(require_admin)])
async def admin_upload(file: UploadFile = File(...), approve: bool = False):
    if not file.filename.lower().endswith(".pdf"): raise HTTPException(400, "Only PDF uploads are accepted")
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024: raise HTTPException(413, "File too large")
    if not data.startswith(b"%PDF"): raise HTTPException(400, "File is not a valid PDF")
    dest = settings.data_dir / "uploads"; dest.mkdir(exist_ok=True)
    p = dest / Path(file.filename).name; p.write_bytes(data)
    return ingest_directory(str(dest), approve=approve) | {"indexed": _reindex()}

@app.get("/api/admin/knowledge/status", dependencies=[Depends(require_admin)])
def admin_status():
    s = load_store()
    return {"documents": list(s["documents"].values()), "chunk_count": len(s["chunks"]),
            "indexed_points": _store.count(), "retrieval_failures": sessions.list_failures()}

@app.get("/api/admin/knowledge/documents/{did}/chunks", dependencies=[Depends(require_admin)])
def admin_chunks(did: str):
    return {"chunks": [c for c in load_store()["chunks"].values() if c["document_id"] == did]}

@app.post("/api/admin/knowledge/documents/{did}/review", dependencies=[Depends(require_admin)])
def admin_review(did: str, body: ReviewIn):
    if body.status not in ("approved", "rejected"): raise HTTPException(400, "status must be approved|rejected")
    doc = set_review(did, body.status)
    if not doc: raise HTTPException(404, "Document not found")
    if body.status == "rejected": _store.delete_document(did)
    return {**doc, "indexed": _reindex()}

@app.post("/api/admin/knowledge/reindex", dependencies=[Depends(require_admin)])
def admin_reindex(): return {"indexed": _reindex()}
