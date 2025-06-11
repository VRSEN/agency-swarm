from mcp.server.fastmcp import FastMCP

# Create server
mcp = FastMCP("Echo Server", log_level="INFO", port=7860)

@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

@mcp.tool()
def get_secret_password() -> str:
    return "hc1291cb7123"

if __name__ == "__main__":
    mcp.run(transport="streamable-http")