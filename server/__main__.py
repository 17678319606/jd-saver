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
    search_goods,
    query_goods_recommend,
    query_goods_combination,
    query_goods_comment_summary,
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


# ==================== Tool 3: 综合省钱方案（含真实凑单推荐） ====================
@mcp.tool()
async def jd_find_deals(link: str, user_id: str = "anonymous") -> dict:
    """综合省钱分析：查券 + 组合优惠推荐 + 商品推荐

    优先使用组合优惠 API，失败时降级为推荐商品
    """
    parsed = parse_jd_url(link)
    if not parsed["sku_id"]:
        return {"success": False, "error": "无法解析商品链接"}

    sku_id = parsed["sku_id"]
    config = JDConfig.from_env()
    results = {"sku_id": sku_id, "coupons": [], "combo_scheme": [], "recommendations": [], "save_info": {}}

    async with httpx.AsyncClient(timeout=25) as client:
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
            results["product"] = {"sku_id": sku_id, "title": "", "price": None}

        # 2. 尝试组合优惠方案（真正的凑单推荐）
        try:
            combo_result = await query_goods_combination(client, config, sku_id)
            goods_list = combo_result.get("goodsList", []) or combo_result.get("goods", [])
            for item in goods_list[:5]:
                item_price = item.get("jdPrice", 0)
                if item_price and float(item_price) > 0:
                    results["combo_scheme"].append({
                        "title": item.get("title", "")[:50],
                        "price": float(item_price),
                        "sku_id": item.get("id") or item.get("skuId", ""),
                        "coupon_info": item.get("couponInfo", {}),
                    })
        except Exception:
            pass

        # 3. 推荐相关商品（作为凑单备选）
        try:
            recommend_result = await query_goods_recommend(client, config, sku_id)
            rec_list = recommend_result.get("recommendGoods", []) or recommend_result.get("goodsList", [])
            main_price = results.get("product", {}).get("price") or 0
            for r in rec_list[:5]:
                r_price = r.get("jdPrice", 0)
                r_sku = r.get("id") or r.get("skuId", "")
                # 只推荐价格合理（小于主商品5倍，大于5元）的
                if r_sku and r_sku != sku_id and 5 < float(r_price) < float(main_price) * 5:
                    results["recommendations"].append({
                        "title": r.get("title", "")[:50],
                        "price": float(r_price),
                        "sku_id": r_sku,
                    })
        except Exception:
            pass

    # 计算可省金额
    total_save = sum(float(c.get("amount") or 0) for c in results.get("coupons", []))
    results["save_info"] = {
        "coupon_save": total_save,
        "has_coupon": total_save > 0,
        "combo_count": len(results.get("combo_scheme", [])),
        "recommend_count": len(results.get("recommendations", [])),
    }

    return {"success": True, **results}


# ==================== Tool 4: 设置降价提醒 ====================
@mcp.tool()
async def jd_set_price_alert(
    link: str,
    target_price: float,
    user_id: str,
) -> dict:
    """设置商品价格降价提醒

    触发时通过 Poke 推送通知用户（需配置 POKE_WEBHOOK_URL）
    """
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
            "message": "暂无历史价格数据，可发送京东链接让我查询当前价格并记录",
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


