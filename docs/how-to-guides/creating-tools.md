# Creating Tools

Tools are crucial for extending the functionality of agents. They allow agents to perform actions ranging from simple computations to complex API interactions.

## Steps to Create a Tool

1. **Import Necessary Modules**:
   ```python
   from agency_swarm.tools import BaseTool
   from pydantic import Field
   ```

2. **Define the Tool Class**:
   ```python
   class MyCustomTool(BaseTool):
       """
       Description of what the tool does.
       """
       input_field: str = Field(..., description="Description of the input field.")

       def run(self):
           # Implement the tool's functionality here
           return "Result of the tool operation"
   ```

3. **Add Validators (Optional)**:

   Use Pydantic validators for input validation.

   ```python
   @validator('input_field')
   def check_input(cls, v):
       if not v:
           raise ValueError('Input cannot be empty')
       return v
   ```

4. **Test the Tool**:

   ```python
   if __name__ == "__main__":
       tool = MyCustomTool(input_field="test input")
       print(tool.run())
   ```

For advanced usage and examples, refer to the [Advanced Tools](../advanced-topics/advanced-tools.md) section. 