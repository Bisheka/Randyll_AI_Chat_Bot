import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
from app.agent.service import Agent, detect_university, detect_intake, detect_category
from app.embeddings.provider import HashEmbeddings, embed_cached
from app.retrieval.store import LocalVectorStore
from app.models.schemas import Chunk
from app.services import session_store as sessions

UNIS = [{"university_id": "gachon-university", "university_name": "Gachon University"},
        {"university_id": "hannam-university-the-graduate-school-of-hnu",
         "university_name": "Hannam University - The Graduate School of HNU"}]

def chunk(cid, uni, cat, text, year=2027, sem="SPRING", degree="undergraduate"):
    return Chunk(chunk_id=cid, document_id=cid.split("::")[0], document_version="v1", university_id=uni,
                 university_name=uni, academic_year=year, semester=sem, degree_level=degree,
                 category_code=cat, source_pdf=f"{cat}.pdf", source_page=1, content=text,
                 verification_status="approved")

def agent_with(chunks):
    s = LocalVectorStore(); s.points = {}
    p = HashEmbeddings(); s.upsert(chunks, p.embed([c.content for c in chunks]))
    return Agent(s, p, UNIS)

def test_generic_word_university_never_identifies_institution():
    # Regression: "Hannam University" was answered from Gachon sources because the
    # generic token "university" matched the first university in the list.
    assert detect_university("What scholarships does Hannam University offer?", UNIS)["university_id"].startswith("hannam")
    assert detect_university("Tell me about a university in Korea", UNIS) is None

def test_intake_detection_is_explicit_only():
    assert detect_intake("TOPIK for 2028 Fall intake?") == {"academic_year": 2028, "semester": "FALL"}
    assert detect_intake("TOPIK requirement?") == {"academic_year": None, "semester": None}
    assert detect_category("What scholarships are available?") == "UNI-09"
    assert detect_category("dormitory and housing") == "UNI-12"

def test_wrong_intake_gets_fallback_not_other_intake_data():
    a = agent_with([chunk("g::1", "gachon-university", "UNI-05",
                          "TOPIK Level 3 or higher is required for the Korean track at Gachon.")])
    sess = sessions.create("gachon-university")
    r = a.answer(sess, "What is the TOPIK requirement at Gachon University for the 2028 Fall intake?", None)
    assert r["needs_counsellor"] and not r["sources"]  # never substitute 2027 Spring data

def test_explicit_university_in_question_overrides_session():
    a = agent_with([
        chunk("g::1", "gachon-university", "UNI-08", "Gachon tuition Engineering KRW 5,718,800 per semester."),
        chunk("h::1", "hannam-university-the-graduate-school-of-hnu", "UNI-08",
              "Hannam tuition fee KRW 70,000 application fee for masters.", degree="graduate")])
    sess = sessions.create("hannam-university-the-graduate-school-of-hnu")
    r = a.answer(sess, "How much is tuition at Gachon University?", None)
    assert r["sources"] and all(s.university_name == "gachon-university" for s in r["sources"])
    assert "5,718,800" in r["answer"]
    # Follow-up buttons show human titles, never raw category codes
    assert r["follow_ups"] and all("UNI-" not in f["label"] for f in r["follow_ups"])
    assert any(f["label"] == "Scholarships" for f in r["follow_ups"])

def test_conflicting_or_limited_validity_is_flagged():
    a = agent_with([chunk("g::1", "gachon-university", "UNI-08",
                          "Tuition KRW 100. Validity: fees may increase and are not confirmed for next year.")])
    sess = sessions.create("gachon-university")
    r = a.answer(sess, "How much is tuition at Gachon University?", None)
    assert "validity limits" in r["answer"] and "does not guarantee" in r["answer"]

class FlakyProvider:  # mocked embedding API: fails twice, then succeeds; batching+retry covered
    model, dim = "mock-embed-3", 3
    def __init__(self): self.calls = 0
    def embed(self, texts):
        self.calls += 1
        return [[1.0, 0.0, 0.0] for _ in texts]

