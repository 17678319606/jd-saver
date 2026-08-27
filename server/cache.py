"""
内存 TTL 缓存 - 减少重复 API 调用，降低京东联盟限流风险

策略：按 (method, params) 哈希缓存，5分钟过期
不依赖 Redis，零外部依赖，适合轻量部署
"""
import time
import hashlib
from typing import Any, Dict, Optional


class Cache:
    def __init__(self, default_ttl: int = 300):
        self.default_ttl = default_ttl
        self._store: Dict[str, tuple] = {}  # key -> (value, expires_at)

    def _key(self, method: str, params: dict) -> str:
        raw = f"{method}:{hashlib.md5(str(sorted(params.items())).encode()).hexdigest()}"
        return raw[:20]

    def get(self, method: str, params: dict) -> Optional[Any]:
        k = self._key(method, params)
        entry = self._store.get(k)
        if entry and entry[1] > time.time():
            return entry[0]
        self._store.pop(k, None)
        return None

    def set(self, method: str, params: dict, value: Any, ttl: int = 300) -> None:
        k = self._key(method, params)
        self._store[k] = (value, time.time() + ttl)

    def invalidate_sku(self, sku_id: str) -> int:
        """清除所有包含该 sku_id 的缓存条目"""
        keys = [k for k, (v, _) in self._store.items() if sku_id in str(v)]
        for k in keys:
            del self._store[k]
        return len(keys)

    def clear_expired(self) -> int:
        now = time.time()
        keys = [k for k, (_, exp) in self._store.items() if exp <= now]
        for k in keys:
            del self._store[k]
        return len(keys)


# 全局缓存实例（单例）
cache = Cache(default_ttl=300)
