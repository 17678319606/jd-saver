"""
京东联盟 API 调用封装
敏感信息（佣金率、佣金金额）在内部使用，不暴露给前端
"""
import hashlib
import json
import time
from typing import Optional
import httpx

from .jd_config import JDConfig


def _generate_sign(params: dict, app_secret: str) -> str:
    """生成京东联盟 API 签名（对齐官方 SDK 实现）"""
    # 按 SDK 要求排序参数并拼接
    keys = sorted(params.keys())
    str_parameters = app_secret + "".join(f"{k}{params[k]}" for k in keys) + app_secret
    # 使用 latin1 编码（与 SDK 一致）
    return hashlib.md5(str_parameters.encode("latin1")).hexdigest().upper()


async def _call_api(
    client: httpx.AsyncClient,
    config: JDConfig,
    method: str,
    params: dict,
    access_token: Optional[str] = None,
) -> dict:
    """通用京东联盟 API 调用"""
    # 时间戳格式必须包含毫秒和时区（与 SDK 一致）
    # 强制使用北京时间（+0800）以避免容器时区问题
    import os
    os.environ.setdefault('TZ', 'Asia/Shanghai')
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S.000+0800", time.localtime())

    sys_params = {
        "app_key": config.app_key,
        "access_token": access_token or config.access_token or "",
        "timestamp": timestamp,
        "v": "1.0",
        "format": "json",
        "sign_method": "md5",
        "360buy_param_json": json.dumps(params, ensure_ascii=False),
    }

    sys_params["sign"] = _generate_sign(sys_params, config.app_secret)

    # 使用 form data 发送（与 SDK 一致）
    resp = await client.post(
        config.top_url,
        data=sys_params,
        timeout=15.0,
    )
    resp.raise_for_status()
    result = resp.json()

    err = result.get("error_response")
    if err:
        raise RuntimeError(f"JD API error {err.get('code')}: {err.get('msg')}")

    return result.get("result", {})


# ==================== 核心 API ====================

async def gen_promo_link(
    client: httpx.AsyncClient,
    config: JDConfig,
    url: str,
    scene_id: int = 1,
) -> dict:
    """生成推广链接（转链）"""
    return await _call_api(client, config, "jd.union.open.goods.link.query", {
        "goodsReq": {
            "@type": "com.jd.union.open.gateway.api.dto.goods.link.LinkGoodsReq",
            "url": url,
            "pid": config.pid,
            "subUnionId": config.sub_union_id,
            "sceneId": scene_id,
        }
    })


async def query_goods_material(
    client: httpx.AsyncClient,
    config: JDConfig,
    sku_id: str,
) -> dict:
    """
    查询商品素材（含优惠券信息）
    返回的数据经过过滤，不暴露佣金细节
    """
    result = await _call_api(client, config, "jd.union.open.goods.material.query", {
        "goodsReq": {
            "@type": "com.jd.union.open.gateway.api.dto.goods.material.MaterialGoodsReq",
            "skuId": sku_id,
            "pid": config.pid,
            "hasCoupon": True,
            "fields": "id,title,imageUrl,jdPrice,couponInfo",
        }
    })

    # 过滤敏感信息
    coupon_info = result.get("couponInfo", {})
    if isinstance(coupon_info, dict):
        # 移除佣金相关字段
        coupon_info.pop("commissionInfo", None)
        coupon_info.pop("commissionRate", None)
        coupon_info.pop("commission", None)
        result["couponInfo"] = coupon_info

    # 移除顶层佣金信息
    result.pop("commissionInfo", None)
    result.pop("commissionRate", None)
    result.pop("commission", None)

    return result


async def query_coupon_info(
    client: httpx.AsyncClient,
    config: JDConfig,
    sku_id: str,
) -> dict:
    """查询优惠券详情"""
    return await _call_api(client, config, "jd.union.open.coupon.query", {
        "couponUrls": f"https://item.jd.com/{sku_id}.html",
    })


