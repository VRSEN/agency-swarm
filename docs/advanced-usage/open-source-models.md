# Open Source Models

While OpenAI is generally recommended, there are situations where you might prefer open-source models. The following projects offer alternatives by mimicking the Assistants API:

### ✅ Tested Projects
- [Astra Assistants API](https://github.com/datastax/astra-assistants-api) - The best and the easiest option for running Open Source models. Supports Assistants API V2. See example [notebook](https://github.com/VRSEN/agency-swarm/blob/main/notebooks/os_models_with_astra_assistants_api.ipynb).
- [Open Assistant API](https://github.com/MLT-OSS/open-assistant-api) - Fully local, stable and tested, but only supports Assistants V1. See example [here](https://github.com/VRSEN/agency-swarm-lab/tree/main/OpenSourceSwarm)

### 🔜 Other Projects
- [OpenOpenAI](https://github.com/transitive-bullshit/OpenOpenAI) - Unverified.
- [LiteLLM](https://github.com/BerriAI/litellm/issues/2842) - Assistants API Proxy in development.

## Astra Assistants API

To use agency-swarm with Astra Assistants API, follow these steps:

**1. Create an account on [Astra Assistants API](https://astra.datastax.com/signup) and obtain an API key.**

![Astra Assistants API Example](https://firebasestorage.googleapis.com/v0/b/vrsen-ai/o/public%2Fgithub%2FScreenshot%202024-07-01%20at%208.19.00%E2%80%AFAM.png?alt=media&token=b4f1a7ad-3b77-40fa-a5da-866a4f1410bd)

**2. Add Astra DB Token to your .env file:**  
    Copy token from the file that starts with "AstraCS:" and paste it into your .env file.

```env
ASTRA_DB_APPLICATION_TOKEN=AstraCS:dsfkgn...
```

**3. Add other model provider API keys to .env as well:**

```env
PERPLEXITYAI_API_KEY=your_perplexityai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
TOGETHER_API_KEY=your_together_api_key
GROQ_API_KEY=your_groq_api_key
```

**4. Install the Astra Assistants API and gradio:**
    
```bash
pip install astra-assistants-api gradio
```
   
**5. Patch the OpenAI client:**

```python
from openai import OpenAI
from astra_assistants import patch
from agency_swarm import set_openai_client
from dotenv import load_dotenv

load_dotenv()

client = patch(OpenAI())

set_openai_client(client)
```

**6. Create an agent:**  
    Create an agent and replace the model parameter with the name of the model you want to use. With Astra Assistants you can upload files like usual using `files_folder`.

```python
from agency_swarm import Agent

ceo = Agent(name="ceo", 
            description="I am the CEO", 
            model='ollama/llama3',
            # model = 'perplexity/llama-3-8b-instruct'
            # model = 'anthropic/claude-3-5-sonnet-20240620'
            # model = 'groq/mixtral-8x7b-32768'
            # model="gpt-4o",
            files_folder="path/to/your/files"
            )
```

**7. Create an agency:**  

You can add more agents as needed, just make sure all manager agents support function calling.

```python
from agency_swarm import Agency

agency = Agency([ceo])
```

**8. Start gradio:**  

To utilize your agency in gradio, apply a specific non-streaming `demo_gradio` method from the [agency-swarm-lab](https://github.com/VRSEN/agency-swarm-lab/blob/main/OpenSourceSwarm/demo_gradio.py) repository:

```python
from agency_swarm import Agency
from .demo_gradio import demo_gradio

agency = Agency([ceo])

demo_gradio(agency)
```

**For a complete example, see the [notebook](https://github.com/VRSEN/agency-swarm/blob/main/notebooks/os_models_with_astra_assistants_api.ipynb).**

## General Instructions

To use agency-swarm with any other projects that mimic the Assistants API, generally, you need to follow these steps:

**1. Install the previous version of agency-swarm as most projects are not yet compatible with streaming and Assistants V2:**

```bash
pip install agency-swarm==0.1.7
```

**2. Switch out the OpenAI client:**

```python
import openai
from agency_swarm import set_openai_client

client = openai.OpenAI(api_key="whatever", base_url="http://127.0.0.1:8000/")

set_openai_client(client)
```

**3. Set the model parameter:**

```python
from agency_swarm import Agent

ceo = Agent(name="ceo", description="I am the CEO", model='ollama/llama3')
```

**4. Start Gradio:**  

To utilize your agency in gradio, apply a specific non-streaming `demo_gradio` method from the [agency-swarm-lab](https://github.com/VRSEN/agency-swarm-lab/blob/main/OpenSourceSwarm/demo_gradio.py) repository:

```python
from agency_swarm import Agency
from .demo_gradio import demo_gradio

agency = Agency([ceo])

demo_gradio(agency)
```

**5. For backend integrations, simply use:**

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