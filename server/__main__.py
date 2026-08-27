"""
京东省钱助手 MCP Server
佣金信息在服务端内部处理，不暴露给前端
短链接使用自己域名 + nginx 302 重定向
"""
import os
import time
import httpx
from typing import Optional

from fastmcp import FastMCP

from .jd_config import JDConfig, parse_jd_url
from .jd_api import (
    gen_promo_link,
    query_goods_material,
    query_coupon_info,
    mcp_search_goods,
    get_mcp_promotion,
    query_goods_snapshot,
)
from .database import PriceDatabase
from .short_links import ShortLinkDatabase
from .cache import cache
from .metrics import metrics

mcp = FastMCP("jd-saver")


# ==================== Tool 1: 查隐藏优惠券 ====================
@mcp.tool()
async def jd_get_coupon(link: str, user_id: str = "anonymous") -> dict:
    """查询京东商品的隐藏优惠券

    注意：佣金率、佣金金额等敏感信息在服务端过滤，不返回给前端
    """
    start_time = time.time()
    metrics.increment("coupon_query_total")

    parsed = parse_jd_url(link)
    if not parsed["sku_id"]:
        return {"success": False, "error": "无法从链接中提取 SKU ID"}

    sku_id = parsed["sku_id"]
    cached = cache.get("coupon", sku_id)
    if cached:
        metrics.increment("coupon_cache_hit")
        return {"success": True, "sku_id": sku_id, "data": cached, "source": "cache"}

    metrics.increment("coupon_cache_miss")
    config = JDConfig.from_env()
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            material = await query_goods_material(client, config, sku_id)
        except Exception as e:
            metrics.increment("coupon_error")
            return {"success": False, "error": f"API 调用失败: {e}"}

    # 只返回用户需要的信息，佣金敏感字段已过滤
    coupons = []
    coupon_info = material.get("couponInfo", {})
    if isinstance(coupon_info, dict):
        coupons = [
            {
                "amount": c.get("discountAmount") or c.get("couponAmt"),
                "threshold": c.get("minOrderAmount") or c.get("threshold"),
            }
            for c in coupon_info.get("coupons", [])
        ]

    result = {
        "success": True,
        "sku_id": sku_id,
        "title": material.get("title", ""),
        "price": material.get("jdPrice"),
        "image_url": material.get("imageUrl", ""),
        "coupons": coupons,
        "total_save": sum(float(c.get("amount") or 0) for c in coupons),
        # 注意：commission 字段已移除
    }

    cache.set("coupon", sku_id, result)
    metrics.observe("coupon_latency", time.time() - start_time)
    return result


# ==================== Tool 2: 生成推广链接（转链） ====================
@mcp.tool()
async def jd_generate_promo_link(link: str, user_id: str = "anonymous") -> dict:
    """生成带佣金的推广链接（转链）

    返回短链接格式：https://jinli.dajiayouxuan.com/go/{sku_id}
    nginx 配置了 302 重定向到京东联盟，用户看不到京东域名
    """
    parsed = parse_jd_url(link)
    if not parsed["sku_id"]:
        return {"success": False, "error": "无法从链接中提取 SKU ID"}

    sku_id = parsed["sku_id"]
    config = JDConfig.from_env()

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            result = await gen_promo_link(client, config, link)
        except Exception as e:
            return {"success": False, "error": f"转链失败: {e}"}

    # 获取原始京东推广链接
    jd_url = result.get("materialUrl") or result.get("url", "")

    # 返回我们自己域名的短链接（nginx 负责 302 重定向）
    short_link = f"https://jinli.dajiayouxuan.com/go/{sku_id}"

    # 保存到短链接数据库
    db = ShortLinkDatabase(os.environ.get("DB_PATH", "./jd_saver.db"))
    await db.connect()
    try:
        await db.save_short_link(sku_id, short_link, jd_url)
    finally:
        await db.close()

    return {
        "success": True,
        "sku_id": sku_id,
        "promo_link": short_link,
        # 注意：original_jd_url 不返回给前端，只在服务端记录
    }


