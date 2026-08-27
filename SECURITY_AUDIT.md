# 京东省钱助手 MCP Server — 架构安全审计与优化建议

> 审计时间：2026-08-28  
> 审计范围：`server/` 全量源码 + `server_sse.py` + `docker/`

---

## 一、安全审计

### 🔴 高风险

#### S1. 敏感凭证硬编码风险（已缓解但需确认）

**现状**：JD 密钥通过环境变量注入，未在代码中硬编码，✅ 符合规范。  
**但**：`.env.example` 必须确认未被提交到 Git。

```bash
# 检查：确保 .env 文件在 .gitignore 中
grep '\.env$' .gitignore
```

若 `.env` 已被意外提交，立即执行：
```bash
git rm --cached .env
git commit -m "Remove .env from tracking"
git push --force-with-lease
# 随后轮换所有 JD_APP_KEY / JD_APP_SECRET / JD_ACCESS_TOKEN
```

---

#### S2. 缺少 API 调用频率限制（Rate Limiting）

**问题**：当前对 `jd_get_coupon`、`jd_generate_promo_link` 等工具无频率限制，恶意调用可导致：
- 京东联盟账号被限流或封禁
- 服务端资源耗尽（每次调用都发 HTTP 请求）

**建议修复**：

```python
# server/ratelimit.py (新增)
import asyncio
from collections import defaultdict
from typing import Dict

class RateLimiter:
    def __init__(self, max_calls: int = 10, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window = window_seconds
        self._calls: Dict[str, list] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def acquire(self, key: str) -> bool:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            timestamps = self._calls[key]
            # 清除窗口外的记录
            self._calls[key] = [t for t in timestamps if now - t < self.window]
            if len(self._calls[key]) >= self.max_calls:
                return False
            self._calls[key].append(now)
            return True
```

然后在 `__main__.py` 每个 tool 入口处加装饰器检查。

---

#### S3. 用户输入未做长度/格式校验

**问题**：`link` 参数直接传入 `parse_jd_url()`，若传入极长字符串（如几千字符）可能造成 DoS。

```python
# 建议：在 __main__.py 开头加基础校验
if not isinstance(link, str) or len(link) > 2000:
    return {"success": False, "error": "链接格式无效或过长"}
```

---

### 🟡 中风险

#### S4. `/metrics` 端点无认证

**问题**：`/metrics` 和 `/health` 当前完全开放，任何能访问该 URL 的人可读取：
- API 调用次数（业务量情报）
- 服务器启动时间（推断运行时长）
- 缓存命中率

**建议**：若暴露于公网，加基础认证或限制来源 IP。

```python
# server_sse.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/metrics", "/health"):
            auth = request.headers.get("authorization", "")
            expected = f"Bearer {os.environ.get('METRICS_TOKEN', '')}"
            if expected and auth != expected:
                return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

app.add_middleware(AuthMiddleware)
```

---

#### S5. SQLite WAL 文件可能暴露

**问题**：WAL 模式下会产生 `.db-wal` 和 `.db-shm` 文件，若 Docker 卷挂载不当可能持久化到宿主机。

**建议**：在 `docker-compose.yml` 中使用匿名卷或 tmpfs：
```yaml
volumes:
  - ./data:/app/data  # 仅映射到应用数据目录，而非宿主机路径
```

---

#### S6. `user_id` 参数可被伪造

**问题**：所有 tool 的 `user_id` 默认为 `"anonymous"`，且无校验。若前端直接传任意字符串，会写入数据库，造成数据污染。

**建议**：
```python
import re
def sanitize_user_id(uid: str) -> str:
    uid = (uid or "anonymous").strip()
    if len(uid) > 64:
        uid = uid[:64]
    uid = re.sub(r'[^\w\-@.]', '', uid)  # 仅允许字母数字及常见符号
    return uid or "anonymous"
```

---

### 🟢 低风险 / 信息

