"""
短链接映射数据库 - SQLite

设计：存储 sku_id 到推广链接的映射，支持高并发查询
"""
import json
import time
import aiosqlite
from pathlib import Path
from typing import Optional


class ShortLinkDatabase:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path or "./jd_saver.db")
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        if self._conn is None:
            self._conn = await aiosqlite.connect(str(self.db_path))
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA synchronous=NORMAL")
            await self._create_tables()

    async def _create_tables(self):
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS short_links (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id        TEXT    NOT NULL UNIQUE,
                promo_link    TEXT    NOT NULL,
                original_url  TEXT    NOT NULL,
                click_count   INTEGER DEFAULT 0,
                created_at    INTEGER NOT NULL,
                updated_at    INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_short_links_sku
                ON short_links(sku_id);
        """)
        await self._conn.commit()

    async def save_short_link(
        self,
        sku_id: str,
        promo_link: str,
        original_url: str,
    ) -> int:
        """保存或更新短链接映射"""
        now = int(time.time())
        await self._conn.execute(
            """
            INSERT INTO short_links (sku_id, promo_link, original_url, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(sku_id) DO UPDATE SET
                promo_link   = excluded.promo_link,
                original_url = excluded.original_url,
                updated_at   = excluded.updated_at
            """,
            (sku_id, promo_link, original_url, now, now),
        )
        await self._conn.commit()
        return now

    async def get_promo_link(self, sku_id: str) -> Optional[str]:
        """查询推广链接"""
        cursor = await self._conn.execute(
            "SELECT promo_link FROM short_links WHERE sku_id = ?",
            (sku_id,),
        )
        row = await cursor.fetchone()
        return row["promo_link"] if row else None

    async def get_original_url(self, sku_id: str) -> Optional[str]:
        """查询原始京东链接"""
        cursor = await self._conn.execute(
            "SELECT original_url FROM short_links WHERE sku_id = ?",
            (sku_id,),
        )
        row = await cursor.fetchone()
        return row["original_url"] if row else None

    async def increment_click(self, sku_id: str):
        """增加点击计数"""
        await self._conn.execute(
            "UPDATE short_links SET click_count = click_count + 1, updated_at = ? WHERE sku_id = ?",
            (int(time.time()), sku_id),
        )
        await self._conn.commit()

    async def get_stats(self, sku_id: str) -> Optional[dict]:
        """获取链接统计"""
        cursor = await self._conn.execute(
            "SELECT sku_id, promo_link, click_count, created_at FROM short_links WHERE sku_id = ?",
            (sku_id,),
        )
        row = await cursor.fetchone()
        if row:
            return {
                "sku_id": row["sku_id"],
                "promo_link": row["promo_link"],
                "click_count": row["click_count"],
                "created_at": row["created_at"],
            }
        return None

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None
