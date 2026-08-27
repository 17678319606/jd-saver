"""
京东省钱助手 MCP Server
提供 6 个工具：查券、转链、省钱方案、降价提醒、历史价格、更新最低价
"""
import os
import asyncio
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
from .cache import cache

mcp = FastMCP("jd-saver")


# ==================== Tool 1: 查隐藏优惠券 ====================
@mcp.tool()
async def jd_get_coupon(link: str, user_id: str = "anonymous") -> dict:
    """查询京东商品的隐藏优惠券和佣金信息

    Args:
        link: 京东商品链接（如 https://item.jd.com/123456.html）
        user_id: 用户标识
    """
    parsed = parse_jd_url(link)
    if not parsed.get("sku_id"):
        return {"success": False, "error": "无法解析京东链接，请确认是京东商品链接"}

    sku_id = parsed["sku_id"]
    config = JDConfig.from_env()

    # 先查缓存
    cached = cache.get("material", {"sku_id": sku_id})
    if cached:
        return {"success": True, "sku_id": sku_id, "source": "cache", **cached}

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            material = await query_goods_material(client, config, sku_id)
        except Exception as e:
            return {"success": False, "error": f"API 错误: {e}"}

    cache.set("material", {"sku_id": sku_id}, material)

    # 解析优惠券
    coupons = []
    coupon_info = material.get("couponInfo") or {}
    if isinstance(coupon_info, dict):
        for c in coupon_info.get("coupons", []) or coupon_info.get("couponList", []):
            coupons.append({
                "amount": c.get("discountAmount") or c.get("couponAmt"),
                "threshold": c.get("minOrderAmount") or c.get("threshold"),
                "end_time": c.get("endTime"),
            })

    commission = None
    comm_info = material.get("commissionInfo") or {}
    if isinstance(comm_info, dict):
        commission = {
            "rate": comm_info.get("commissionRate"),
            "earn": comm_info.get("commission"),
        }

    return {
        "success": True,
        "sku_id": sku_id,
        "title": material.get("title", ""),
        "price": material.get("jdPrice"),
        "image_url": material.get("imageUrl", ""),
        "coupons": coupons,
        "commission": commission,
        "total_save": sum(float(c.get("amount") or 0) for c in coupons),
    }


# ==================== Tool 2: 生成推广链接（转链 CPS） ====================
@mcp.tool()
async def jd_generate_promo_link(link: str, user_id: str = "anonymous") -> dict:
    """生成带佣金的推广链接（转链），用于 CPS 赚佣金

    Args:
        link: 京东商品链接
        user_id: 用户标识
    """
    parsed = parse_jd_url(link)
    if not parsed.get("sku_id"):
        return {"success": False, "error": "无法解析京东链接"}

    config = JDConfig.from_env()
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            result = await gen_promo_link(client, config, link)
        except Exception as e:
            return {"success": False, "error": f"转链失败: {e}"}

    promo_url = (
        result.get("materialUrl")
        or result.get("url")
        or result.get("unionUrl")
        or ""
    )

    return {
        "success": True,
        "sku_id": parsed["sku_id"],
        "promo_link": promo_url,
        "raw": result,
    }


