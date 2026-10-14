"""轻量安全防护：API Token 鉴权 + 每客户端滑动窗口限流（无第三方依赖）。"""

import time
from collections import deque
from threading import Lock

from fastapi import HTTPException, Request

from .config import AppSettings


class SlidingWindowRateLimiter:
    """按客户端 IP 的滑动窗口限流器。limit <= 0 表示不限流。"""

    def __init__(self, limit: int, window_seconds: int = 60, max_clients: int = 1024):
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._hits: dict[str, deque] = {}
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        if self.limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                if len(self._hits) >= self.max_clients:
                    # 淘汰整窗无请求的客户端，避免内存无限增长
                    stale = [
                        k
                        for k, q in self._hits.items()
                        if not q or now - q[-1] > self.window_seconds
                    ]
                    for k in stale:
                        del self._hits[k]
                hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > self.window_seconds:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True


_limiter: SlidingWindowRateLimiter | None = None


def _get_limiter() -> SlidingWindowRateLimiter:
    global _limiter
    if _limiter is None:
        settings = AppSettings()
        _limiter = SlidingWindowRateLimiter(limit=settings.rate_limit_per_minute)
    return _limiter


async def require_auth(request: Request) -> None:
    """鉴权 + 限流依赖：未配置 AUTH_TOKEN 时仅限流，配置后要求 Bearer Token。"""
    settings = AppSettings()
    if settings.api_token:
        header = request.headers.get("authorization", "")
        if header.startswith("Bearer "):
            provided = header[len("Bearer "):].strip()
        else:
            provided = header.strip()
        if provided != settings.api_token:
            raise HTTPException(status_code=401, detail="无效或缺失的 API Token")
    key = request.client.host if request.client else "unknown"
    if not _get_limiter().allow(key):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
