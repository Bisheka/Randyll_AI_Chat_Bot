"""Usage (Windows):
  .\.venv\Scripts\python.exe scripts\ingest.py --dir "D:\Randyll\Randyll_Data" [--approve] [--index]
--approve marks extracted chunks approved (admin review step); without it they stay
pending_review and are invisible to the student chatbot."""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.ingestion.pipeline import ingest_directory, load_store
from app.models.schemas import Chunk

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--index", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-chunk even if the PDF hash is unchanged")
    a = ap.parse_args()
    report = ingest_directory(a.dir, approve=a.approve, force=a.force)
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in report.items()}, indent=1))
    for d in report["processed"]:
        print(f"{d['document_id']}  {d['category_code']}  chunks={d['chunk_count']}  status={d['status']}  needs_review={d['needs_review']} {d['review_reasons']}")
    if report["errors"]: print("ERRORS:", report["errors"])
    if a.index:
        from app.embeddings.provider import get_provider
        from app.retrieval.store import get_store, index_approved
        chunks = [Chunk(**c) for c in load_store()["chunks"].values()]
        print("indexed approved chunks:", index_approved(get_store(), get_provider(), chunks))
