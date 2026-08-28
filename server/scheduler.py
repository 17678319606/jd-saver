"""
后台价格轮询任务 - 定时检查降价提醒是否触发
触发后通过 Poke webhook 推送通知（如配置了 POKE_WEBHOOK_URL）
"""
import asyncio
import os
import httpx

from .jd_config import JDConfig
from .jd_api import query_goods_material
from .database import PriceDatabase


# 从环境变量读取 Poke webhook URL（用户自行配置）
POKE_WEBHOOK_URL = os.environ.get("POKE_WEBHOOK_URL", "")


async def _send_poke_notification(webhook_url: str, message: str) -> bool:
    """发送 Poke 通知"""
    if not webhook_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                webhook_url,
                json={"text": message, "msg_type": "text"},
            )
            resp.raise_for_status()
            return True
    except Exception as e:
        print(f"[NOTIFY] 发送失败: {e}")
        return False


async def poll_and_notify():
    """核心轮询逻辑：每 5 分钟执行一次"""
    db = PriceDatabase(os.environ.get("DB_PATH", "./jd_saver.db"))
    await db.connect()
    config = JDConfig.from_env()

    notified_cache = set()  # 避免重复通知同一 (user_id, sku_id)

    while True:
        try:
            # 获取所有有待检查的 SKU
            skus = await db.get_active_alert_skus()
            if not skus:
                await asyncio.sleep(300)
                continue

            async with httpx.AsyncClient(timeout=15) as client:
                for sku_id in skus:
                    try:
                        material = await query_goods_material(client, config, sku_id)
                        current_price = float(material.get("jdPrice", 0))
                        product_title = material.get("title", "")
                        await db.update_alert_price(sku_id, current_price)

                        # 检查是否触发
                        triggers = await db.check_and_get_triggers()
                        for user_id, alert_sku, cp, tp in triggers:
                            if alert_sku == sku_id:
                                cache_key = (user_id, sku_id)
                                if cache_key in notified_cache:
                                    continue
                                notified_cache.add(cache_key)

                                price_drop = float(tp) - float(cp)
                                percent = (price_drop / float(tp) * 100) if tp else 0

                                print(f"[ALERT] user={user_id} sku={sku_id} price={cp} target={tp} drop={percent:.1f}%")

                                # 构建通知消息
                                notify_msg = (
                                    f"🔔 降价提醒\n"
                                    f"商品：{product_title[:30]}\n"
                                    f"目标价：¥{tp} → 当前价：¥{cp}\n"
                                    f"已降价：¥{price_drop:.2f}（{percent:.1f}%）\n"
                                    f"快去下单吧！"
                                )

                                # 通过 Poke 推送
                                if POKE_WEBHOOK_URL:
                                    ok = await _send_poke_notification(POKE_WEBHOOK_URL, notify_msg)
                                    if not ok:
                                        print(f"[NOTIFY] 推送失败，保留通知供重试")
                                        notified_cache.discard(cache_key)  # 失败则允许重试
                                    else:
                                        print(f"[NOTIFY] 已推送给 user={user_id}")

                                await db.mark_notified(user_id, sku_id)

                    except Exception as e:
                        print(f"[ERROR] poll sku={sku_id}: {e}")

        except Exception as e:
            print(f"[ERROR] poll loop: {e}")

        await asyncio.sleep(300)  # 5 分钟间隔


def run_scheduler():
    asyncio.run(poll_and_notify())


if __name__ == "__main__":
    run_scheduler()
