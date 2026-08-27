"""
Poke 通知模块 - 发送价格提醒通知
"""
import os
import json
import httpx
from typing import Optional, Dict, Any


class PokeNotifier:
    """Poke webhook 通知器"""
    
    def __init__(self):
        self.webhook_url = "https://poke.com/api/v1/inbound/webhook"
        self.webhook_token = os.environ.get("POKE_WEBHOOK_TOKEN", "")
        self.api_key = os.environ.get("POKE_API_KEY", "")
        
    async def send_price_drop_alert(
        self,
        user_id: str,
        product_title: str,
        original_price: float,
        current_price: float,
        promo_link: str,
        sku_id: str,
    ) -> Dict[str, Any]:
        """发送降价提醒通知"""
        discount = ((original_price - current_price) / original_price * 100) if original_price > 0 else 0
        
        payload = {
            "event": "price_drop",
            "user_id": user_id,
            "product": {
                "title": product_title[:50],
                "sku_id": sku_id,
                "original_price": round(original_price, 2),
                "current_price": round(current_price, 2),
                "discount_percent": round(discount, 1),
            },
            "promo_link": promo_link,
            "timestamp": _now_iso(),
        }
        
        return await self._send_webhook(payload)
    
    async def send_message(self, message: str) -> Dict[str, Any]:
        """发送消息到 Poke（非 webhook 方式）"""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://poke.com/api/v1/inbound/api-message",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"message": message},
            )
            return resp.json()
    
    async def _send_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """发送 webhook 通知"""
        if not self.webhook_token:
            return {"success": False, "error": "POKE_WEBHOOK_TOKEN not configured"}
        
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                self.webhook_url,
                headers={
                    "Authorization": f"Bearer {self.webhook_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            return resp.json()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
