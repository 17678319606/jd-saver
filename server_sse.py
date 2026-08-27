"""
SSE 入口 - 用于 poke tunnel 远程部署
docker run 时默认启动此模式
"""
import os
import sys
from starlette.responses import PlainTextResponse, JSONResponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import mcp
from server.metrics import metrics


def _build_app():
    app = mcp.http_app()

    from starlette.routing import Route

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

    # Add custom routes
    app.routes.append(Route("/metrics", metrics_endpoint))
    app.routes.append(Route("/health", health_endpoint))

    return app


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("MCP_PORT", "8765"))
    app = _build_app()
    uvicorn.run(app, host="0.0.0.0", port=port)
