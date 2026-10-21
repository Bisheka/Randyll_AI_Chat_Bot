import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

try:  # local secrets live in the repo-root .env (git-ignored, never committed)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

def _b(v, d=False):
    return os.getenv(v, str(d)).lower() in ("1", "true", "yes") if v in os.environ else d

class Settings:
    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    openai_chat_model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
    gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

    @property
    def llm_provider(self) -> str:
        if self.gemini_api_key: return "gemini"
        if self.anthropic_api_key: return "anthropic"
        return "openai" if self.openai_api_key else "extractive"

    @property
    def llm_model(self) -> str:
        return {"gemini": self.gemini_model, "anthropic": self.anthropic_model}.get(
            self.llm_provider, self.openai_chat_model)
    openai_embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    qdrant_url = os.getenv("QDRANT_URL", "")            # empty -> local vector store
    qdrant_api_key = os.getenv("QDRANT_API_KEY", "")
    collection = os.getenv("QDRANT_COLLECTION", "randyll_university_knowledge")
    data_dir = Path(os.getenv("RANDYLL_DATA_DIR", str(ROOT / "backend" / "data")))
    knowledge_dir = os.getenv("KNOWLEDGE_DIR", str(ROOT / "university_knowledge"))
    admin_api_key = os.getenv("ADMIN_API_KEY", "dev-admin-key-change-me")
    chat_rate_limit = int(os.getenv("CHAT_RATE_LIMIT_PER_MIN", "30"))
    session_retention_days = int(os.getenv("SESSION_RETENTION_DAYS", "30"))
    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "25"))
    fallback_message = os.getenv("FALLBACK_MESSAGE",
        "I couldn't verify that information from the university guidelines currently "
        "available. Please contact a Randyll Overseas counsellor for confirmation.")
    sqlserver_dsn = os.getenv("SQLSERVER_DSN", "")      # external, never invented
    enable_ocr = _b("ENABLE_OCR", False)

settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