| 编号 | 问题 | 建议 |
|------|------|------|
| S7 | 日志用 `print()` 而非结构化日志 | 引入 `logging` 模块，便于对接 Loki/ELK |
| S8 | `metrics.py` 内存直方图无限增长 | 已有限制 1000 条，✅ 合理 |
| S9 | 错误信息直接返回给前端（如 API 异常详情） | 生产环境应泛化错误消息，隐藏内部实现细节 |

---

## 二、边界测试评估

### 测试矩阵

| 场景 | 当前行为 | 风险评估 | 建议 |
|------|----------|----------|------|
| 空 `link` 字符串 | 返回 "无法提取 SKU ID" ✅ | 低 | 增加类型校验 |
| 非京东 URL（如 `https://taobao.com/x`） | `sku_id=None`，返回错误 ✅ | 低 | — |
| `user_id` 为空字符串 | 默认为 `"anonymous"` ✅ | 低 | 考虑拦截空值 |
| `target_price` 为负数 | 会正常插入 DB ⚠️ | 中 | 校验 `target_price > 0` |
| `target_price` 极大（如 999999） | 逻辑上无意义但不会崩溃 | 低 | 加合理范围限制 |
| `limit` 超出预期（如 10000） | SQL LIMIT 接受大值，加载全部数据 ⚠️ | 中 | 限制 `limit <= 100` |
| 并发写同一 SKU 提醒 | SQLite WAL 模式处理写冲突 ✅ | 低 | — |
| 数据库文件损坏 | 无恢复机制 ⚠️ | 高 | 加自动备份或定期 dump |

### 边界测试用例建议

```python
# 建议在 test/ 目录下添加
async def test_empty_link(): ...
async def test_invalid_sku_format(): ...
async def test_negative_target_price(): ...
async def test_oversized_limit(): ...
async def test_duplicate_alert_same_user_sku(): ...
async def test_concurrent_price_alert_updates(): ...
```

---

## 三、性能审查

### 瓶颈分析

| 项目 | 现状 | 瓶颈等级 | 优化建议 |
|------|------|----------|----------|
| **京东 API 延迟** | 每次调用 ~1-3s | 🔴 高 | 已实现 TTL 缓存（300s），覆盖率需验证 |
| **缓存 key 设计** | `method:md5(sorted_params)` | 🟡 中 | `jd_get_coupon` 使用 `sku_id` 直接作 key（`cache.get("coupon", sku_id)`），但其他函数未统一；建议全部改用规范化 key |
| **轮询间隔** | 固定 5 分钟 | 🟢 低 | 可改为指数退避（无 alert 时延长间隔） |
| **SQLite 并发写** | WAL + synchronous=NORMAL | 🟢 低 | 适合当前规模，用户量大时考虑迁移 PostgreSQL |
| **`invalidate_sku` 线性扫描** | `for k,v in store.items()` | 🟡 中 | 建立 `sku_id → set(keys)` 索引，O(1) 清除 |
| **无连接池** | 每次 tool 调用新建 httpx client | 🟡 中 | 复用 client 或使用 `httpx.AsyncClient` 单例 |

### 缓存 Key 不一致问题

`cache.py` 的 `_key()` 方法使用 `(method, params)` 哈希，但 `__main__.py` 调用时直接传 `sku_id` 作为 params：

```python
# __main__.py L45 — 正确用法
cached = cache.get("coupon", sku_id)

# jd_api.py 中的函数没有调用 cache（缓存由 __main__.py 层控制）
# 但 mcp_search_goods 等其他调用若绕过 __main__.py 直接调用 jd_api，缓存将失效
```

**建议**：将缓存逻辑下沉到 `jd_api.py` 内部，或在文档中明确缓存只应在 `__main__.py` 层使用。

---

## 四、功能完整性检查

### 已实现功能 ✅

| 功能 | 状态 |
|------|------|
| 查隐藏优惠券 | ✅ `jd_get_coupon` |
| 生成推广链接（转链） | ✅ `jd_generate_promo_link` |
| 综合省钱方案（凑单推荐） | ✅ `jd_find_deals` |
| 设置降价提醒 | ✅ `jd_set_price_alert` |
| 查询历史价格 | ✅ `jd_query_history` |
| 更新最低价 | ✅ `jd_update_min_price` |
| 短链接数据库映射 | ✅ `short_links.py` |
| Prometheus 指标 | ✅ `/metrics` |
| 健康检查 | ✅ `/health` |
| 数据清理工具 | ✅ `cleanup.py` |
| Docker 部署 | ✅ `docker-compose.yml` |
| nginx 配置（外部） | ✅ 已在服务器上部署 |