# ==================== Tool 7: 关键词搜索商品 ====================
@mcp.tool()
async def jd_search_goods(
    keyword: str,
    self_run_only: bool = False,
    max_price: Optional[float] = None,
    min_price: Optional[float] = None,
    sort_by: str = "sales",
    page: int = 1,
) -> dict:
    """
    搜索京东商品，优先返回自营、好评率高、价格合理的商品

    参数：
      keyword: 商品关键词
      self_run_only: 是否只显示京东自营商品（默认False）
      max_price: 最高价格过滤
      min_price: 最低价格过滤
      sort_by: 排序方式 "sales"=销量降序, "price_asc"=价格升序, "price_desc"=价格降序
      page: 页码（默认1）

    返回商品列表（不含佣金敏感信息）
    """
    start_time = time.time()
    metrics.increment("search_total")

    config = JDConfig.from_env()
    cache_key = f"search:{keyword}:{self_run_only}:{max_price}:{min_price}:{sort_by}:{page}"
    cached = cache.get("search", cache_key)
    if cached:
        metrics.increment("search_cache_hit")
        return {"success": True, "source": "cache", **cached}

    metrics.increment("search_cache_miss")

    # 构建 shop_types 参数
    shop_types = "1" if self_run_only else None

    # 构建排序：京东 API sort=1 升序, sort=2 降序
    sort_name = None
    sort_order = 1
    if sort_by == "price_asc":
        sort_name, sort_order = "price", 1
    elif sort_by == "price_desc":
        sort_name, sort_order = "price", 2
    elif sort_by == "sales":
        sort_name, sort_order = "salesCount", 2  # 销量降序

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            result = await search_goods(
                client, config, keyword,
                page_index=page,
                shop_types=shop_types,
                sort_name=sort_name,
                sort_order=sort_order,
                price_from=min_price,
                price_to=max_price,
            )
        except Exception as e:
            metrics.increment("search_error")
            return {"success": False, "error": f"搜索失败: {e}"}

    goods_list = result.get("goodsList", []) or result.get("data", {}).get("goodsList", [])

    # 过滤敏感信息，整理返回
    clean_goods = []
    for g in goods_list:
        coupon_info = g.get("couponInfo", {})
        coupons = []
        if isinstance(coupon_info, dict):
            coupons = [
                {"amount": c.get("discountAmount") or c.get("couponAmt"),
                 "threshold": c.get("minOrderAmount") or c.get("threshold")}
                for c in coupon_info.get("coupons", []) if c.get("discountAmount") or c.get("couponAmt")
            ]

        clean_goods.append({
            "sku_id": g.get("id") or g.get("skuId", ""),
            "title": g.get("title", ""),
            "price": g.get("jdPrice"),
            "image_url": g.get("imageUrl", ""),
            "shop_type": g.get("shopType", ""),  # "1"=自营
            "sales_count": g.get("salesCount", 0),
            "coupons": coupons,
            "total_coupon_save": sum(float(c.get("amount") or 0) for c in coupons),
        })

    output = {
        "success": True,
        "keyword": keyword,
        "total": len(clean_goods),
        "page": page,
        "self_run_only": self_run_only,
        "goods": clean_goods,
    }

    cache.set("search", cache_key, output, ttl=180)
    metrics.observe("search_latency", time.time() - start_time)
    return output


# ==================== Tool 8: 评论质量查询 ====================
@mcp.tool()
async def jd_query_comment_quality(sku_id: str) -> dict:
    """
    查询商品评论质量（好评率、差评关键词）
    用于判断商品是否有质量问题，帮助筛选
    """
    config = JDConfig.from_env()

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            result = await query_goods_comment_summary(client, config, sku_id)
        except Exception as e:
            return {"success": False, "error": f"评论查询失败: {e}", "sku_id": sku_id}

    summary = result.get("commentSummary", {}) or result.get("data", {})
    if not summary:
        return {
            "success": True,
            "sku_id": sku_id,
            "comment_rate": None,
            "good_rate": None,
            "bad_keywords": [],
            "message": "暂无评论数据",
        }

    good_rate = summary.get("goodRate", 0) or summary.get("good_COMMENT_RATE", 0)
    bad_keywords = summary.get("badCommentTagInfos", []) or summary.get("badKeywords", [])
    if isinstance(bad_keywords, list):
        bad_keywords = [bw.get("name") or bw.get("tagName", "") for bw in bad_keywords[:5]]

    return {
        "success": True,
        "sku_id": sku_id,
        "good_rate": float(good_rate),
        "total_comments": summary.get("commentCount", 0) or summary.get("count", 0),
        "bad_keywords": bad_keywords,
        "quality_grade": "优秀" if float(good_rate) >= 98 else ("良好" if float(good_rate) >= 95 else "一般"),
    }


# ==================== Tool 9: 商品组合优惠方案 ====================
@mcp.tool()
async def jd_get_combo_scheme(sku_id: str) -> dict:
    """
    查询商品的组合优惠方案（真正的凑单推荐）
    返回可以搭配购买享受额外优惠的商品列表
    """
    config = JDConfig.from_env()

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            result = await query_goods_combination(client, config, sku_id)
        except Exception as e:
            return {"success": False, "error": f"组合优惠查询失败: {e}", "sku_id": sku_id}

    goods_list = result.get("goodsList", []) or result.get("goods", []) or result.get("combinationGoods", [])

    scheme = []
    for item in goods_list[:10]:
        item_price = item.get("jdPrice", 0) or item.get("price", 0)
        coupon_info = item.get("couponInfo", {})
        coupons = []
        if isinstance(coupon_info, dict):
            coupons = [
                {"amount": c.get("discountAmount") or c.get("couponAmt"),
                 "threshold": c.get("minOrderAmount") or c.get("threshold")}
                for c in coupon_info.get("coupons", []) if c.get("discountAmount") or c.get("couponAmt")
            ]

        scheme.append({
            "sku_id": item.get("id") or item.get("skuId", ""),
            "title": item.get("title", "")[:50],
            "price": float(item_price) if item_price else 0,
            "coupons": coupons,
            "total_coupon_save": sum(float(c.get("amount") or 0) for c in coupons),
        })

    return {
        "success": True,
        "sku_id": sku_id,
        "scheme_count": len(scheme),
        "scheme": scheme,
    }
