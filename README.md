# JD Saver - 京东省钱助手

基于 FastMCP 的京东联盟优惠助手，通过 Poke Recipe 分发。

## 功能

- 🔍 查隐藏优惠券
- 🔗 CPS 转链赚佣金
- 💰 综合省钱方案（券+凑单）
- 🔔 降价提醒
- 📈 历史价格追踪

## 快速开始（本地开发）

```bash
cd jd-saver
pip install -r requirements.txt

# 配置环境变量
export JD_APP_KEY=your_key
export JD_APP_SECRET=your_secret
export JD_PID=123456_1000

# 启动（stdio 模式，WorkBuddy 直接调用）
python -m server
```

## Docker 部署（Oracle 服务器）

```bash
cd docker
cp .env.example .env  # 填入凭证
docker compose up -d --build

# 另开隧道用于 poke recipe
npx poke@latest tunnel http://localhost:8765/mcp -n "jd-saver" --recipe
```

## MCP 工具列表

| 工具 | 说明 |
|------|------|
| `jd_get_coupon` | 查优惠券 |
| `jd_generate_promo_link` | 转链 |
| `jd_find_deals` | 综合省钱方案 |
| `jd_set_price_alert` | 降价提醒 |
| `jd_query_history` | 历史价格 |
| `jd_update_min_price` | 更新最低价 |
| `jd_get_combo_scheme` | 凑单优惠方案 |

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `JD_APP_KEY` | ✅ | 京东联盟 App Key |
| `JD_APP_SECRET` | ✅ | 京东联盟 App Secret |
| `JD_PID` | ✅ | 推广位 PID（如 123456_1000） |
| `DB_PATH` | ❌ | SQLite 路径，默认 `./jd_saver.db` |
