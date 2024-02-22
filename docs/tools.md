# Advanced Tools

All tools in Agency Swarm are created using [Instructor](https://github.com/jxnl/instructor). 

The only difference is that you must extend the `BaseTool` class and implement the `run` method. For many great examples on what you can create, checkout [Instructor Cookbook](https://jxnl.github.io/instructor/examples/).

## Converting [Validated Citations Tool from Instructor](https://jxnl.github.io/instructor/examples/exact_citations/#the-fact-class)

This is an example of an extremely useful tool for RAG applications. It allows your agents to not only answer questions based on context, but also to provide the exact citations for the answers. This way you can be sure that the information is always accurate and reliable.

```python




```


---


## ToolFactory Class

Import in 1 line of code from [Langchain](https://python.langchain.com/docs/integrations/tools) (not recommended):

!!! warning "Not recommended"  
    This method is not recommended, as it does not provide the same level of type checking, error correction and tool descriptions as Instructor. However, it is still possible to use this method if you prefer.

    ```python
    from langchain.tools import YouTubeSearchTool
    from agency_swarm.tools import ToolFactory
    
    LangchainTool = ToolFactory.from_langchain_tool(YouTubeSearchTool)
    ```
    
    ```python
    from langchain.agents import load_tools
    
    tools = load_tools(
        ["arxiv", "human"],
    )
    
    tools = ToolFactory.from_langchain_tools(tools)
    ```

Convert from OpenAPI schemas:

```python
# using local file
with open("schemas/your_schema.json") as f:
    tools = ToolFactory.from_openapi_schema(
        f.read(),
    )

# using requests
tools = ToolFactory.from_openapi_schema(
    requests.get("https://api.example.com/openapi.json").json(),
)
```