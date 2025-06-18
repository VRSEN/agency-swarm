from agents import function_tool


@function_tool
def sample_tool(text: str) -> str:
    """Echo tool that returns the input text."""
    return f"Echo: {text}"
