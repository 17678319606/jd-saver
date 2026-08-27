# Poke Recipe 发布指南

## 当前状态

MCP 服务已部署: `https://jinli.dajiayouxuan.com/mcp`

## 发布步骤

### 方法 1: 浏览器手动添加（推荐）

1. 打开 https://poke.com/integrations/new
2. 填写:
   - **Server URL**: `https://jinli.dajiayouxuan.com/mcp`
   - **Name**: `JD Saver`
3. 保存后，用户可以在对话中使用 MCP 工具

### 方法 2: CLI 添加

```bash
# 需要先登录 Poke
poke login

# 添加 MCP 服务器
poke mcp add https://jinli.dajiayouxuan.com/mcp --name "JD Saver"
```

### 方法 3: 创建 Recipe（分享链接）

```bash
# 本地开发时使用隧道
npx poke@latest tunnel http://localhost:8765/mcp --name "jd-saver" --recipe
```

## Recipe 内容建议

### 名称
```
京东省钱助手
```

### 描述
```
查询京东优惠券、生成推广链接、设置降价提醒、追踪历史价格
```

### Onboarding Context
```
你是一个京东购物助手，可以帮助用户：
1. 查询京东商品的隐藏优惠券
2. 生成带佣金的推广链接（短链接）
3. 设置价格降价提醒
4. 查询商品历史价格

使用示例：
- "查一下这个商品的优惠券：https://item.jd.com/12345678.html"
- "帮我转链：https://item.jd.com/12345678.html"
- "设置降价提醒，目标价 199 元"
```

### 首条消息
```
你好！我是京东省钱助手，可以帮你查询优惠券、设置降价提醒。试试发送一个京东商品链接给我吧！
```

## MCP 工具列表

| 工具 | 说明 |
|------|------|
| `jd_get_coupon` | 查隐藏优惠券 |
| `jd_generate_promo_link` | 转链生成短链接 |
| `jd_find_deals` | 综合省钱方案 |
| `jd_set_price_alert` | 设置降价提醒 |
| `jd_query_history` | 查询历史价格 |
| `jd_update_min_price` | 更新最低价 |
| `jd_get_combo_scheme` | 凑单优惠方案 |

## 发布后验证

1. 在 Poke 中发送消息测试工具是否正常
2. 检查短链接重定向是否工作
3. 确认价格提醒功能正常
