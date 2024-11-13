# Contributing to Agency Swarm

We welcome contributions to Agency Swarm! Here's how you can contribute:

## Contributing Agents and Tools

- **Agents**: Place new agents in the `agency_swarm/agents/` directory within an appropriate category.
- **Tools**: Add new tools to the `agency_swarm/tools/` directory under a relevant category.

## Folder Structure

- **Agents**:
  ```
  agency_swarm/agents/your_agent_category/AgentName/
  ├── __init__.py
  ├── AgentName.py
  ├── instructions.md
  └── tools/
      ├── ToolName.py
      └── ...  ```

- **Tools**:
  ```
  agency_swarm/tools/your_tool_category/
  ├── __init__.py
  ├── ToolName.py
  └── ...  ```

## Adding Tests

- **Location**: Place tests in the `agency_swarm/tests/` directory.
- **Example**:
  ```python
  def test_my_custom_tool():
      tool = MyCustomTool(input_field="test")
      result = tool.run()
      assert "expected_output" in result  ```

## Submitting Changes

1. **Fork the Repository**: Create a fork of the Agency Swarm repository.
2. **Create a Branch**: Work on a feature branch for your changes.
3. **Submit a Pull Request**: Describe your changes and submit a PR for review.

## Guidelines

- **Code Quality**: Follow PEP 8 style guidelines.
- **Documentation**: Update or add documentation for your contributions.
- **Testing**: Ensure all new and existing tests pass. 