# ==================== Tool 3: 综合省钱方案 ====================
@mcp.tool()
async def jd_find_deals(link: str, user_id: str = "anonymous") -> dict:
    """综合省钱分析：查券 + 推荐凑单品

    只返回用户可见的优惠信息，佣金详情不外泄
    """
    parsed = parse_jd_url(link)
    if not parsed["sku_id"]:
        return {"success": False, "error": "无法解析商品链接"}

    sku_id = parsed["sku_id"]
    config = JDConfig.from_env()
    results = {"sku_id": sku_id, "coupons": [], "deals": [], "save_info": {}}

    async with httpx.AsyncClient(timeout=20) as client:
        # 1. 查询优惠券
        try:
            material = await query_goods_material(client, config, sku_id)
            coupon_info = material.get("couponInfo", {})
            results["product"] = {
                "title": material.get("title", ""),
                "image": material.get("imageUrl", ""),
                "price": material.get("jdPrice"),
            }
            if isinstance(coupon_info, dict):
                results["coupons"] = [
                    {
                        "amount": c.get("discountAmount") or c.get("couponAmt"),
                        "threshold": c.get("minOrderAmount") or c.get("threshold"),
                    }
                    for c in coupon_info.get("coupons", [])
                ]
        except Exception as e:
            results["coupon_error"] = str(e)

        # 2. 搜索同类低价商品（凑单参考）
        product_title = results.get("product", {}).get("title", "")
        if product_title:
            try:
                keyword = product_title[:20]
                search_result = await mcp_search_goods(client, config, keyword)
                goods_list = search_result.get("goodsList", [])
                current_price = results.get("product", {}).get("price", 99999)
                for g in goods_list[:5]:
                    g_price = g.get("jdPrice", 0)
                    if 0 < g_price < current_price * 0.3 and g_price >= 5:
                        results["deals"].append({
                            "title": g.get("title", "")[:40],
                            "price": g_price,
                            "sku_id": g.get("id", ""),
                        })
            except Exception:
                pass

    # 计算可省金额
    total_save = sum(float(c.get("amount") or 0) for c in results.get("coupons", []))
    results["save_info"] = {
        "coupon_save": total_save,
        "has_coupon": total_save > 0,
    }

    return {"success": True, **results}


# ==================== Tool 4: 设置降价提醒 ====================
@mcp.tool()
async def jd_set_price_alert(
    link: str,
    target_price: float,
    user_id: str,
) -> dict:
    """设置商品价格降价提醒"""
    parsed = parse_jd_url(link)
    if not parsed["sku_id"]:
        return {"success": False, "error": "无法解析商品链接"}

    sku_id = parsed["sku_id"]
    config = JDConfig.from_env()

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            material = await query_goods_material(client, config, sku_id)
            current_price = float(material.get("jdPrice", 0))
        except Exception:
            current_price = 0

    db = PriceDatabase(os.environ.get("DB_PATH", "./jd_saver.db"))
    await db.connect()
    try:
        await db.add_price_alert(user_id, sku_id, target_price, current_price)
    finally:
        await db.close()

    return {
        "success": True,
        "sku_id": sku_id,
        "target_price": target_price,
        "current_price": current_price,
        "alert_created": current_price > target_price,
    }


# ==================== Tool 5: 查询历史价格 ====================
@mcp.tool()
async def jd_query_history(sku_id: str, limit: int = 30) -> dict:
    """查询商品历史价格记录"""
    db = PriceDatabase(os.environ.get("DB_PATH", "./jd_saver.db"))
    await db.connect()
    try:
        records = await db.get_price_history(sku_id, limit)
        lowest = await db.get_lowest_price(sku_id)
    finally:
        await db.close()

    if not records:
        return {
            "success": True,
            "sku_id": sku_id,
            "records": [],
            "lowest_price": None,
            "message": "暂无历史价格数据",
        }

    return {
        "success": True,
        "sku_id": sku_id,
        "records": records,
        "lowest_price": lowest,
        "record_count": len(records),
    }


# ==================== Tool 6: 更新最低价 ====================
@mcp.tool()
async def jd_update_min_price(sku_id: str, price: float, note: str = "") -> dict:
    """更新商品历史最低价（用户反馈更低价时调用）"""
    db = PriceDatabase(os.environ.get("DB_PATH", "./jd_saver.db"))
    await db.connect()
    try:
        record_time = await db.save_price_record(sku_id, price, note)
        cache.invalidate_sku(sku_id)
    finally:
        await db.close()

    return {
        "success": True,
        "sku_id": sku_id,
        "price": price,
        "note": note,
        "recorded_at": record_time,
    }
