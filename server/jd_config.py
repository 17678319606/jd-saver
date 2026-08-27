"""
京东联盟配置 & URL 解析工具
"""
import os
from dataclasses import dataclass
from typing import Optional
import re


@dataclass
class JDConfig:
    app_key: str = ""
    app_secret: str = ""
    top_url: str = "https://api.jd.com/routerjson"
    pid: str = ""           # 推广位，格式 e.g. "1000138638_4100368453_3003539490"
    sub_union_id: str = ""  # 子推广位 ID（可选）
    access_token: str = ""  # 用户 token（可选，转链可用）

    @classmethod
    def from_env(cls) -> "JDConfig":
        return cls(
            app_key=os.environ.get("JD_APP_KEY", ""),
            app_secret=os.environ.get("JD_APP_SECRET", ""),
            top_url=os.environ.get("JD_TOP_URL", "https://api.jd.com/routerjson"),
            pid=os.environ.get("JD_PID", ""),
            sub_union_id=os.environ.get("JD_SUB_UNION_ID", ""),
            access_token=os.environ.get("JD_ACCESS_TOKEN", ""),
        )


def extract_sku_id(jd_url: str) -> Optional[str]:
    """从京东商品链接中提取 skuId"""
    # 匹配 ?skuId=123456 或 &skuId=123456
    m = re.search(r"[?&]skuId=(\d+)", jd_url)
    if m:
        return m.group(1)
    # 匹配 item.jd.com/123456.html
    m = re.search(r"item\.jd\.com/(\d+)", jd_url)
    if m:
        return m.group(1)
    # 匹配 /item/123456.html
    m = re.search(r"/item/(\d+)\.html", jd_url)
    if m:
        return m.group(1)
    return None


def parse_jd_url(url: str) -> dict:
    """解析京东 URL，返回结构化信息"""
    sku_id = extract_sku_id(url)
    return {
        "original_url": url,
        "sku_id": sku_id,
        "is_jd_url": bool(sku_id or "jd.com" in url),
    }
