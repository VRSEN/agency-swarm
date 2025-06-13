from agency_swarm.tools.mcp import MCPServerStreamableHttp

client = MCPServerStreamableHttp(
    params={"url": "http://localhost:7860/mcp", "headers": {"Authorization": "Bearer 123"}},
)

if __name__ == "__main__":
    response = client.call_tool("ExampleTool", {"input": "Test"})
    print(f"ExampleTool response: {response.content[0].text}")

    response = client.call_tool("TestTool", {"input": "Test"})
    print(f"TestTool response: {response.content[0].text}")