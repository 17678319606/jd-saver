import os
import httpx
from datetime import datetime

MCP_POKE_WEBHOOK_URL = os.environ.get("MCP_POKE_WEBHOOK_URL", "")


async def send_poke_notification(webhook_url: str, message: str) -> bool:
    """发送 Poke 通知"""
    if not webhook_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json={"text": message, "msg_type": "text"})
            resp.raise_for_status()
            return True
    except Exception as e:
        print(f"[POKE] Send failed: {e}")
        return False


async def notify_mcp_usage(user_id: str, tool_name: str, params: dict, success: bool, result: dict):
    """推送 MCP 工具调用记录到 Poke"""
    if not MCP_POKE_WEBHOOK_URL:
        return
    try:
        price = result.get("price", "N/A")
        coupons = len(result.get("coupons", []))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = (
            "MCP 工具调用记录\n"
            f"时间: {now_str}\n"
            f"用户: {user_id}\n"
            f"工具: {tool_name}\n"
            f"成功: {success}\n"
            f"参数: {params}\n"
            f"价格: {price}\n"
            f"优惠券: {coupons}张"
        )
        await send_poke_notification(MCP_POKE_WEBHOOK_URL, msg)
    except Exception as e:
        print(f"[POKE] Error: {e}")
