# 京东联盟开发文档

本目录存放京东联盟（京东联盟开放平台）的开发 SDK 和参考文档。

## 文件说明

| 文件 | 说明 |
|------|------|
| `python3-sdk/` | Python 3 官方 SDK（已解压，可直接参考 API 参数） |
| `jd-api-sdk-python3-20260826.zip` | Python 3 SDK 原始压缩包 |
| `jd-api-sdk-python-20260826.zip` | Python 2 SDK 原始压缩包（仅供参考） |
| `jd-api-sdk-java-20260826.zip` | Java SDK 原始压缩包 |
| `jd-api-sdk-php-20260826.zip` | PHP SDK 原始压缩包 |

## 项目已使用的 API 接口

当前 `server/jd_api.py` 已实现以下接口调用：

| API 名称 | 方法 | 用途 |
|----------|------|------|
| `jd.union.open.goods.material.query` | UnionOpenGoodsMaterialQueryRequest | 查商品素材（含优惠券） |
| `jd.union.open.goods.link.query` | UnionOpenGoodsLinkQueryRequest | 转链生成推广链接 |
| `jd.union.open.mcp.goods.query` | UnionOpenMcpGoodsQueryRequest | MCP 商品搜索 |
| `jd.union.open.mcp.promotion.get` | UnionOpenMcpPromotionGetRequest | 获取促销码/凑单方案 |
| `jd.union.open.mcp.goods.snapshop.query` | UnionOpenMcpGoodsSnapshopQueryRequest | 查询商品快照（价格追踪） |

## 相关 API（未实现，参考 SDK）

### 价格追踪相关
- `UnionOpenGoodsSnapshopQueryRequest` — `jd.union.open.goods.snapshop.query`

### 组合/凑单优惠
- `UnionOpenGoodsCombinationQueryRequest` — `jd.union.open.goods.combination.query`（组合优惠查询，可用于实现 `jd_get_combo_scheme`）
- `UnionOpenMcpPromotionRedpacketGetRequest` — `jd.union.open.mcp.promotion.redpacket.get`

### 优惠券相关
- `UnionOpenCouponQueryRequest` — `jd.union.open.coupon.query`（已有，在 jd_api.py 中）

## 如何使用 SDK 参考

Python SDK 的 Request 类格式为参考标准，参数结构如下：

```python
# 示例：UnionOpenGoodsMaterialQueryRequest
class UnionOpenGoodsMaterialQueryRequest(RestApi):
    def getapiname(self):
        return 'jd.union.open.goods.material.query'
    
    # GoodsReq 参数：
    # skuId, pid, hasCoupon, fields, subUnionId 等
```

本项目直接使用 `httpx` + MD5 签名，不依赖 SDK，但可参考 SDK 中的参数定义确保字段名正确。

## 官方文档入口

- 京东联盟开放平台：https://union.jd.com/openplatform/
- API 列表：https://union.jd.com/openplatform/console/apiList

## Python3 SDK 目录结构

```
python3-sdk/
├── ReadMe.md                      # SDK 使用说明
├── jd/
│   ├── __init__.py
│   ├── api/
│   │   ├── base.py                # 基础 API 类（签名/请求逻辑）
│   │   └── rest/                  # 所有接口 Request 类
│   │       ├── UnionOpenGoodsMaterialQueryRequest.py   # 查商品素材
│   │       ├── UnionOpenGoodsLinkQueryRequest.py       # 转链
│   │       ├── UnionOpenMcpGoodsQueryRequest.py        # MCP 商品搜索
│   │       ├── UnionOpenMcpPromotionGetRequest.py      # 促销码
│   │       ├── UnionOpenMcpGoodsSnapshopQueryRequest.py # 商品快照
│   │       ├── UnionOpenGoodsCombinationQueryRequest.py # 组合优惠
│   │       ├── UnionOpenCouponQueryRequest.py          # 优惠券查询
│   │       └── ...（共 ~70+ 个接口）
│   └── security/                  # TDE 加密（敏感数据加密）
```
