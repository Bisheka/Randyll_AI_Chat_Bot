"""Test isolation: never call the real OpenAI/Qdrant services, never touch the
developer's real data directory or any key present in the shell environment."""
import os, tempfile

os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["QDRANT_URL"] = ""
os.environ["RANDYLL_DATA_DIR"] = tempfile.mkdtemp(prefix="randyll-test-data-")
