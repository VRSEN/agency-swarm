# Observability

Agency Swarm supports [Helicone](https://www.helicone.ai/), an observability platform for LLM applications that offers:

- Request logging and monitoring
- Cost tracking
- Latency measurements
- Advanced analytics

## Setup

1. **Sign up** for a Helicone account at [helicone.ai](https://www.helicone.ai/).
2. **Obtain your Helicone API key** from the dashboard.
3. **Enable Helicone tracking** by adding your API key to your environment variables:

   ```env
   HELICONE_API_KEY=your_helicone_api_key
   ```

## How It Works

When Agency Swarm detects the `HELICONE_API_KEY` in your environment variables, it automatically:

- Routes all OpenAI API requests through Helicone's proxy endpoint (`https://oai.hconeai.com/v1`).
- Adds the necessary Helicone authentication headers.
- Enables logging and monitoring of all LLM interactions.

No additional code changes are required for standard agent operations—just set your Helicone API key, and Agency Swarm handles the rest.

## Tracking OpenAI API Requests in Custom Tools

For manual OpenAI API requests inside your custom tools (since Assistants API calls are tracked automatically), use the pre-configured OpenAI client from Agency Swarm to ensure Helicone tracking:

```python
from agency_swarm import get_openai_client

client = get_openai_client()
```

This client automatically routes requests through Helicone when `HELICONE_API_KEY` is set, ensuring your manual API calls are tracked.

## Viewing Your Data

Access your Agency Swarm LLM interactions in the Helicone dashboard:

1. Log into your Helicone account.
2. Navigate to the dashboard.
3. View metrics, logs, and analytics for your requests.

This provides insights into your agents' performance, costs, and behavior.
