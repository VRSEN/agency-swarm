# Observability

Agency Swarm supports tracking your agents using Langchain callbacks. This allows you to monitor and analyze the behavior and performance of your agents.

To use tracking with Langchain callbacks, you need to install the langchain package:

```bash
pip install langchain
```

## Langfuse

Langfuse is an observability platform that allows you to track and analyze the execution of your agents in detail. It provides features like tracing, metrics, and debugging tools.

To use Langfuse with Agency Swarm, follow these steps:

1. Install the langfuse package:

```bash
pip install langfuse
```

2. Set the LANGFUSE_SECRET_KEY and LANGFUSE_PUBLIC_KEY environment variables:

```bash
export LANGFUSE_SECRET_KEY=<your-secret-key>
export LANGFUSE_PUBLIC_KEY=<your-public-key>
```

You can get your keys from the [Langfuse dashboard](https://cloud.langfuse.com/).

3. Initialize the tracking in your code:

```python
from agency_swarm import init_tracking

init_tracking("langfuse")
```

You can pass additional configuration options to the Langfuse callback handler:

```python
init_tracking(
    "langfuse",
    debug=True,
    host="custom-host",
    user_id="user-123",
)
```

For additional parameters and more information on the Langfuse callback handler, see the [Langfuse documentation](https://langfuse.com/docs/integrations/langchain/tracing#add-langfuse-to-your-langchain-application).

## Local

The local tracker provides a lightweight solution for logging agent activities to a SQLite database.

To use the local tracker, simply initialize it in your code:

```python
from agency_swarm import init_tracking

init_tracking("local")
```

This will create a SQLite database in the current working directory.

For custom database location:

```python
from agency_swarm import init_tracking

init_tracking("local", db_path="path/to/your/database.db")
```
