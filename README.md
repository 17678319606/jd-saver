# JD Saver - 京东省钱助手

基于 FastMCP 的京东联盟优惠助手，通过 Poke Recipe 分发。

## 功能

- 🔍 查隐藏优惠券
- 🔗 CPS 转链赚佣金（短链接保护隐私）
- 💰 综合省钱方案（券+凑单）
- 🔔 降价提醒 + Poke 通知
- 📈 历史价格追踪

## 快速开始（本地开发）

```bash
cd jd-saver
pip install -r requirements.txt

# 配置环境变量
export JD_APP_KEY=your_key
export JD_APP_SECRET=your_secret
export JD_PID=123456_1000
export POKE_API_KEY=your_poke_api_key
export POKE_WEBHOOK_TOKEN=your_webhook_token

# 启动
python -m server
```

## Docker 部署（Oracle 服务器）

```bash
cd docker
cp .env.example .env  # 填入凭证

# 构建并启动
docker compose up -d --build

# 验证服务
curl http://localhost:8765/sse
```

## Poke Recipe 发布

### 方法 1: 手动添加 MCP（推荐）

1. 访问 https://poke.com/integrations/new
2. 添加 MCP 服务器 URL: `https://jinli.dajiayouxuan.com/mcp`
3. 名称: `JD Saver`

### 方法 2: CLI 添加

```bash
poke mcp add https://jinli.dajiayouxuan.com/mcp --name "JD Saver"
```

### 方法 3: 创建 Recipe（开发阶段）

```bash
# 启动本地隧道
npx poke@latest tunnel http://localhost:8765/mcp --name "jd-saver" --recipe
```

> 注意：隧道仅用于开发测试。生产环境请使用方法 1 或 2。

## MCP 工具列表

| 工具 | 说明 |
|------|------|
| `jd_get_coupon` | 查优惠券 |
| `jd_generate_promo_link` | 转链生成短链接 |
| `jd_find_deals` | 综合省钱方案 |
| `jd_set_price_alert` | 设置降价提醒 |
| `jd_query_history` | 查询历史价格 |
| `jd_update_min_price` | 更新最低价 |
| `jd_get_combo_scheme` | 凑单优惠方案 |

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `JD_APP_KEY` | ✅ | 京东联盟 App Key |
| `JD_APP_SECRET` | ✅ | 京东联盟 App Secret |
| `JD_PID` | ✅ | 推广位 PID（如 123456_1000） |
| `POKE_API_KEY` | ❌ | Poke API 密钥（用于消息推送） |
| `POKE_WEBHOOK_TOKEN` | ❌ | Poke Webhook Token（降价提醒通知） |
| `DB_PATH` | ❌ | SQLite 路径，默认 `./jd_saver.db` |
| `CACHE_TTL` | ❌ | 缓存过期时间（秒），默认 300 |
| `POLL_INTERVAL` | ❌ | 价格轮询间隔（秒），默认 300 |

## 架构说明

```
用户 → EdgeOne CDN → 前端服务器 (122.51.106.193)
                    → nginx 反向代理 → WireGuard → Oracle (144.24.11.95)
                                               → jd-saver Docker 容器 (:8765)
                                               → 京东联盟 API
                                               → SQLite 数据库
                                               → Poke Webhook (降价提醒)
```

## 隐私保护

- 佣金率、佣金金额等敏感信息在服务端过滤，不返回给前端
- 转链后展示短链接 `https://jinli.dajiayouxuan.com/go/{sku_id}`，不暴露京东域名
- 所有佣金数据仅在服务端内部使用

## 性能优化

- SQLite WAL 模式支持高并发读写
- TTL 内存缓存减少京东 API 调用
- 异步价格监控避免阻塞主线程
- logrotate 日志轮转防止磁盘占用

## GitHub

https://github.com/17678319606/jd-saver
