import sys

from fastmcp import FastMCP

# Create the MCP server
mcp = FastMCP("STDIO Example Server")


@mcp.tool()
def greet(name: str) -> str:
    """Greet a user by name"""
    return f"Hello, {name}! Welcome to the STDIO server."


@mcp.tool()
def add(a: int, b: int) -> str:
    """Add two numbers and return the result"""
    return f"The sum of {a} and {b} is {a + b}."


if __name__ == "__main__":
    # Keep stdout clean for JSONRPC: mcp 2.x rejects non-JSON lines.
    print("Starting MCP server with STDIO transport...", file=sys.stderr)
    # The run() method uses stdio by default
    mcp.run()
