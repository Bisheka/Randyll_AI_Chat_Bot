"""Idempotent ingestion: discover -> hash -> extract (PyMuPDF) -> chunk -> store.
Re-running with an unchanged hash is a no-op; a changed hash supersedes old chunks."""
import json, re
from pathlib import Path
import pymupdf
from ..config import settings
from ..models.schemas import Chunk, DocumentRecord
from . import metadata as md
from .chunking import chunk_page

STORE = settings.data_dir / "knowledge_store.json"

def _load() -> dict:
    return json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {"documents": {}, "chunks": {}}

def _save(s: dict):
    STORE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")

def load_store() -> dict:
    return _load()

def extract_pages(path: Path) -> list[str]:
    doc = pymupdf.open(path)
    pages = []
    for page in doc:
        text = page.get_text() or ""
        for t in page.find_tables().tables:  # keep tables intact as one block
            rows = [" | ".join((c or "").replace("\n", " ") for c in r) for r in t.extract()]
            block = "\n".join(r for r in rows if r.strip(" |"))
            if block and block.split(" | ")[0].strip() not in text:
                text += "\n[TABLE]\n" + block
        pages.append(text)
    return pages

def ingest_directory(directory: str, approve: bool = False, force: bool = False) -> dict:
    root = Path(directory)
    store, report = _load(), {"directory": str(root), "processed": [], "skipped_unchanged": [],
                              "needs_review": [], "errors": [], "total_chunks": 0}
    pdfs = sorted(root.rglob("*.pdf")) if root.exists() else []
    if not pdfs:
        report["errors"].append(f"No PDFs found under {root}")
    for path in pdfs:
        try:
            sha, did = md.sha256_of(path), None
            did = md.doc_id(path, sha)
            prev = store["documents"].get(did)
            if prev and prev["sha256"] == sha and not force:
                report["skipped_unchanged"].append(did)
                if approve and prev.get("status") != "approved":  # approval of an unchanged doc still applies
                    prev["status"] = "approved"
                    for c in store["chunks"].values():
                        if c["document_id"] == did: c["verification_status"] = "approved"
                    _save(store)
                continue
            pages = extract_pages(path)
            full = "\n".join(pages)
            meta = md.parse(full, path)
            if len(full.strip()) < 100:
                raise ValueError("Unreadable/empty text layer (OCR disabled)")
            status = "approved" if approve else "pending_review"
            chunks, version = [], sha[:12]
            for pno, ptext in enumerate(pages, 1):
                # drop the repeated running header line of the categorized PDFs
                body = re.sub(r"^.*UNI-\d{2}.*Source pages:.*\nPage \d+\n", "", ptext, flags=re.M)
                if pno == 1:
                    # Drop the provenance header block from chunk *content* (it is kept
                    # in metadata); otherwise every p.1 chunk leads with boilerplate
                    # instead of the actual fees/requirements.
                    body = re.sub(r"^.*?Status\s*\n\S+\s*\n", "", body, flags=re.S)
                for i, (head, body_text) in enumerate(chunk_page(body)):
                    if "Status\nEXTRACTED" in body_text and pno == 1 and i == 0:
                        pass  # header block kept: it carries university/guideline provenance
                    chunks.append(Chunk(
                        chunk_id=f"{did}::p{pno}::{i}", document_id=did, document_version=version,
                        university_id=meta["university_id"], university_name=meta["university_name"] or path.parent.name,
                        academic_year=meta["academic_year"], semester=meta["semester"],
                        admission_type=meta["admission_type"], degree_level=meta["degree_level"],
                        category_code=meta["category_code"] or "UNKNOWN", category_name=meta["category_name"],
                        source_pdf=path.name, source_page=pno, original_source_pages=meta["original_source_pages"],
                        content=body_text, heading=head, verification_status=status,
                        needs_review=meta["needs_review"], review_reasons=meta["review_reasons"]))
            for cid in [c for c, v in store["chunks"].items() if v["document_id"] == did]:
                del store["chunks"][cid]  # supersede old version
            for c in chunks:
                store["chunks"][c.chunk_id] = c.model_dump()
            rec = DocumentRecord(document_id=did, document_version=version, sha256=sha, source_pdf=path.name,
                university_id=meta["university_id"], university_name=meta["university_name"],
                category_code=meta["category_code"], pages=len(pages), chunk_count=len(chunks), status=status,
                needs_review=meta["needs_review"], review_reasons=meta["review_reasons"])
            store["documents"][did] = rec.model_dump()
            report["processed"].append(rec.model_dump()); report["total_chunks"] += len(chunks)
            if meta["needs_review"]: report["needs_review"].append({"document_id": did, "reasons": meta["review_reasons"]})
        except Exception as e:  # flag, never abort the whole run
            report["errors"].append({"file": str(path), "error": str(e)})
    _save(store)
    (settings.data_dir / "last_ingestion_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report

def set_review(document_id: str, status: str) -> dict | None:
    store = _load(); doc = store["documents"].get(document_id)
    if not doc: return None
    doc["status"] = status
    for c in store["chunks"].values():
        if c["document_id"] == document_id: c["verification_status"] = status
    _save(store); return doc
