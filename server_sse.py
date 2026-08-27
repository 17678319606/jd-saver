"""
SSE 入口 - 用于 poke tunnel 远程部署
docker run 时默认启动此模式
"""
import os
import re
import sys
from starlette.responses import PlainTextResponse, JSONResponse, RedirectResponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import mcp
from server.metrics import metrics
from server.short_links import ShortLinkDatabase


def _build_app():
    app = mcp.http_app()

    from starlette.routing import Route, Mount

    async def metrics_endpoint(request):
        """Prometheus metrics endpoint"""
        return PlainTextResponse(content=metrics.get_prometheus_text())

    async def health_endpoint(request):
        """Health check endpoint"""
        return JSONResponse(content={
            "status": "ok",
            "uptime": int(metrics._start_time),
            "port": int(os.environ.get("MCP_PORT", "8765")),
        })

    _SKU_ID_PATTERN = re.compile(r"^(\d+)$")

    async def promo_redirect(request):
        """短链接 302 重定向到京东联盟推广链接"""
        sku_id = request.path_params.get("sku_id", "")
        if not _SKU_ID_PATTERN.match(sku_id):
            return JSONResponse({"error": "invalid sku_id"}, status_code=400)

        db = ShortLinkDatabase(os.environ.get("DB_PATH", "./jd_saver.db"))
        try:
            await db.connect()
            original_url = await db.get_original_url(sku_id)
            if not original_url:
                return JSONResponse({"error": "link not found"}, status_code=404)
            await db.increment_click(sku_id)
        finally:
            await db.close()

        return RedirectResponse(url=original_url, status_code=302)

    # Add custom routes
    app.routes.append(Route("/metrics", metrics_endpoint))
    app.routes.append(Route("/health", health_endpoint))
    app.routes.append(Route("/api/promo/{sku_id}", promo_redirect))

    return app


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("MCP_PORT", "8765"))
    app = _build_app()
    uvicorn.run(app, host="0.0.0.0", port=port)
