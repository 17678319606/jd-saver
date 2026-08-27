"""
后台价格轮询任务 - 定时检查降价提醒是否触发
"""
import asyncio
import os
import httpx
import time

from .jd_config import JDConfig
from .jd_api import query_goods_material
from .database import PriceDatabase


async def poll_and_notify():
    """核心轮询逻辑：每 5 分钟执行一次"""
    db = PriceDatabase(os.environ.get("DB_PATH", "./jd_saver.db"))
    await db.connect()
    config = JDConfig.from_env()

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
                        await db.update_alert_price(sku_id, current_price)

                        # 检查是否触发
                        triggers = await db.check_and_get_triggers()
                        for user_id, alert_sku, cp, tp in triggers:
                            if alert_sku == sku_id:
                                print(f"[ALERT] user={user_id} sku={sku_id} price={cp} target={tp}")
                                # TODO: 接入 Poke 消息推送
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
