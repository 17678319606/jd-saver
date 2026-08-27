"""
京东联盟 Open API 调用封装
基于 jos-php-open-api-sdk-2.0 的 Python 实现
对应 JdClient + UnionOpenGoodsLinkQueryRequest 等
"""
import hashlib
import json
import time
from typing import Optional
import httpx

from .jd_config import JDConfig


def _generate_sign(params: dict, app_secret: str) -> str:
    """
    生成京东联盟 API 签名（MD5）
    算法：sort by key, concat appSecret + k+v + appSecret, md5 uppercase
    """
    sorted_params = dict(sorted(params.items()))
    s = app_secret
    for k, v in sorted_params.items():
        if k == "360buy_param_json":
            s += k + v
        else:
            s += k + str(v)
    s += app_secret
    return hashlib.md5(s.encode("utf-8")).hexdigest().upper()


async def _call_api(
    client: httpx.AsyncClient,
    config: JDConfig,
    method: str,
    params: dict,
    access_token: Optional[str] = None,
) -> dict:
    """通用京东联盟 API 调用"""
    now = int(time.time() * 1000)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now / 1000))

    sys_params = {
        "app_key": config.app_key,
        "access_token": access_token or config.access_token or "",
        "timestamp": timestamp,
        "v": "2.0",
        "format": "json",
        "sign_method": "md5",
        "360buy_param_json": json.dumps(params, ensure_ascii=False),
    }

    sys_params["sign"] = _generate_sign(sys_params, config.app_secret)

    resp = await client.post(
        config.top_url,
        params=sys_params,
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
    """
    生成推广链接（转链）
    API: jd.union.open.goods.link.query
    """
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
    fields: str = "id,title,imageUrl,jdPrice,couponInfo,commissionInfo",
) -> dict:
    """
    查询商品素材（含隐藏优惠券 + 佣金）
    API: jd.union.open.goods.material.query
    """
    return await _call_api(client, config, "jd.union.open.goods.material.query", {
        "goodsReq": {
            "@type": "com.jd.union.open.gateway.api.dto.goods.material.MaterialGoodsReq",
            "skuId": sku_id,
            "pid": config.pid,
            "hasCoupon": True,
            "fields": fields,
        }
    })


async def query_coupon_info(
    client: httpx.AsyncClient,
    config: JDConfig,
    sku_id: str,
) -> dict:
    """
    查询优惠券详情
    API: jd.union.open.coupon.query
    """
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
    """
    MCP 商品搜索（关键词搜商品，返回可推广的佣金信息）
    API: jd.union.open.mcp.goods.query
    """
    return await _call_api(client, config, "jd.union.open.mcp.goods.query", {
        "goodsReq": {
            "@type": "com.jd.union.open.gateway.api.dto.mcp.GoodsReq",
            "keyword": keyword,
            "pageIndex": page_index,
            "pageSize": page_size,
            "pid": config.pid,
            "fields": "id,title,imageUrl,jdPrice,couponInfo,commissionInfo",
        }
    })


async def get_mcp_promotion(
    client: httpx.AsyncClient,
    config: JDConfig,
    material_id: str,
) -> dict:
    """
    获取促销码 / 凑单优惠方案
    API: jd.union.open.mcp.promotion.get
    """
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
    """
    查询商品快照（用于价格追踪）
    API: jd.union.open.mcp.goods.snapshop.query
    """
    return await _call_api(client, config, "jd.union.open.mcp.goods.snapshop.query", {
        "snapShopGoodsReq": {
            "@type": "com.jd.union.open.gateway.api.dto.mcp.SnapShopGoodsReq",
            "skuId": sku_id,
            "pid": config.pid,
        }
    })
