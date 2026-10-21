"""Lightweight local session store (SQLite). Only necessary fields; retention-pruned.
Swap for SQL Server operational tables once its schema/credentials are supplied."""
import json, sqlite3, uuid
from datetime import datetime, timedelta, timezone
from ..config import settings

DB = settings.data_dir / "sessions.db"

def _db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, created TEXT, updated TEXT,
                 university_id TEXT, degree_level TEXT, intake TEXT, program TEXT, context TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,
                 session_id TEXT, role TEXT, content TEXT, sources TEXT, created TEXT)""")
    c.execute("CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, helpful INT, comment TEXT, created TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS retrieval_failures(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, query TEXT, reason TEXT, created TEXT)")
    return c

def _now(): return datetime.now(timezone.utc).isoformat()

def create(university_id=None) -> dict:
    sid, c = uuid.uuid4().hex, _db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=settings.session_retention_days)).isoformat()
    c.execute("DELETE FROM sessions WHERE updated < ?", (cutoff,))
    c.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)", (sid, _now(), _now(), university_id, None, None, None, "{}"))
    c.commit(); return get(sid)

def get(sid: str) -> dict | None:
    c = _db(); r = c.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not r: return None
    msgs = c.execute("SELECT role,content,sources FROM messages WHERE session_id=? ORDER BY id", (sid,)).fetchall()
    d = dict(r); d["context"] = json.loads(d["context"] or "{}")
    d["messages"] = [{"role": m["role"], "content": m["content"],
                      "sources": json.loads(m["sources"] or "[]")} for m in msgs]
    return d

def update_context(sid: str, **kw):
    c = _db(); s = get(sid)
    if not s: return
    ctx = {**s["context"], **{k: v for k, v in kw.pop("context", {}).items()}}
    cols = {k: kw.get(k, s[k]) for k in ("university_id", "degree_level", "intake", "program")}
    c.execute("UPDATE sessions SET updated=?,university_id=?,degree_level=?,intake=?,program=?,context=? WHERE id=?",
              (_now(), cols["university_id"], cols["degree_level"], cols["intake"], cols["program"], json.dumps(ctx), sid))
    c.commit()

def add_message(sid: str, role: str, content: str, sources=None):
    c = _db(); c.execute("INSERT INTO messages(session_id,role,content,sources,created) VALUES (?,?,?,?,?)",
                         (sid, role, content, json.dumps(sources or [], ensure_ascii=False), _now())); c.commit()

def add_feedback(sid, helpful, comment):
    c = _db(); c.execute("INSERT INTO feedback VALUES (NULL,?,?,?,?)", (sid, int(helpful), comment, _now())); c.commit()

def log_failure(sid, query, reason):
    c = _db(); c.execute("INSERT INTO retrieval_failures VALUES (NULL,?,?,?,?)", (sid, query[:500], reason, _now())); c.commit()

def list_failures(limit=50):
    c = _db(); return [dict(r) for r in c.execute("SELECT * FROM retrieval_failures ORDER BY id DESC LIMIT ?", (limit,))]
