# JD Saver 性能架构分析与优化方案

## 一、当前架构性能评估

### 1. SQLite 数据库容量分析

**数据结构：**
```sql
price_alerts (降价提醒)
├── user_id + sku_id (唯一索引)
├── target_price
├── current_price
└── notified (是否已通知)

price_records (价格历史记录)
├── sku_id + recorded_at (索引)
├── price
└── note
```

**容量估算：**

| 指标 | 1万用户 | 10万用户 | 100万用户 |
|------|---------|----------|-----------|
| 平均提醒数/用户 | 3条 | 3条 | 3条 |
| alerts表行数 | 3万 | 30万 | 300万 |
| records表行数 | 9万 | 90万 | 900万 |
| 数据库大小 | ~15MB | ~150MB | ~1.5GB |
| SQLite 支持上限 | ✅ | ✅ | ✅ (~140TB) |

**结论：SQLite 完全够用，百万用户以下无需迁移**

### 2. API 调用压力分析

**当前设计：**
- TTL 缓存 300s（5分钟）
- 相同 SKU 查询不重复调用京东 API

**压力测试估算：**

| 日活用户 | 人均查询次数 | 总查询次数 | 去重后 API 调用 |
|----------|-------------|------------|-----------------|
| 1万 | 5次 | 5万 | ~1万（缓存命中80%） |
| 10万 | 5次 | 50万 | ~10万 |
| 100万 | 5次 | 500万 | ~100万 |

**京东联盟限制：**
- 每日流量：30万次/天（从截图看）
- 我们的使用：正常情况远低于限制

### 3. 降价提醒通知量分析

**假设场景：**
- 100万用户，每人设置3个提醒 = 300万提醒
- 价格每5分钟轮询一次
- 触发通知率：< 1%（价格大幅波动才触发）

**通知压力：**
- 每秒检查：300万 / 300s = 1万次/秒
- 实际触发：100次/秒（乐观估计）

**解决方案：**
- ✅ 当前实现：异步队列 + 批量通知
- ⚠️ 需要：消息队列（Redis / RabbitMQ）当用户超过50万时

---

## 二、性能瓶颈与优化

### 瓶颈1：SQLite 并发写入

**问题：** 多用户同时设置提醒时写入竞争

**优化方案：**
```python
# 数据库连接池
class DatabasePool:
    _connections = {}
    
    async def get_connection(self, db_path):
        if db_path not in self._connections:
            self._connections[db_path] = await aiosqlite.connect(db_path)
        return self._connections[db_path]
```

### 瓶颈2：API 调用频率

**问题：** 大量用户同时查询同一商品

**优化方案：**
```python
# 分布式缓存（Redis）
async def get_cached_material(sku_id: str) -> dict:
    redis_key = f"jd:material:{sku_id}"
    cached = await redis.get(redis_key)
    if cached:
        return json.loads(cached)
    
    # 缓存 300s
    data = await query_goods_material(sku_id)
    await redis.set(redis_key, json.dumps(data), ex=300)
    return data
```

### 瓶颈3：降价提醒轮询

**问题：** 300万提醒，每5分钟检查一次

**优化方案：**
```python
# 分批轮询 + 增量检查
async def poll_alerts():
    # 每次只检查 1000 个提醒
    alerts = await db.get_active_alerts(limit=1000, offset=0)
    for alert in alerts:
        await check_and_notify(alert)
    
    # 使用优先级队列，高价值商品优先检查
```

---

## 三、扩展架构方案

### 阶段1：当前（0-10万用户）
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  EdgeOne CDN │────▶│  Nginx 反代  │────▶│  Oracle服务器 │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                                      ┌────────▼────────┐
                                      │  Docker容器     │
                                      │  FastMCP Server │
                                      └────────┬────────┘
                                               │
                                      ┌────────▼────────┐
                                      │  SQLite (本地)  │
                                      └─────────────────┘
```

### 阶段2：增长期（10-50万用户）
```
添加 Redis 缓存层：
- API 响应缓存
- 会话管理
- 限流计数器
```

### 阶段3：大规模（50万+用户）
```
拆分服务：
1. MCP 服务集群（无状态，可水平扩展）
2. Redis 集群（缓存层）
3. PostgreSQL（替代 SQLite，支持分库分表）
4. RabbitMQ（消息队列，处理降价提醒）
5. 定时任务服务（独立部署）
```

---

## 四、日志清理策略

### 1. Nginx 日志轮转（已配置）
```nginx
# /etc/logrotate.d/jd-saver
/www/wwwlogs/jinli.dajiayouxuan.com.log {
    weekly          # 每周轮转
    rotate 4        # 保留4周
    compress        # 压缩旧日志
    delaycompress   # 延迟压缩
    missingok       # 文件缺失不报错
    notifempty      # 空文件不轮转
    copytruncate    # 复制后截断（不重启nginx）
}
```

### 2. Docker 容器日志限制
```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"    # 单文件最大10MB
    max-file: "3"      # 最多3个文件
```

### 3. SQLite 数据库维护
```python
# 定期清理过期数据
async def cleanup_old_data():
    # 清理30天前的价格记录
    await db.execute("""
        DELETE FROM price_records 
        WHERE recorded_at < ? 
        AND sku_id NOT IN (
            SELECT sku_id FROM price_alerts
        )
    """, (int(time.time()) - 30*86400,))
```

---

## 五、关键决策总结

| 问题 | 决策 | 理由 |
|------|------|------|
| 数据库选型 | SQLite | 百万用户以下够用，零运维 |
| 缓存策略 | 内存 TTL + 可选 Redis | 简单场景先内存，复杂再加 Redis |
| 降价提醒 | 异步轮询 + 批量处理 | 避免实时通知压力 |
| 日志管理 | logrotate + Docker限制 | 自动清理，不占满磁盘 |
| 扩展路径 | SQLite → PostgreSQL | 用户增长后平滑迁移 |

---

## 六、下一步优化清单

- [ ] 添加 Redis 缓存层（可选）
- [ ] 实现日志自动清理脚本
- [ ] 添加 Prometheus 监控指标
- [ ] 实现用户配额限制（防止滥用）
- [ ] 添加 API 调用频率限制