# ==================== Tool 3: 综合省钱方案（查券+凑单） ====================
@mcp.tool()
async def jd_find_deals(link: str, user_id: str = "anonymous") -> dict:
    """综合省钱分析：查隐藏券 + 推荐凑单品

    用户发商品链接后，一次性返回完整省钱方案
    """
    parsed = parse_jd_url(link)
    if not parsed.get("sku_id"):
        return {"success": False, "error": "无法解析京东链接"}

    sku_id = parsed["sku_id"]
    config = JDConfig.from_env()
    result = {"sku_id": sku_id, "coupons": [], "deals": [], "commission": None}

    async with httpx.AsyncClient(timeout=20) as client:
        # 1. 查优惠券
        try:
            material = await query_goods_material(client, config, sku_id)
            result["product"] = {
                "title": material.get("title", ""),
                "price": material.get("jdPrice"),
                "image": material.get("imageUrl", ""),
            }
            coupon_info = material.get("couponInfo") or {}
            if isinstance(coupon_info, dict):
                for c in coupon_info.get("coupons", []) or coupon_info.get("couponList", []):
                    result["coupons"].append({
                        "amount": c.get("discountAmount") or c.get("couponAmt"),
                        "threshold": c.get("minOrderAmount") or c.get("threshold"),
                    })
            comm = material.get("commissionInfo") or {}
            if isinstance(comm, dict):
                result["commission"] = {"rate": comm.get("commissionRate"), "earn": comm.get("commission")}
        except Exception as e:
            result["coupon_error"] = str(e)

        # 2. 查凑单优惠方案
        try:
            promotion = await get_mcp_promotion(client, config, sku_id)
            result["promotion"] = promotion
        except Exception:
            pass

        # 3. 搜索同类低价凑单品
        title = result.get("product", {}).get("title", "")
        if title:
            try:
                keyword = title[:15]
                search = await mcp_search_goods(client, config, keyword)
                goods_list = search.get("goodsList", [])
                cur_price = result.get("product", {}).get("price") or 99999
                for g in goods_list[:5]:
                    g_price = g.get("jdPrice", 0)
                    if 0 < g_price < cur_price * 0.3 and g_price >= 3:
                        result["deals"].append({
                            "title": g.get("title", "")[:40],
                            "price": g_price,
                            "sku_id": g.get("id", ""),
                        })
            except Exception:
                pass

    result["total_save"] = sum(float(c.get("amount") or 0) for c in result["coupons"])
    return {"success": True, **result}


# ==================== Tool 4: 设置降价提醒 ====================
@mcp.tool()
async def jd_set_price_alert(link: str, target_price: float, user_id: str) -> dict:
    """为商品设置降价提醒，价格低于目标价时通知用户

    Args:
        link: 京东商品链接
        target_price: 目标价格（低于此价格时提醒）
        user_id: 用户标识
    """
    parsed = parse_jd_url(link)
    if not parsed.get("sku_id"):
        return {"success": False, "error": "无法解析京东链接"}

    sku_id = parsed["sku_id"]
    config = JDConfig.from_env()

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            material = await query_goods_material(client, config, sku_id)
            current_price = float(material.get("jdPrice", 0))
        except Exception as e:
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
        "alert_active": current_price > target_price,
    }


# ==================== Tool 5: 查询历史价格 ====================
@mcp.tool()
async def jd_query_history(sku_id: str, limit: int = 30) -> dict:
    """查询商品历史价格，标注历史最低价

    Args:
        sku_id: 商品 SKU ID
        limit: 返回记录数（最多 365 条）
    """
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
            "message": "暂无历史数据，首次通过 jd_update_min_price 或 jd_query_history 会记录当前价",
        }

    return {
        "success": True,
        "sku_id": sku_id,
        "records": records,
        "lowest_price": lowest,
        "record_count": len(records),
    }


# ==================== Tool 6: 更新最低价（用户反馈） ====================
@mcp.tool()
async def jd_update_min_price(sku_id: str, price: float, note: str = "") -> dict:
    """用户反馈有更低价时，更新历史最低价记录

    Args:
        sku_id: 商品 SKU ID
        price: 更低的实际成交价
        note: 备注（如"双11叠加券"）
    """
    db = PriceDatabase(os.environ.get("DB_PATH", "./jd_saver.db"))
    await db.connect()
    try:
        recorded_at = await db.save_price_record(sku_id, price, note)
        cache.invalidate_sku(sku_id)
    finally:
        await db.close()

    return {
        "success": True,
        "sku_id": sku_id,
        "price": price,
        "note": note,
        "recorded_at": recorded_at,
    }


# ==================== Tool 7: 获取凑单优惠方案（纯凑单） ====================
@mcp.tool()
async def jd_get_combo_scheme(sku_id: str, user_id: str = "anonymous") -> dict:
    """查询该商品的凑单优惠方案（满减/套餐券等）

    Args:
        sku_id: 商品 SKU ID
    """
    config = JDConfig.from_env()
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            material = await query_goods_material(client, config, sku_id)
            promotion = await get_mcp_promotion(client, config, sku_id)
            return {"success": True, "material": material, "promotion": promotion}
        except Exception as e:
            return {"success": False, "error": str(e)}


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
