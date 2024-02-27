# Azure OpenAI

Many organizations are concerned about data privacy and sharing their data with OpenAI. However, using Azure ensures that your data is processed in a secure environment, allowing you to utilize the OpenAI API without even sharing data with OpenAI itself.

## Prerequisites

Before you begin, ensure that you have the following:

- An Azure account with an active subscription. [Create an account here](https://azure.microsoft.com/en-us/free/).
- Approved access to the OpenAI Service on Azure.
- An Azure OpenAI resource created in [one of the available regions](https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models#assistants-preview) and a model deployed to it.
- Enpoint URL and API key for the OpenAI resource.

## Using Azure OpenAI

To use Azure OpenAI, you need to change OpenAI client with AzureOpenAI client. Here is an example of how you can do it in agency swarm:

```python
from openai import AzureOpenAI
from agency_swarm import set_openai_client

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    api_version="2024-02-15-preview",
    azure_endpoint=os.getenv("AZURE_ENDPOINT"),
    timeout=5,
    max_retries=5,
)

set_openai_client(client)
```

Then, you also have to replace `model` parameter inside each agent with your model deployment name from Azure. Here is an example of how you can do it:

```python
ceo = Agent(name="ceo", description="I am the CEO", model='azure-model-deployment-name')
```

Then, you can run your agency as usual:

```python
agency = Agency([ceo])
agency.run_demo()
```

!!! warning "Retrieval is not supported yet"
    Currently, Azure OpenAI does not support the `Retrieval` tool. You can only use `CodeInterpreter` or custom tools made with the `BaseTool` class.

## Example Notebook

You can find an example notebook for using Azure OpenAI in the [notebooks folder](https://github.com/VRSEN/agency-swarm/blob/main/notebooks/azure.ipynb).