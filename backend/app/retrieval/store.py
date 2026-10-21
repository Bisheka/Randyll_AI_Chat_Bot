"""Vector store interface: Qdrant when QDRANT_URL is set, else a persisted local
store with identical filtering semantics (metadata filters applied BEFORE scoring)."""
import json, math, uuid
from ..config import settings
from ..models.schemas import Chunk
from ..embeddings.provider import embed_cached

FILTER_KEYS = ("university_id", "academic_year", "semester", "degree_level",
               "admission_type", "category_code", "verification_status")

def _match(payload: dict, filters: dict) -> bool:
    return all(payload.get(k) == v for k, v in filters.items() if v is not None)

def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))

class LocalVectorStore:
    name = "local"
    def __init__(self):
        self.path = settings.data_dir / "vector_store.json"
        self.points: dict = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
    def _save(self): self.path.write_text(json.dumps(self.points, ensure_ascii=False), encoding="utf-8")
    def ensure(self, dim: int): pass
    def upsert(self, chunks: list[Chunk], vectors):
        for c, v in zip(chunks, vectors):
            self.points[c.chunk_id] = {"vector": v, "payload": {**c.model_dump(), "content": c.content}}
        self._save()
    def delete_document(self, document_id: str):
        self.points = {k: v for k, v in self.points.items() if v["payload"]["document_id"] != document_id}; self._save()
    def search(self, vector, filters: dict, limit: int = 6):
        hits = [{"score": _cos(vector, p["vector"]), **p["payload"]} for p in self.points.values() if _match(p["payload"], filters)]
        return sorted(hits, key=lambda h: -h["score"])[:limit]
    def count(self): return len(self.points)

class QdrantStore:
    name = "qdrant"
    def __init__(self):
        from qdrant_client import QdrantClient
        self.client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
        self.collection = settings.collection
    def ensure(self, dim: int):
        from qdrant_client.models import Distance, VectorParams, PayloadSchemaType
        cols = [c.name for c in self.client.get_collections().collections]
        if self.collection not in cols:
            self.client.create_collection(self.collection, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))
            for k in FILTER_KEYS:
                try: self.client.create_payload_index(self.collection, k, PayloadSchemaType.KEYWORD)
                except Exception: pass
    def upsert(self, chunks, vectors):
        from qdrant_client.models import PointStruct
        pts = [PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL, c.chunk_id)), vector=v,
                           payload={**c.model_dump(), "content": c.content}) for c, v in zip(chunks, vectors)]
        for i in range(0, len(pts), 128): self.client.upsert(self.collection, pts[i:i + 128])
    def delete_document(self, document_id: str):
        from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector
        self.client.delete(self.collection, points_selector=FilterSelector(filter=Filter(
            must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))])))
    def search(self, vector, filters, limit=6):
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        must = [FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items() if v is not None]
        r = self.client.query_points(self.collection, query=vector, query_filter=Filter(must=must) if must else None, limit=limit)
        return [{"score": p.score, **p.payload} for p in r.points]
    def count(self):
        try: return self.client.count(self.collection).count
        except Exception: return 0

def get_store():
    if settings.qdrant_url:
        try:
            s = QdrantStore(); s.count(); return s
        except Exception:
            pass  # fall back locally rather than failing the API
    return LocalVectorStore()

def index_approved(store, provider, chunks: list[Chunk]) -> int:
    approved = [c for c in chunks if c.verification_status == "approved"]
    if not approved: return 0
    vectors = embed_cached(provider, [c.content for c in approved])
    store.ensure(provider.dim); store.upsert(approved, vectors)
    return len(approved)
