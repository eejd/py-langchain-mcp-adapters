"""Exercise the MCP 2 transports against a real local server."""

import asyncio
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from fastmcp import FastMCP


server = FastMCP("adapter-test")


@server.tool
def add(a: int, b: int) -> int:
    return a + b


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["stdio", "http"])
async def test_mcp2_add(transport):
    from langchain_mcp_adapters.client import MultiServerMCPClient

    process = None
    if transport == "stdio":
        connection = {"transport": "stdio", "command": sys.executable,
                      "args": [str(Path(__file__).resolve()), "stdio"]}
    else:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                                    "http", str(port)])
        try:
            for _ in range(100):
                try:
                    reader, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.close()
                    await writer.wait_closed()
                    break
                except OSError:
                    await asyncio.sleep(0.05)
            else:
                raise RuntimeError("MCP HTTP server did not start")
        except BaseException:
            process.terminate()
            process.wait(timeout=5)
            raise
        connection = {"transport": "streamable_http",
                      "url": f"http://127.0.0.1:{port}/mcp"}
    try:
        client = MultiServerMCPClient({"local": connection})
        tools = await client.get_tools()
        add_tool = next(tool for tool in tools if tool.name == "add")
        result = await add_tool.ainvoke({"a": 19, "b": 23})
        assert "42" in str(result)
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=5)


@pytest.mark.asyncio
async def test_to_fastmcp_executes_langchain_tool():
    from langchain_core.tools import tool
    from langchain_mcp_adapters.tools import to_fastmcp

    @tool
    def add_values(a: int, b: int) -> int:
        """Add two values."""
        return a + b

    result = await to_fastmcp(add_values).run({"a": 19, "b": 23})
    assert "42" in str(result)


if __name__ == "__main__":
    if sys.argv[1] == "stdio":
        server.run(transport="stdio", show_banner=False)
    else:
        server.run(transport="http", host="127.0.0.1", port=int(sys.argv[2]), show_banner=False)
