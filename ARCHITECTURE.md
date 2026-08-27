# JD Saver - 京东省钱助手 架构文档

## 项目结构

```
jd-saver/
├── server/
│   ├── __init__.py          # 包入口
│   ├── __main__.py          # MCP 工具定义（stdio/sse模式）
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
├── README.md
└── ARCHITECTURE.md
```

---

## 已实现的 6 个 MCP 工具

| 工具名 | 功能 | 对应 JD API |
|--------|------|-------------|
| `jd_get_coupon` | 查隐藏优惠券 + 佣金率 | jd.union.open.goods.material.query |
| `jd_generate_promo_link` | 生成 CPS 推广链接（转链） | jd.union.open.goods.link.query |
| `jd_find_deals` | 综合省钱方案（券+凑单） | material + mcp.promotion + mcp.goods.query |
| `jd_set_price_alert` | 设置降价提醒 | material.query + SQLite INSERT |
| `jd_query_history` | 查历史价格，标注最低价 | SQLite SELECT |
| `jd_update_min_price` | 用户反馈更低价时更新记录 | SQLite INSERT |

---

## 生产部署架构 (✅ 已完成)

```
用户浏览器
    ↓ HTTPS
EdgeOne CDN (腾讯云)
    ↓
前端反代 122.51.106.193 (宝塔 nginx)
    ↓ WireGuard 隧道
甲骨文服务器 144.24.11.95
    ↓ Docker
jd-saver 容器 :8765
    ↓ HTTPS
京东联盟 API api.jd.com
```

### 当前状态

| 组件 | 状态 | 地址 |
|------|------|------|
| Docker 容器 | ✅ 运行中 | `http://10.99.99.2:8765/sse` |
| Nginx 反代 | ✅ 已配置 | `https://jinli.dajiayouxuan.com/mcp` |
| EdgeOne CDN | ✅ 已接入 | DNS 指向 `eo.dnse2.com` |
| MCP 服务 | ✅ 响应正常 | SSE 端点可用 |

### 访问验证

```bash
# 本地测试 (oracle服务器)
curl http://127.0.0.1:8765/sse

# 远程测试 (通过域名)
curl https://jinli.dajiayouxuan.com/mcp

# 预期响应
event: endpoint
data: /messages/?session_id=xxxxx
```

---

## 环境变量配置

| 变量 | 必需 | 值 |
|------|------|-----|
| `JD_APP_KEY` | ✅ | `d51d12fb9411f97ca19a724530729950` |
| `JD_APP_SECRET` | ✅ | `d939d5b59ca547ba934bb9d7656eb527` |
| `JD_PID` | ✅ | `1000138638_4100368453_3003539490` |
| `DB_PATH` | ❌ | `/data/jd_saver.db` (默认) |

---

## 部署步骤 (供他人复用)

### 1. Oracle 服务器部署

```bash
# 创建目录
sudo mkdir -p /www/docker/jd-saver

# 上传代码 (从本地)
scp -r jd-saver/ ubuntu@144.24.11.95:/www/docker/

# 启动容器
cd /www/docker/jd-saver/docker
docker compose up -d --build

# 验证
curl http://127.0.0.1:8765/sse
```

### 2. 前端反代配置 (122.51.106.193)

```bash
# 添加 upstream
cat >> /www/server/panel/vhost/nginx/0.upstreams.conf << 'EOF'
upstream jd_saver {
    server 10.99.99.2:8765;
    keepalive 16;
}
EOF

# 创建站点配置
cat > /www/server/panel/vhost/nginx/jinli.dajiayouxuan.com.conf << 'EOF'
server {
    listen 80;
    server_name jinli.dajiayouxuan.com;

    location /mcp {
        proxy_pass http://jd_saver/sse;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
EOF

# 重载 nginx
nginx -t && nginx -s reload
```

### 3. DNS 配置

```
jinli.dajiayouxuan.com → EdgeOne CDN
  或直连 → 122.51.106.193
```

### 4. Poke Recipe 发布

```bash
# 方式1: 使用隧道 (开发环境)
npx poke@latest tunnel http://localhost:8765/mcp -n "jd-saver" --recipe

# 方式2: 配置远程 MCP
# 在 poke.com/kitchen 添加 MCP: https://jinli.dajiayouxuan.com/mcp
```

---

## 性能优化要点

| 优化点 | 实现方式 |
|--------|----------|
| **API 缓存** | 内存 TTL 缓存 300s，相同 SKU 不重复调用 |
| **SQLite WAL** | 高并发读写，不锁表 |
| **连接复用** | httpx AsyncClient 复用 TCP 连接 |
| **异步 I/O** | 全部 async/await，单进程处理多请求 |
| **无状态设计** | 服务无状态，可水平扩展 |

---

## 数据库选型说明

- **SQLite**（默认）：零运维、单文件备份、足够支持几十万用户
- **MySQL**：不推荐，额外成本和维护负担
- **Redis**（可选）：仅做热点缓存，不替代 SQLite 持久化

---

## 后续优化建议

1. **添加 Redis 缓存层**：高并发时减少 SQLite 压力
2. **实现 Promtail 日志采集**：对接 Loki 日志平台
3. **添加 Prometheus 监控**：暴露 MCP 指标
4. **实现用户认证**：JWT Token 验证
5. **添加配额限制**：防止恶意调用

---

## GitHub 仓库

```bash
# 克隆代码
git clone https://github.com/lixuehan/jd-saver.git
cd jd-saver

# 查看文档
cat README.md
cat ARCHITECTURE.md
```

---

## 联系与维护

- 项目路径: `/www/docker/jd-saver/` (Oracle)
- 日志查看: `docker logs jd-saver -f`
- 重启服务: `docker compose restart`
- 数据库位置: `/data/jd_saver.db`
