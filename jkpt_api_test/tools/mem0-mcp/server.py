import os
from mcp.server.fastmcp import FastMCP
from mem0 import MemoryClient

# MemoryClient = 走云端 API，数据存在 mem0 服务器
client = MemoryClient(api_key=os.environ["MEM0_API_KEY"])
mcp = FastMCP("mem0")

@mcp.tool()
def add_memory(text: str, user_id: str = "tongmeina") -> str:
    client.add(text, user_id=user_id)
    return "ok"

@mcp.tool()
def search_memory(query: str, user_id: str = "tongmeina", limit: int = 5) -> list:
    results = client.search(query, user_id=user_id, limit=limit)
    return [r.get("memory", str(r)) for r in results]

if __name__ == "__main__":
    mcp.run()