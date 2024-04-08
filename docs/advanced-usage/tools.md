# Advanced Tools

All tools in Agency Swarm are created using [Instructor](https://github.com/jxnl/instructor). 

The only difference is that you must extend the `BaseTool` class and implement the `run` method with your logic inside. For many great examples on what you can create, checkout [Instructor Cookbook](https://jxnl.github.io/instructor/examples/).

---

## Example: Converting [Answering Questions with Validated Citations Example](https://jxnl.github.io/instructor/examples/exact_citations/) from Instructor 

This is an example of how to convert an extremely useful tool for RAG applications from instructor. It allows your agents to not only answer questions based on context, but also to provide the exact citations for the answers. This way your users can be sure that the information is always accurate and reliable.


### Original Instructor library implementation


```python
from agency_swarm.tools import BaseTool, BaseModel
from pydantic import Field, model_validator, FieldValidationInfo
from typing import List
import re

class Fact(BaseModel):
    fact: str = Field(...)
    substring_quote: List[str] = Field(...)
    
    @model_validator(mode="after")
    def validate_sources(self, info: FieldValidationInfo) -> "Fact":
        text_chunks = info.context.get("text_chunk", None)
        spans = list(self.get_spans(text_chunks))
        self.substring_quote = [text_chunks[span[0] : span[1]] for span in spans]
        return self

    def get_spans(self, context):
        for quote in self.substring_quote:
            yield from self._get_span(quote, context)

    def _get_span(self, quote, context):
        for match in re.finditer(re.escape(quote), context):
            yield match.span()

class QuestionAnswer(BaseModel):
    question: str = Field(...)
    answer: List[Fact] = Field(...)

    @model_validator(mode="after")
    def validate_sources(self) -> "QuestionAnswer":
        self.answer = [fact for fact in self.answer if len(fact.substring_quote) > 0]
        return self
```

!!! note "Context Retrieval"
    In the original Instructor example, [the context is passed into the prompt beforehand](https://jxnl.github.io/instructor/examples/exact_citations/#the-ask_ai-function), which is typical for standard non-agent LLM applications. However, in the context of Agency Swarm, we must allow the agents to retrieve the context themselves.

### Agency Swarm Implementation

To allow your agents to retrieve the context themselves, we must split `QuestionAnswer` into two separate tools: `QueryDatabase` and `AnswerQuestion`. We must also retrieve context from `shared_state`, as the context is not passed into the prompt beforehand, and `FieldValidationInfo` is not available in the `validate_sources` method.

#### The `QueryDatabase` tool will:

1. Check if the context is already retrieved in `shared_state`. If it is, raise an error. (This means that the agent retrieved the context twice, without answering the question in between, which is most likely a hallucination.)
2. Retrieve the context and save it to the `shared_state`.
3. Return the context to the agent, so it can be used to answer the question.

```python
class QueryDatabase(BaseTool):
    """Use this tool to query a vector database to retrieve the relevant context for the question."""
    question: str = Field(..., description="The question to be answered")
    
    def run(self):
        # Check if context is already retrieved 
        if self.shared_state.get("context", None) is not None:
            raise ValueError("Context already retrieved. Please proceed with the AnswerQuestion tool.")
        
        # Your code to retrieve the context here
        context = "This is a test context"
        
        # Then, save the context to the shared state
        self.shared_state.set("context", context)
        
        return f"Context retrieved: {context}.\n\n Please proceed with the AnswerQuestion tool."

```

!!! note "Shared State"
    `shared_state` is a state that is shared between all tools, across all agents. It allows you to control the execution flow, share data, and provide instructions to the agents based on certain conditions or actions performed by other agents. 

#### The `AnswerQuestion` tool will:

1. Check if the context is already retrieved. If it is not, raise an error. (This means that the agent is trying to answer the question without retrieving the context first.)
2. Use the context from the `shared_state` to answer the question with a list of facts.
3. Remove the context from the `shared_state` after the question is answered. (This is done, so the next  question can be answered with a fresh context.)


```python
class AnswerQuestion(BaseTool):
    answer: str = Field(..., description="The answer to the question, based on context.")
    sources: List[Fact] = Field(..., description="The sources of the answer")
    
    def run(self):
        # Remove the context after question is answered
        self.shared_state.set("context", None)
        
        # additional logic here as needed, for example save the answer to a database
        
        return "Success. The question has been answered." # or return the answer, if needed
    
    @model_validator(mode="after")
    def validate_sources(self) -> "QuestionAnswer":
        # In "Agency Swarm", context is directly extracted from `shared_state`
        context = self.shared_state.get("context", None)  # Highlighting the change
        if context is None:
            # Additional check to ensure context is retrieved before proceeding
            raise ValueError("Please retrieve the context with the QueryDatabase tool first.")
        self.answer = [fact for fact in self.answer if len(fact.substring_quote) > 0]
        return self
    

```

#### The `Fact` tool

The `Fact` tool will stay primarily the same. The only difference is that we must extract the context from the `shared_state` inside the `validate_sources` method. The `run` method is not needed, as this tool only validates the input from the model.

```python
class Fact(BaseTool):
    fact: str = Field(...)
    substring_quote: List[str] = Field(...)
    
    def run(self):
        pass
    
    @model_validator(mode="after")
    def validate_sources(self) -> "Fact":
        context = self.shared_state.get("context", None)  
        text_chunks = context.get("text_chunk", None)
        spans = list(self.get_spans(text_chunks))
        self.substring_quote = [text_chunks[span[0] : span[1]] for span in spans]
        return self

    # Methods `get_spans` and `_get_span` remain unchanged

```


### Conclusion

To implement tools with Instructor in Agency Swarm, generally, you must:

1. Extend the `BaseTool` class.
2. Add fields with types and clear descriptions, plus the tool description itself.
3. Implement the `run` method with your execution logic inside.
4. Add validators and checks based on various conditions. 
5. Split tools into smaller tools to give your agents more control, as needed.


---


## ToolFactory Class

Tool factory is a class that allows you to create tools from different sources. You can create tools from Langchain, OpenAPI schemas. However, it is preferable to implement tools from scratch using Instructor, as it gives you a lot more control.

### Import from Langchain

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

### Convert from OpenAPI schemas

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

---

## PRO Tips

1. Use enumerators or Literal types instead of strings to allow your agents to perform only certain actions or commands, instead of executing any arbitrary code. This makes your whole system a lot more reliable.

    ```python
    class RunCommand(BaseTool):
        command: Literal["start", "stop"] = Field(...)
   
       def run(self):
            if command == "start":
                subprocess.run(["start", "your_command"])
            elif command == "stop":
                subprocess.run(["stop", "your_command"])
            else:
                raise ValueError("Invalid command")
    ```


2. Provide additional instructions to the agents in the `run` method of the tool as function outputs. This allows you to control the execution flow, based on certain conditions.

    ```python
    class QueryDatabase(BaseTool):
        question: str = Field(...)
   
        def run(self):
            # query your database here
            context = query_database(self.question)
   
            if context is None:
                raise ValueError("No context found. Please propose to the user to change the topic.")
            else:
                self.shared_state.set("context", context)
                return "Context retrieved. Please proceed with explaining the answer."
    ``` 
3. Use `shared_state` to validate actions taken by other agents, before allowing them to proceed with the next action.

    ```python
    class Action2(BaseTool):
        input: str = Field(...)
   
        def run(self):
            if self.shared_state.get("action_1_result", None) is "failure":
                raise ValueError("Please proceed with the Action1 tool first.")
            else:
                return "Success. The action has been taken."
    ```
4. Consider `one_call_at_a_time` class attribute to prevent multiple instances of the same tool from running at the same time. This is useful when you want your agents to see the results of the previous action before proceeding with the next one.

    ```python
    class Action1(BaseTool):
        input: str = Field(...)
        one_call_at_a_time: bool = True
   
        def run(self):
            # your code here
    ```
