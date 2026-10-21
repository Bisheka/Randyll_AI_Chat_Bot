"""Run the evaluation dataset (backend/tests/evaluation_questions.json) against the
indexed knowledge base, one university at a time. Usage:
  .\.venv\Scripts\python.exe scripts\evaluate.py [--university gachon-university]"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.agent.service import Agent
from app.embeddings.provider import get_provider
from app.retrieval.store import get_store
from app.ingestion.pipeline import load_store
from app.services import session_store as sessions

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--university", default=None); a = ap.parse_args()
    docs = load_store()["documents"].values(); seen = {}
    for d in docs:
        if d.get("university_name"): seen[d["university_id"]] = d["university_name"]
    unis = [{"university_id": k, "university_name": v} for k, v in sorted(seen.items())]
    if a.university: unis = [u for u in unis if u["university_id"] == a.university]
    agent = Agent(get_store(), get_provider(), unis)
    questions = json.loads((Path(__file__).resolve().parents[1] / "backend" / "tests" /
                            "evaluation_questions.json").read_text(encoding="utf-8"))
    for u in unis:
        s, passed = sessions.create(u["university_id"]), 0
        for item in questions:
            r = agent.answer(s, item["q"].format(uni=u["university_name"]), u["university_id"])
            if item.get("expect") == "fallback":
                good = r["needs_counsellor"] and not r["sources"]
            elif item.get("expect") == "no_misattribution":
                good = all(x.university_name == u["university_name"] for x in r["sources"])
            else:
                good = any(e.lower() in r["answer"].lower() for e in item.get("expect_any", []))
            passed += good
            print(f"{item['category']:>14} {'PASS' if good else 'MISS'}  src={[x.category_code for x in r['sources'][:2]]}")
        print(f"{u['university_name']}: {passed}/{len(questions)}")
