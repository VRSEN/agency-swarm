# Asynchronous Execution

Enhance the performance of your agency by running agents and tools asynchronously.

## Agents Threading

- **Enable Asynchronous Agents**: Set `async_mode` to `'threading'` when initializing the agency.
  ```python
  agency = Agency(agents=[ceo], async_mode='threading')  ```

- **Benefits**: Agents can operate independently without waiting for others to complete tasks.

## Tools Threading

- **Enable Asynchronous Tools**: Set `async_mode` to `'tools_threading'`.
  ```python
  agency = Agency(agents=[ceo], async_mode='tools_threading')  ```

- **Benefits**: Tools execute concurrently, reducing latency for I/O-bound operations.

## Considerations

- **Concurrency Control**: Ensure thread-safe operations to prevent race conditions.
- **Resource Management**: Monitor system resources to avoid overconsumption. 