async def mcp_search_goods(
    client: httpx.AsyncClient,
    config: JDConfig,
    keyword: str,
    page_index: int = 1,
    page_size: int = 10,
) -> dict:
    """MCP 商品搜索"""
    return await _call_api(client, config, "jd.union.open.mcp.goods.query", {
        "goodsReq": {
            "@type": "com.jd.union.open.gateway.api.dto.mcp.GoodsReq",
            "keyword": keyword,
            "pageIndex": page_index,
            "pageSize": page_size,
            "pid": config.pid,
            "fields": "id,title,imageUrl,jdPrice,couponInfo",
        }
    })


async def get_mcp_promotion(
    client: httpx.AsyncClient,
    config: JDConfig,
    material_id: str,
) -> dict:
    """获取促销码 / 凑单优惠方案"""
    return await _call_api(client, config, "jd.union.open.mcp.promotion.get", {
        "promotionCodeReq": {
            "@type": "com.jd.union.open.gateway.api.dto.mcp.PromotionCodeReq",
            "materialId": material_id,
            "pid": config.pid,
        }
    })


async def query_goods_snapshot(
    client: httpx.AsyncClient,
    config: JDConfig,
    sku_id: str,
) -> dict:
    """查询商品快照（用于价格追踪）"""
    return await _call_api(client, config, "jd.union.open.mcp.goods.snapshop.query", {
        "snapShopGoodsReq": {
            "@type": "com.jd.union.open.gateway.api.dto.mcp.SnapShopGoodsReq",
            "skuId": sku_id,
            "pid": config.pid,
        }
    })


# ==================== 新增 API ====================

async def search_goods(
    client: httpx.AsyncClient,
    config: JDConfig,
    keyword: str,
    page_index: int = 1,
    page_size: int = 10,
    shop_types: Optional[str] = None,
    sort_name: Optional[str] = None,
    sort_order: int = 1,
    price_from: Optional[float] = None,
    price_to: Optional[float] = None,
) -> dict:
    """
    通用商品搜索（支持自营筛选、价格区间、排序）

    shop_types: "1"=自营, "2"=商家店铺（可传 "1,2" 多选）
    sort_name: 排序字段 "price"/"salesCount"/"commission"
    sort_order: 1=升序, 2=降序
    """
    params: dict = {
        "@type": "com.jd.union.open.gateway.api.dto.mcp.GoodsReq",
        "keyword": keyword,
        "pageIndex": page_index,
        "pageSize": page_size,
        "pid": config.pid,
        "fields": "id,title,imageUrl,jdPrice,couponInfo,salesCount,shopType,commentCount",
    }
    if shop_types:
        params["shopTypes"] = shop_types
    if sort_name:
        params["sortName"] = sort_name
        params["sort"] = sort_order
    if price_from is not None:
        params["priceFrom"] = price_from
    if price_to is not None:
        params["priceTo"] = price_to
    return await _call_api(client, config, "jd.union.open.mcp.goods.query", {"goodsReq": params})


async def query_goods_recommend(
    client: httpx.AsyncClient,
    config: JDConfig,
    sku_id: str,
) -> dict:
    """根据商品 SKU 推荐相关商品（凑单/搭配推荐）"""
    return await _call_api(client, config, "jd.union.open.goods.recommend.query", {
        "recommendGoodsReq": {
            "@type": "com.jd.union.open.gateway.api.dto.goods.recommend.RecommendGoodsReq",
            "skuId": sku_id,
            "sceneId": 1,
        }
    })


async def query_goods_combination(
    client: httpx.AsyncClient,
    config: JDConfig,
    sku_id: str,
) -> dict:
    """
    组合优惠查询（真正的凑单方案）
    返回可以一起购买享受额外优惠的商品列表
    """
    return await _call_api(client, config, "jd.union.open.goods.combination.query", {
        "goodsReq": {
            "@type": "com.jd.union.open.gateway.api.dto.goods.combination.CombinationGoodsReq",
            "skuId": sku_id,
            "pid": config.pid,
            "needClickUrl": True,
            "pageIndex": 1,
            "pageSize": 10,
        }
    })


async def query_goods_comment_summary(
    client: httpx.AsyncClient,
    config: JDConfig,
    sku_id: str,
) -> dict:
    """
    查询商品评论摘要（好评率、差评关键词）
    用于过滤差评率高的商品
    """
    return await _call_api(client, config, "biz.product.commentSummarys.query", {
        "sku": sku_id,
    })
