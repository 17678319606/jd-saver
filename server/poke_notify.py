"""
Poke 通知模块 - 发送 MCP 工具调用记录到用户 Poke
"""
import os
import time
import httpx
from datetime import datetime
from typing import Optional

# 从环境变量读取 Webhook URL
POKE_WEBHOOK_URL = os.environ.get("MCP_POKE_WEBHOOK_URL", "")


async def notify_mcp_usage(
    user_id: str,
    tool_name: str,
    params: dict,
    success: bool,
    result: Optional[dict] = None,
) -> bool:
    """
    推送 MCP 工具调用记录到 Poke

    user_id: 用户标识
    tool_name: 工具名称
    params: 调用参数
    success: 是否成功
    result: 返回结果（仅包含摘要）
    """
    if not POKE_WEBHOOK_URL:
        return False

    # 构建通知消息
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "✅ 成功" if success else "❌ 失败"

    # 格式化参数（截断过长字段）
    params_str = ""
    for k, v in params.items():
        v_str = str(v)
        if len(v_str) > 50:
            v_str = v_str[:50] + "..."
        params_str += f"\n• {k}: {v_str}"

    # 格式化结果摘要
    result_summary = ""
    if result and success:
        if tool_name == "jd_get_coupon":
            price = result.get("price", "")
            coupons = result.get("coupons", [])
            total_save = result.get("total_save", 0)
            result_summary = f"\n💰 价格: ¥{price}\n🎫 优惠券: {len(coupons)}张\n💵 可省: ¥{total_save:.2f}"
        elif tool_name == "jd_generate_promo_link":
            promo_link = result.get("promo_link", "")
            result_summary = f"\n🔗 推广链接: {promo_link}"
        elif tool_name == "jd_set_price_alert":
            target = result.get("target_price", "")
            current = result.get("current_price", "")
            result_summary = f"\n📉 目标价: ¥{target}\n💵 当前价: ¥{current}"
        elif tool_name == "jd_search_goods":
            total = result.get("total", 0)
            goods = result.get("goods", [])
            result_summary = f"\n📦 找到 {total} 件商品"
            if goods:
                result_summary += f"\n🏆 最高销量: {goods[0].get('title', '')[:20]}..."
        elif tool_name == "jd_query_history":
            record_count = result.get("record_count", 0)
            lowest = result.get("lowest_price", "")
            result_summary = f"\n📊 历史记录: {record_count}条"
            if lowest:
                result_summary += f"\n📉 最低价: ¥{lowest}"
        elif tool_name == "jd_query_comment_quality":
            good_rate = result.get("good_rate", 0)
            quality_grade = result.get("quality_grade", "")
            result_summary = f"\n⭐ 好评率: {good_rate:.2f}%"
            if quality_grade:
                result_summary += f"\n📋 质量等级: {quality_grade}"
        elif tool_name == "jd_get_combo_scheme":
            scheme_count = result.get("scheme_count", 0)
            result_summary = f"\n🎁 凑单方案: {scheme_count}个"
        elif tool_name == "jd_find_deals":
            coupon_count = len(result.get("coupons", []))
            combo_count = result.get("save_info", {}).get("combo_count", 0)
            result_summary = f"\n🎫 优惠券: {coupon_count}张\n🎁 凑单方案: {combo_count}个"

    message = (
        f"🤖 MCP 工具调用记录\n"
        f"⏰ 时间: {now}\n"
        f"👤 用户: {user_id}\n"
        f"🔧 工具: {tool_name}\n"
        f"{status}\n"
        f"📝 参数:{params_str}\n"
        f"{result_summary}"
    )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                POKE_WEBHOOK_URL,
                json={"text": message, "msg_type": "text"},
            )
            resp.raise_for_status()
            return True
    except Exception as e:
        print(f"[POKE] 推送失败: {e}")
        return False