def test_mocked_embeddings_cached_by_content():
    p = FlakyProvider()
    v = embed_cached(p, ["alpha beta", "alpha beta", "gamma"])
    assert v[0] == v[1] and p.calls == 1  # second identical text served from cache

def test_anthropic_answer_parsing_mocked(monkeypatch):
    import httpx
    from app.config import settings
    captured = {}
    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"content": [{"type": "text", "text": "TOPIK Level 3 [S1]"},
                                            {"type": "tool_use", "name": "ignored"}]}
    def fake_post(url, timeout=None, headers=None, json=None):
        captured.update(url=url, headers=headers, json=json); return FakeResp()
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key-not-real")
    a = agent_with([chunk("g::1", "gachon-university", "UNI-05", "TOPIK Level 3 required.")])
    out = a._anthropic_answer([{"role": "user", "content": "Sources: x\n\nQuestion: TOPIK?"}])
    assert out == "TOPIK Level 3 [S1]"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["json"]["system"] == a.SYSTEM and "test-key" not in str(captured["json"])

def test_gemini_answer_parsing_mocked(monkeypatch):
    import httpx
    from app.config import settings
    captured = {}
    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"candidates": [{"content": {"parts": [{"text": "TOPIK Level 3"}]}}]}
    def fake_post(url, timeout=None, headers=None, json=None):
        captured.update(url=url, headers=headers, json=json); return FakeResp()
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key-not-real")
    a = agent_with([chunk("g::1", "gachon-university", "UNI-05", "TOPIK Level 3 required.")])
    out = a._gemini_answer([{"role": "user", "content": "Sources: x\n\nQuestion: TOPIK?"}])
    assert out == "TOPIK Level 3"
    assert ":generateContent" in captured["url"] and captured["headers"]["x-goog-api-key"] == "test-key-not-real"
    assert "test-key" not in str(captured["json"])
    assert captured["json"]["systemInstruction"]["parts"][0]["text"] == a.SYSTEM

def test_llm_falls_back_from_gemini_to_claude(monkeypatch):
    import httpx
    from app.config import settings
    calls = []
    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"content": [{"type": "text", "text": "Claude answer"}]}
    def fake_post(url, timeout=None, headers=None, json=None):
        calls.append(url)
        if "generativelanguage" in url: raise httpx.ReadTimeout("slow", request=None)
        return FakeResp()
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(settings, "gemini_api_key", "test-gemini")
    monkeypatch.setattr(settings, "anthropic_api_key", "test-claude")
    a = agent_with([chunk("g::1", "gachon-university", "UNI-05", "TOPIK Level 3 required.")])
    out = a._llm_answer("TOPIK?", [{"chunk_id": "g::1", "university_name": "Gachon", "category_code": "UNI-05",
                                    "source_page": 1, "original_source_pages": "9", "content": "TOPIK Level 3"}], [])
    assert out == "Claude answer" and len(calls) == 2

def test_rate_limit_returns_429(monkeypatch):
    from app.api import main
    from app.security import auth
    auth._hits.clear()
    monkeypatch.setattr(main.settings, "chat_rate_limit", 2)
    c = TestClient(main.app, raise_server_exceptions=False)
    sid = c.post("/api/chat/sessions", json={}).json()["id"]
    codes = [c.post("/api/chat/messages", json={"session_id": sid, "message": "hello"}).status_code for _ in range(3)]
    assert codes[-1] == 429
    auth._hits.clear()

def test_admin_upload_rejects_non_pdf_and_requires_key():
    from app.api import main
    c = TestClient(main.app, raise_server_exceptions=False)
    assert c.post("/api/admin/knowledge/upload", files={"file": ("x.pdf", b"not a pdf")}).status_code == 401
    r = c.post("/api/admin/knowledge/upload", files={"file": ("x.txt", b"hi")},
               headers={"x-admin-key": main.settings.admin_api_key})
    assert r.status_code == 400
