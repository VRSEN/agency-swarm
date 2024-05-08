# Open Source Models

While OpenAI is generally recommended, there are situations where you might prefer open-source models. The following projects offer alternatives by mimicking the Assistants API:

### ✅ Tested Projects
- [Open Assistant API](https://github.com/MLT-OSS/open-assistant-api) - Stable and tested, but currently has [one bug needing resolution](https://github.com/MLT-OSS/open-assistant-api/issues/61). This is currently the best option for open-source models.

### 🔜 Other Projects
- [Astra Assistants API](https://github.com/datastax/astra-assistants-api) - Under development, facing [some issues with tool logic](https://github.com/datastax/astra-assistants-api/issues/27).
- [OpenOpenAI](https://github.com/transitive-bullshit/OpenOpenAI) - Unverified, but likely operational.
- [LiteLLM](https://github.com/BerriAI/litellm/issues/2842) - Assistants API Proxy in development, potentially the preferred choice once stable.

## Using Open Source Models

To integrate open-source models with this framework, install the previous version of agency-swarm as most projects are not yet compatible with streaming and Assistants V2.

```bash
pip install agency-swarm==0.1.7
```

Next, switch out the OpenAI client:

```python
import openai
from agency_swarm import set_openai_client

client = openai.OpenAI(api_key="whatever", base_url="http://127.0.0.1:8000/")

set_openai_client(client)
```

and the model parameter:

```python
from agency_swarm import Agent

ceo = Agent(name="ceo", description="I am the CEO", model='ollama/llama3')
```

To utilize your agency in gradio, apply a specific non-streaming `demo_gradio` method from the [agency-swarm-lab](https://github.com/VRSEN/agency-swarm-lab/blob/main/OpenSourceSwarm/demo_gradio.py) repository:

```python
from agency_swarm import Agency
from .demo_gradio import demo_gradio

agency = Agency([ceo])

demo_gradio(agency)
```

For backend integrations, simply use:

```python
agency.get_completion("I am the CEO")
```

## Limitations

- **Function calling is not supported by most open-source models**: This limitation prevents the agent from communicating with other agents in the agency. So, it must be positioned at the end of the agency chart and cannot utilize any tools.
- **RAG is typically limited**: Most open-source assistants API implementations have restricted Retrieval-Augmented Generation capabilities. It is recommended to develop a custom tool with your own vector database.
- **CodeInterpreter is not supported**: The Code Interpreter feature is still under development for all open-source assistants API implementations.

## Future Plans

Updates will be provided as new open-source assistant API implementations stabilize. 

If you successfully integrate other projects with agency-swarm, please share your experience through an issue or pull request.