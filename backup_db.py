"""
数据库自动备份脚本

用法：
    python backup_db.py                  # 备份到 ./backups/
    python backup_db.py --days 7         # 同时清理 7 天前的备份
    python backup_db.py --db /data/jd_saver.db
"""
import argparse
import asyncio
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

DB_PATH_ENV = "DB_PATH"
BACKUP_DIR = "backups"


async def do_backup(db_path: str, backup_dir: str, retention_days: int = 7) -> dict:
    """执行 SQLite 备份（VACUUM + 拷贝）"""
    db = Path(db_path)
    if not db.exists():
        return {"success": False, "error": f"数据库不存在: {db_path}"}

    backup_dir_path = Path(backup_dir)
    backup_dir_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir_path / f"jd_saver_{timestamp}.db"
    wal_file = backup_dir_path / f"jd_saver_{timestamp}.db-wal"
    shm_file = backup_dir_path / f"jd_saver_{timestamp}.db-shm"

    # VACUUM 压缩（可选，数据量大时耗时，默认跳过）
    # await run_vacuum(db_path)

    # 拷贝主数据库文件
    shutil.copy2(db_path, str(backup_file))

    # 拷贝 WAL/SHM（如果存在）
    for src, dst in [
        (str(db) + "-wal", str(wal_file)),
        (str(db) + "-shm", str(shm_file)),
    ]:
        if os.path.exists(src):
            shutil.copy2(src, dst)

    # 清理过期备份
    deleted = 0
    if retention_days > 0:
        cutoff = time.time() - retention_days * 86400
        for f in backup_dir_path.glob("jd_saver_*.db"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                deleted += 1

    return {
        "success": True,
        "backup_file": str(backup_file),
        "backup_size_mb": round(backup_file.stat().st_size / 1024 / 1024, 2),
        "deleted_old_backups": deleted,
    }


async def run_vacuum(db_path: str):
    """压缩数据库（可选，耗时操作）"""
    import aiosqlite
    conn = await aiosqlite.connect(db_path)
    try:
        await conn.execute("VACUUM")
        await conn.commit()
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description="京东省钱助手 - 数据库备份")
    parser.add_argument("--db", default=os.environ.get(DB_PATH_ENV, "./jd_saver.db"), help="数据库路径")
    parser.add_argument("--dir", default=BACKUP_DIR, help="备份目录")
    parser.add_argument("--days", type=int, default=7, help="保留天数（清理过期备份）")
    args = parser.parse_args()

    result = asyncio.run(do_backup(args.db, args.dir, args.days))
    print(f"备份结果: {result}")
    if not result["success"]:
        exit(1)


if __name__ == "__main__":
    main()
