import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf, pytest
from fastapi.testclient import TestClient
from app.ingestion import metadata as md
from app.ingestion.chunking import chunk_page
from app.ingestion.pipeline import ingest_directory, load_store
from app.embeddings.provider import HashEmbeddings, embed_cached
from app.retrieval.store import LocalVectorStore
from app.models.schemas import Chunk

def make_pdf(tmp_path, uni="Test University", status="EXTRACTED_PENDING_REVIEW"):
    d = tmp_path / "2027-Spring-Test"; d.mkdir()
    p = d / "UNI-08_Fees-and-Financial-Requirements.pdf"
    doc = pymupdf.open(); page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(40, 40, 550, 760),
        f"University\n{uni}\nGuideline\n2027 Spring Semester Undergraduate Admission Guideline\n"
        "Academic year / semester\n2027 / SPRING\nCategory\nUNI-08 - Fees & Financial Requirements\n"
        "Source pages (original PDF)\n10, 12\nSource file\norig.pdf\nStatus\n" + status + "\n"
        "1. Application fee\nApplication fee is KRW 150,000 and must be paid before the deadline. "
        "The application is not accepted unless the application fee is paid in full.\n"
        "2. Tuition\nEngineering tuition is KRW 5,718,800 per semester for the stated academic year.")
    doc.save(p); return p

def test_metadata_from_header_not_guessed(tmp_path):
    p = make_pdf(tmp_path)
    m = md.parse(pymupdf.open(p)[0].get_text(), p)
    assert m["university_name"] == "Test University" and m["category_code"] == "UNI-08"
    assert m["academic_year"] == 2027 and m["semester"] == "SPRING" and m["degree_level"] == "undergraduate"
    assert not m["needs_review"]
    m2 = md.parse("no header here", p)
    assert m2["needs_review"] and "missing university_name" in m2["review_reasons"]

def test_metadata_alternate_knu_header_layout(tmp_path):
    text = ("UNI-01   University Information\nKongju National University - 2027 Spring Graduate Admission\n"
            "University\nKongju National University\nSource guide\n2027 Spring Semester Graduate School "
            "Admission Guide for International Students\nIntake\n2027 Spring - Graduate (Master's / Doctoral)\n"
            "Category\nUNI-01 - University Information\n")
    p = tmp_path / "KNU_2027S_Grad_UNI-01_University_Information.pdf"
    m = md.parse(text, p)
    assert m["university_name"] == "Kongju National University" and m["category_code"] == "UNI-01"
    assert m["academic_year"] == 2027 and m["semester"] == "SPRING" and m["degree_level"] == "graduate"
    assert not m["needs_review"]

def test_chunking_keeps_heading_with_body():
    chunks = chunk_page("1. Fees\nApplication fee KRW 150,000 must be paid. " + "x " * 60 +
                        "\n2. Tuition\nEngineering KRW 5,718,800 per semester. " + "y " * 60)
    assert any("Application fee" in b and "1. Fees" in b for _, b in chunks)

def test_embeddings_mocked_and_cached():
    v = embed_cached(HashEmbeddings(), ["tuition fee", "tuition fee"])
    assert len(v) == 2 and len(v[0]) == 384 and v[0] == v[1]

def chunk(cid, uni, cat, text, status="approved"):
    return Chunk(chunk_id=cid, document_id="d1", document_version="v1", university_id=uni,
                 university_name=uni, category_code=cat, source_pdf="x.pdf", source_page=1,
                 content=text, verification_status=status)

def test_metadata_filter_prevents_wrong_university():
    s = LocalVectorStore(); s.points = {}
    cs = [chunk("a", "gachon", "UNI-08", "tuition KRW 100"), chunk("b", "hannam", "UNI-08", "tuition KRW 999")]
    vecs = HashEmbeddings().embed([c.content for c in cs]); s.upsert(cs, vecs)
    hits = s.search(vecs[0], {"university_id": "gachon", "verification_status": "approved"}, limit=5)
    assert [h["chunk_id"] for h in hits] == ["a"]
    pending = [chunk("c", "gachon", "UNI-08", "secret pending", status="pending_review")]
    s.upsert(pending, HashEmbeddings().embed([pending[0].content]))
    assert not s.search(vecs[0], {"verification_status": "approved", "university_id": "gachon"}, limit=5)[0]["chunk_id"] == "c"

def test_ingest_idempotent_and_pending_by_default(tmp_path):
    make_pdf(tmp_path)
    r1 = ingest_directory(str(tmp_path)); r2 = ingest_directory(str(tmp_path))
    assert r1["total_chunks"] >= 1 and r2["skipped_unchanged"] and not r2["processed"]
    assert any("5,718,800" in c["content"] for c in load_store()["chunks"].values())
    assert all(c["verification_status"] == "pending_review" for c in load_store()["chunks"].values())

def test_api_grounding_fallback_and_admin_auth(tmp_path):
    make_pdf(tmp_path)
    ingest_directory(str(tmp_path), approve=True)
    from app.api.main import app, _reindex
    _reindex(); c = TestClient(app)
    assert c.get("/api/health").json()["status"] == "ok"
    assert c.get("/api/admin/knowledge/status").status_code == 401
    sid = c.post("/api/chat/sessions", json={}).json()["id"]
    # no university named -> clarification, not a fabricated answer
    r = c.post("/api/chat/messages", json={"session_id": sid, "message": "How much is the tuition?"}).json()
    assert r["missing_information"] == ["university"] or r["needs_counsellor"]
    r = c.post("/api/chat/messages", json={"session_id": sid, "message": "What is the application fee at Test University?"}).json()
    assert "150,000" in r["answer"] and r["sources"] and r["sources"][0]["source_pdf"].startswith("UNI-08")
    r = c.post("/api/chat/messages", json={"session_id": sid, "message": "What is the TOPIK requirement for a PhD in astrophysics?"}).json()
    assert r["needs_counsellor"] or "couldn't verify" in r["answer"]
