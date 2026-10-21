import time
from collections import defaultdict, deque
from fastapi import Header, HTTPException
from ..config import settings

def require_admin(x_admin_key: str = Header(default="")):
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(401, "Admin authentication required")
    return True

_hits: dict[str, deque] = defaultdict(deque)

def rate_limit(key: str):
    now, q = time.time(), _hits[key]
    while q and q[0] < now - 60: q.popleft()
    if len(q) >= settings.chat_rate_limit:
        raise HTTPException(429, "Too many requests, please wait a moment.")
    q.append(now)

def sanitize(text: str) -> str:
    return " ".join((text or "").replace("\x00", " ").split())[:4000]
