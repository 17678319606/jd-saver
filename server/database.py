"""
价格追踪数据库 - SQLite（轻量，适合几十万用户规模）

设计原则：
- SQLite WAL 模式：高并发读，不锁写
- 单文件，零运维，自动备份方便
- 不依赖外部 MySQL/Redis，除非需要集群
- 可选接 Redis 做热点缓存层
"""
import json
import time
import aiosqlite
from pathlib import Path
from typing import List, Optional


class PriceDatabase:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path or "./jd_saver.db")
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        if self._conn is None:
            self._conn = await aiosqlite.connect(str(self.db_path))
            self._conn.row_factory = aiosqlite.Row
            # WAL 模式：提升并发读写性能
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA synchronous=NORMAL")
            await self._conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
            await self._create_tables()

    async def _create_tables(self):
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS price_alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT    NOT NULL,
                sku_id      TEXT    NOT NULL,
                target_price REAL  NOT NULL,
                current_price REAL,
                notified    INTEGER DEFAULT 0,
                created_at  INTEGER NOT NULL,
                updated_at  INTEGER NOT NULL,
                UNIQUE(user_id, sku_id)
            );

            CREATE TABLE IF NOT EXISTS price_records (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id      TEXT    NOT NULL,
                price       REAL   NOT NULL,
                recorded_at INTEGER NOT NULL,
                note        TEXT   DEFAULT '',
                created_at  INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_records_sku_time
                ON price_records(sku_id, recorded_at DESC);
            CREATE INDEX IF NOT EXISTS idx_alerts_user
                ON price_alerts(user_id, notified);
            CREATE INDEX IF NOT EXISTS idx_alerts_sku
                ON price_alerts(sku_id, notified);
        """)
        await self._conn.commit()

    # ---- 价格记录 ----

    async def save_price_record(self, sku_id: str, price: float, note: str = "") -> int:
        now = int(time.time())
        await self._conn.execute(
            "INSERT INTO price_records (sku_id, price, recorded_at, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (sku_id, price, now, note, now),
        )
        await self._conn.commit()
        return now

    async def get_price_history(self, sku_id: str, limit: int = 30) -> List[dict]:
        cursor = await self._conn.execute(
            "SELECT price, recorded_at, note FROM price_records "
            "WHERE sku_id = ? ORDER BY recorded_at DESC LIMIT ?",
            (sku_id, limit),
        )
        return [
            {"price": r["price"], "recorded_at": r["recorded_at"], "note": r["note"] or ""}
            for r in await cursor.fetchall()
        ]

    async def get_lowest_price(self, sku_id: str) -> Optional[float]:
        cursor = await self._conn.execute(
            "SELECT MIN(price) FROM price_records WHERE sku_id = ?", (sku_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] is not None else None

    # ---- 降价提醒 ----

    async def add_price_alert(
        self, user_id: str, sku_id: str, target_price: float, current_price: float
    ) -> int:
        now = int(time.time())
        await self._conn.execute(
            """
            INSERT INTO price_alerts (user_id, sku_id, target_price, current_price, notified, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, ?, ?)
            ON CONFLICT(user_id, sku_id) DO UPDATE SET
                target_price   = excluded.target_price,
                updated_at     = excluded.updated_at
            """,
            (user_id, sku_id, target_price, current_price, now, now),
        )
        await self._conn.commit()
        return now

    async def update_alert_price(self, sku_id: str, current_price: float):
        """轮询时更新某 SKU 的当前价格"""
        await self._conn.execute(
            "UPDATE price_alerts SET current_price = ?, updated_at = ? WHERE sku_id = ?",
            (current_price, int(time.time()), sku_id),
        )
        await self._conn.commit()

    async def get_active_alert_skus(self) -> List[str]:
        """获取有待检查的 SKU 列表"""
        cursor = await self._conn.execute(
            "SELECT DISTINCT sku_id FROM price_alerts WHERE notified = 0"
        )
        return [r[0] for r in await cursor.fetchall()]

    async def check_and_get_triggers(self) -> List[tuple]:
        """查出所有已触发的提醒，返回 (user_id, sku_id, current_price, target_price)"""
        cursor = await self._conn.execute(
            """
            SELECT user_id, sku_id, current_price, target_price
            FROM price_alerts
            WHERE notified = 0 AND current_price IS NOT NULL AND current_price <= target_price
            """
        )
        return await cursor.fetchall()

    async def mark_notified(self, user_id: str, sku_id: str):
        await self._conn.execute(
            "UPDATE price_alerts SET notified = 1, updated_at = ? WHERE user_id = ? AND sku_id = ?",
            (int(time.time()), user_id, sku_id),
        )
        await self._conn.commit()

    # ---- 清理 ----

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None
