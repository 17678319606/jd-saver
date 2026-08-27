"""
京东省钱助手 — 单元测试套件

运行：
    pytest tests/ -v
"""
import asyncio
import os
import tempfile
import time
import pytest
import aiosqlite

from server.jd_config import JDConfig, extract_sku_id, parse_jd_url
from server.database import PriceDatabase
from server.cache import Cache
from server.short_links import ShortLinkDatabase


# ==================== jd_config 测试 ====================

class TestJDConfig:
    def test_extract_sku_id_from_query(self):
        assert extract_sku_id("https://item.jd.com/123456.html?skuId=123456") == "123456"

    def test_extract_sku_id_from_path(self):
        assert extract_sku_id("https://item.jd.com/987654.html") == "987654"

    def test_extract_sku_id_from_item_path(self):
        assert extract_sku_id("https://item.jd.com/item/555555.html") == "555555"

    def test_extract_sku_id_invalid(self):
        assert extract_sku_id("https://taobao.com/x") is None
        assert extract_sku_id("") is None
        assert extract_sku_id("not-a-url") is None

    def test_parse_jd_url_valid(self):
        result = parse_jd_url("https://item.jd.com/123456.html")
        assert result["sku_id"] == "123456"
        assert result["is_jd_url"] is True

    def test_parse_jd_url_invalid(self):
        result = parse_jd_url("https://taobao.com/x")
        assert result["sku_id"] is None
        assert result["is_jd_url"] is False

    def test_jd_config_from_env(self, monkeypatch):
        monkeypatch.setenv("JD_APP_KEY", "test_key")
        monkeypatch.setenv("JD_APP_SECRET", "test_secret")
        monkeypatch.setenv("JD_PID", "test_pid")
        cfg = JDConfig.from_env()
        assert cfg.app_key == "test_key"
        assert cfg.app_secret == "test_secret"
        assert cfg.pid == "test_pid"
        assert cfg.top_url == "https://api.jd.com/routerjson"


# ==================== cache 测试 ====================

class TestCache:
    @pytest.fixture
    def cache(self):
        return Cache(default_ttl=60)

    def test_set_and_get(self, cache):
        cache.set("coupon", "123456", {"price": 99})
        assert cache.get("coupon", "123456") == {"price": 99}

    def test_get_miss(self, cache):
        assert cache.get("coupon", "999999") is None

    def test_ttl_expiration(self, cache):
        cache.set("coupon", "123", {"price": 10}, ttl=0.1)
        time.sleep(0.2)
        assert cache.get("coupon", "123") is None

    def test_invalidate_sku(self, cache):
        cache.set("coupon", "abc", {"sku": "abc"})
        cache.set("coupon", "def", {"sku": "def"})
        removed = cache.invalidate_sku("abc")
        assert removed == 1
        assert cache.get("coupon", "abc") is None
        assert cache.get("coupon", "def") is not None

    def test_clear_expired(self, cache):
        cache.set("a", "1", {"x": 1}, ttl=0.1)
        cache.set("b", "2", {"y": 2}, ttl=60)
        time.sleep(0.2)
        removed = cache.clear_expired()
        assert removed == 1
        assert cache.get("b", "2") is not None


# ==================== database 测试 ====================

@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_jd_saver.db")


@pytest.fixture
async def db(db_path):
    d = PriceDatabase(db_path)
    await d.connect()
    yield d
    await d.close()


class TestPriceDatabase:
    @pytest.mark.asyncio
    async def test_save_and_get_price_record(self, db):
        now = await db.save_price_record("123456", 99.9, "manual")
        assert isinstance(now, int)
        records = await db.get_price_history("123456")
        assert len(records) == 1
        assert records[0]["price"] == 99.9
        assert records[0]["note"] == "manual"

    @pytest.mark.asyncio
    async def test_get_lowest_price(self, db):
        await db.save_price_record("123456", 100.0)
        await db.save_price_record("123456", 80.0)
        await db.save_price_record("123456", 90.0)
        lowest = await db.get_lowest_price("123456")
        assert lowest == 80.0

    @pytest.mark.asyncio
    async def test_add_price_alert(self, db):
        now = await db.add_price_alert("user1", "123456", 80.0, 100.0)
        assert isinstance(now, int)
        skus = await db.get_active_alert_skus()
        assert "123456" in skus

    @pytest.mark.asyncio
    async def test_update_and_trigger_alert(self, db):
        await db.add_price_alert("user1", "123456", 80.0, 100.0)
        await db.update_alert_price("123456", 75.0)
        triggers = await db.check_and_get_triggers()
        assert len(triggers) == 1
        user_id, sku_id, cp, tp = triggers[0]
        assert user_id == "user1"
        assert sku_id == "123456"
        assert cp == 75.0
        assert tp == 80.0

    @pytest.mark.asyncio
    async def test_mark_notified(self, db):
        await db.add_price_alert("user1", "123456", 80.0, 100.0)
        await db.update_alert_price("123456", 75.0)
        await db.mark_notified("user1", "123456")
        triggers = await db.check_and_get_triggers()
        assert len(triggers) == 0

    @pytest.mark.asyncio
    async def test_duplicate_alert_upsert(self, db):
        await db.add_price_alert("user1", "123456", 80.0, 100.0)
        await db.add_price_alert("user1", "123456", 70.0, 90.0)
        skus = await db.get_active_alert_skus()
        assert len(skus) == 1  # 同一 user+sku 只有一条

    @pytest.mark.asyncio
    async def test_get_price_history_limit(self, db):
        for i in range(5):
            await db.save_price_record("123456", float(100 + i))
        records = await db.get_price_history("123456", limit=3)
        assert len(records) == 3

    @pytest.mark.asyncio
    async def test_empty_history(self, db):
        records = await db.get_price_history("999999")
        assert records == []
        lowest = await db.get_lowest_price("999999")
        assert lowest is None


# ==================== short_links 测试 ====================

@pytest.fixture
async def link_db(db_path):
    d = ShortLinkDatabase(db_path)
    await d.connect()
    yield d
    await d.close()


class TestShortLinkDatabase:
    @pytest.mark.asyncio
    async def test_save_and_get(self, link_db):
        await link_db.save_short_link("123456", "https://example.com/go/123456", "https://jd.com/123456")
        promo = await link_db.get_promo_link("123456")
        assert promo == "https://example.com/go/123456"

    @pytest.mark.asyncio
    async def test_get_original_url(self, link_db):
        await link_db.save_short_link("123456", "https://example.com/go/123456", "https://jd.com/123456")
        original = await link_db.get_original_url("123456")
        assert original == "https://jd.com/123456"

    @pytest.mark.asyncio
    async def test_increment_click(self, link_db):
        await link_db.save_short_link("123456", "https://example.com/go/123456", "https://jd.com/123456")
        await link_db.increment_click("123456")
        await link_db.increment_click("123456")
        stats = await link_db.get_stats("123456")
        assert stats["click_count"] == 2

    @pytest.mark.asyncio
    async def test_upsert_short_link(self, link_db):
        await link_db.save_short_link("123456", "https://old.com/go/123456", "https://jd.com/123456")
        await link_db.save_short_link("123456", "https://new.com/go/123456", "https://jd.com/123456")
        promo = await link_db.get_promo_link("123456")
        assert promo == "https://new.com/go/123456"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, link_db):
        assert await link_db.get_promo_link("999999") is None
        assert await link_db.get_stats("999999") is None
