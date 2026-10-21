"""OpenAI embeddings when a key is configured; deterministic local hash embeddings
otherwise (dev/tests only — same interface, clearly named model). Cached by content hash."""
import hashlib, json, math, re, time
from ..config import settings

CACHE = settings.data_dir / "embedding_cache.json"

def _cache() -> dict:
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

class HashEmbeddings:  # offline fallback, NOT a semantic model
    model, dim = "local-hash-384", 384
    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dim
            for tok in re.findall(r"[a-z0-9₩$%]+", t.lower()):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                v[h % self.dim] += 1.0; v[(h >> 8) % self.dim] += 0.5
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out

class OpenAIEmbeddings:
    def __init__(self):
        from openai import OpenAI
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model, self.dim = settings.openai_embedding_model, 1536
    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for i in range(0, len(texts), 64):  # batched
            batch, err = texts[i:i + 64], None
            for attempt in range(4):
                try:
                    r = self.client.embeddings.create(model=self.model, input=batch)
                    out.extend(d.embedding for d in r.data); err = None; break
                except Exception as e:  # rate-limit / transient backoff, key never logged
                    err = e; time.sleep(2 ** attempt)
            if err: raise RuntimeError(f"embedding request failed after retries: {type(err).__name__}")
        return out

def get_provider():
    return OpenAIEmbeddings() if settings.openai_api_key else HashEmbeddings()

def embed_cached(provider, texts: list[str]) -> list[list[float]]:
    cache, todo, todo_idx = _cache(), [], []
    result: list = [None] * len(texts)
    for i, t in enumerate(texts):
        k = hashlib.sha256((provider.model + "|" + t).encode()).hexdigest()
        if k in cache: result[i] = cache[k]
        else: todo.append(t); todo_idx.append((i, k))
    if todo:
        for (i, k), v in zip(todo_idx, provider.embed(todo)):
            result[i] = cache[k] = v
        CACHE.write_text(json.dumps(cache), encoding="utf-8")
    return result
