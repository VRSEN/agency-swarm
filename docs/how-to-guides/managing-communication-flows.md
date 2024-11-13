# Managing Communication Flows

Effective communication between agents is essential for collaboration. Agency Swarm allows you to define custom communication flows.

## Defining Communication Flows

- **Agency Chart**: Communication permissions are set using the `agency_chart` parameter in the `Agency` class.
  ```python
  agency = Agency([
      ceo,  # Entry point for user communication
      [ceo, dev],  # CEO can communicate with Developer
      [dev, va],   # Developer can communicate with Virtual Assistant
  ])  ```

- **Directionality**: Communication is directional, established from left to right.

## Best Practices

- **Intentional Design**: Define communication flows that reflect organizational hierarchies or workflows.
- **Limit Unnecessary Access**: Restrict communication paths to prevent information overload or confusion. 