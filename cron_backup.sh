#!/bin/bash
# 每日定时备份京东省钱助手数据库
# 加入 crontab：0 2 * * * /path/to/cron_backup.sh
set -e

DB_PATH="${DB_PATH:-/data/jd_saver.db}"
BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/jd_saver_${TIMESTAMP}.db"

mkdir -p "${BACKUP_DIR}"

# SQLite 原生备份（在线热备，不锁表）
cp "${DB_PATH}" "${BACKUP_FILE}"

# 同步 WAL 和 SHM 文件（如果存在）
for ext in "-wal" "-shm"; do
    src="${DB_PATH}${ext}"
    dst="${BACKUP_FILE}${ext}"
    [ -f "${src}" ] && cp "${src}" "${dst}"
done

echo "[backup] ${BACKUP_FILE} ($(du -sh "${BACKUP_FILE}" | cut -f1))"

# 清理过期备份
find "${BACKUP_DIR}" -name "jd_saver_*.db" -type f -mtime +${RETENTION_DAYS} -delete
echo "[backup] retention=${RETENTION_DAYS}d"