### 未实现 / 待完善功能 ⚠️

| 功能 | 状态 | 说明 |
|------|------|------|
| 短链接实际 302 路由 | ⚠️ 待验证 | `short_links.py` 已写好，但 nginx 侧需要新增 location 规则：`location /go/ { rewrite ^/go/(.*)$ /redirect/$1 last; }` 并配合服务端 handler |
| 降价提醒实际通知 | ⚠️ 当前为空操作 | `mark_notified()` 只标记 DB，无外部推送；用户已决定取消 Poke 通知，但需确认替代方案（邮件？Webhook？） |
| 后端管理 API | ❌ 缺失 | 无 REST API 供前端查询提醒列表、历史价格图表 |
| 单元测试 | ❌ 缺失 | 无 `test/` 目录，无法 CI/CD |
| 输入校验中间件 | ❌ 缺失 | 见 S2/S3 |
| 日志轮转 | ❌ 缺失 | `print()` 输出到 stdout，Docker 日志不限制大小 |

---

## 五、代码级修改建议（优先级排序）

### P0 — 立即修复

**1. 加输入校验（`server/__main__.py`）**

```python
import re

def validate_link(link: str) -> Optional[str]:
    """返回 sku_id 或 error dict"""
    if not isinstance(link, str) or not link.strip():
        return {"success": False, "error": "链接不能为空"}
    if len(link) > 2000:
        return {"success": False, "error": "链接过长"}
    parsed = parse_jd_url(link)
    if not parsed["sku_id"]:
        return {"success": False, "error": "无法识别商品链接，请粘贴京东商品页完整 URL"}
    return None  # 表示校验通过
```

**2. 限制 `limit` 参数（`jd_query_history`）**

```python
async def jd_query_history(sku_id: str, limit: int = 30) -> dict:
    if not isinstance(limit, int) or limit < 1 or limit > 100:
        limit = 30
    ...
```

**3. 校验 `target_price` 正数（`jd_set_price_alert`）**

```python
if target_price <= 0:
    return {"success": False, "error": "目标价格必须大于 0"}
```

### P1 — 近期修复

**4. 统一缓存 key 策略**：将 `cache.get/set` 的调用方式规范化，避免后续维护者混淆。

**5. 添加 `rate_limit.py`**：对核心工具加每分钟 N 次限制。

**6. 日志结构化**：替换 `print()` 为 `logging.info/warning/error`。

### P2 — 长期优化

**7. 短链接 nginx 路由**：需在 frontend 服务器 nginx 配置中添加：
```nginx
location ~ ^/go/(\d+)$ {
    internal;  # 只允许后端代理访问，防止直接访问
    proxy_pass http://10.99.99.2:8765/api/promo/$1;
}
```

**8. 降级提醒通知渠道**：虽然取消了 Poke，建议至少保留 email 或 webhook 扩展点，便于未来接入。

---

## 六、总结

| 维度 | 评分 | 主要问题 |
|------|------|----------|
| 安全性 | 🟡 中 | 缺 rate limit、输入校验弱、metrics 无鉴权 |
| 稳定性 | 🟢 良 | WAL 模式、异常处理较完整，但缺备份机制 |
| 可维护性 | 🟢 良 | 模块划分清晰，缓存/DB/API 分离合理 |
| 功能完整性 | 🟡 中 | 核心功能完备，短链接路由和通知环节待补全 |
| 性能 | 🟢 良 | 缓存覆盖核心 API，WAL 优化到位，小并发场景无问题 |

**总体评价**：架构设计合理，关键安全项已规避（密钥不进代码、佣金信息已过滤）。主要短板在于**防御纵深不足**——缺少输入校验、限流、认证三道防线，建议优先修复 P0 项。
