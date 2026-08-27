"""
数据清理工具 - 定期清理过期数据
"""
import os
import asyncio
from datetime import datetime, timedelta
from .database import PriceDatabase


async def cleanup_old_data(days: int = 30) -> dict:
    """清理过期数据
    
    Args:
        days: 保留天数，默认30天
    Returns:
        清理统计信息
    """
    db_path = os.environ.get("DB_PATH", "./jd_saver.db")
    db = PriceDatabase(db_path)
    await db.connect()
    
    try:
        cutoff_time = int((datetime.now() - timedelta(days=days)).timestamp())
        
        # 清理超过30天的价格记录
        cursor = await db._conn.execute(
            "DELETE FROM price_records WHERE recorded_at < ?",
            (cutoff_time,)
        )
        deleted_records = cursor.rowcount
        
        # 清理已通知的提醒（超过30天）
        cursor2 = await db._conn.execute(
            "DELETE FROM price_alerts WHERE notified = 1 AND updated_at < ?",
            (cutoff_time,)
        )
        deleted_alerts = cursor2.rowcount
        
        await db._conn.commit()
        
        return {
            "success": True,
            "deleted_price_records": deleted_records,
            "deleted_alerts": deleted_alerts,
            "cutoff_date": datetime.fromtimestamp(cutoff_time).isoformat(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        await db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="清理过期数据")
    parser.add_argument("--days", type=int, default=30, help="保留天数")
    args = parser.parse_args()
    
    result = asyncio.run(cleanup_old_data(args.days))
    print(f"清理结果: {result}")
