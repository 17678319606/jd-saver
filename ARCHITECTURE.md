# JD Saver - 京东省钱助手 架构文档

## 项目结构

```
jd-saver/
├── server/
│   ├── __init__.py          # 包入口
│   ├── __main__.py          # MCP 工具定义（stdio 模式）
│   ├── jd_config.py         # 配置 & JD URL 解析
│   ├── jd_api.py            # 京东联盟 API 封装（5个核心接口）
│   ├── database.py          # SQLite 价格追踪存储
│   ├── cache.py             # TTL 内存缓存（300s）
│   └── scheduler.py         # 定时轮询降价提醒
├── server_sse.py            # SSE 入口（poke tunnel 用）
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── .env.example
├── poke/recipe.json         # Poke Recipe 元数据
├── requirements.txt
└── README.md
```

---

## 已实现的 6 个 MCP 工具

| 工具名 | 功能 | 对应 JD API |
|--------|------|-------------|
| `jd_get_coupon` | 查隐藏优惠券 + 佣金率 | jd.union.open.goods.material.query |
| `jd_generate_promo_link` | 生成 CPS 推广链接（转链） | jd.union.open.goods.link.query |
| `jd_find_deals` | 综合省钱方案（券+凑单推荐） | material + mcp.promotion + mcp.goods.query |
| `jd_set_price_alert` | 设置降价提醒 | material.query + SQLite INSERT |
| `jd_query_history` | 查历史价格，标注最低价 | SQLite SELECT |
| `jd_update_min_price` | 用户反馈更低价时更新记录 | SQLite INSERT |
| `jd_get_combo_scheme` | 查询凑单优惠方案 | mcp.promotion.get |

---

## 部署方案详解

### 生产环境：Oracle 甲骨文服务器 + Docker

```
┌─────────────────────────────────────────────────┐
│  Oracle Cloud Free Tier 虚拟机                  │
│  ┌───────────────────────────────────────────┐  │
│  │  Docker Compose                            │  │
│  │  ┌──────────────┐  ┌─────────────────────┐ │  │
│  │  │ jd-saver     │  │ SQLite (WAL mode)   │ │  │
│  │  │ :8765 (SSE)  │  │ /data/jd_saver.db   │ │  │
│  │  └──────────────┘  └─────────────────────┘ │  │
│  │                                              │  │
│  │  npx poke@latest tunnel http://...:8765     │  │
│  └───────────────────────────────────────────┘  │
│                    ↓                             │
│         jinli.dajiayouxuan.com (CNAME)         │
└─────────────────────────────────────────────────┘
```

**步骤：**

1. **Oracle 服务器上**
```bash
# 创建目录，拷贝代码
git clone <repo> /opt/jd-saver && cd /opt/jd-saver/docker

# 配置环境变量
cp .env.example .env
vim .env  # 填入 JD_APP_KEY, JD_APP_SECRET, JD_PID

# 启动
docker compose up -d --build
```

2. **本地 Poke 隧道发布 Recipe**
```bash
npx poke@latest tunnel http://localhost:8765/mcp -n "jd-saver" --recipe
# 输出分享链接，分发给用户
```

3. **反向代理（nginx 可选）**
```nginx
server {
    listen 80;
    server_name jinli.dajiayouxuan.com;
    location /mcp {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 为什么不用 MySQL

| 对比 | SQLite | MySQL |
|------|--------|-------|
| 运维成本 | 零，单文件 | 需安装、备份、监控 |
| 并发 | WAL 模式足够支持数万同时读写 | 更强但过度设计 |
| 几十万用户 | 每用户 ~10 条记录 = 百万级行，SQLite 轻松应对 | 需要分库分表才够 |
| 成本 | 免费 | 云数据库 ¥50-200/月 |
| 迁移 | 直接复制 .db 文件 | mysqldump |

**结论**：SQLite 在此场景下是更合理的选择。除非后续需要跨多节点共享数据，否则不要引入不必要的复杂度。

### 定时任务 vs 宝塔面板

- **不推荐宝塔计划任务**：会多开进程，且不好管理 Python 异步代码
- **推荐方案**：用 APScheduler 内置在程序中，或 `docker compose` 的 healthcheck + 后台任务
- **当前实现**：`scheduler.py` 内嵌在同一个进程里，每 5 分钟检查一次

---

## 性能优化要点

| 优化点 | 实现方式 |
|--------|----------|
| **API 缓存** | 内存 TTL 缓存 300s，同一 SKU 5 分钟内不重复调用京东 API |
| **SQLite WAL** | 提升并发读写，避免锁表 |
| **连接池复用** | httpx.AsyncClient 复用 TCP 连接 |
| **异步 I/O** | 全部 async/await，单进程可处理多请求 |
| **无状态设计** | 服务无状态，可水平扩多实例（共享 SQLite 文件） |
| **数据库分区** | price_records 按 sku_id 索引，查询 O(log n) |

**几十万人规模预估**：
- 日活假设 1 万，人均每天调用 3 次 = 3 万次 API 调用
- 300s 缓存后实际调用降至 ~6000 次/天，完全可行
- SQLite 100 万行数据查询 < 50ms

---

## 域名选择

推荐使用 **`jinli.dajiayouxuan.com`**：
- 主域名已备案其他站点，不动主域
- 子域名独立备案（ICP 备案支持子域名）
- 与京东联盟备案域名关联清晰
