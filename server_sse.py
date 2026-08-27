"""
SSE 入口 - 用于 poke tunnel 远程部署
docker run 时默认启动此模式
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import mcp

if __name__ == "__main__":
    port = int(os.environ.get("MCP_PORT", "8765"))
    mcp.run(transport="sse", host="0.0.0.0", port=port)
