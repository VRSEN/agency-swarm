# Open-Source Models Support

While OpenAI models are recommended, Agency Swarm supports open-source models through projects that mimic the Assistants API.

## Supported Projects

- **Astra Assistants API**: Best option for running open-source models. Supports Assistants API V2.
- **Open Assistant API**: Fully local and stable, supports Assistants API V1.

## Integration Steps

1. **Install Required Packages**:
   ```bash
   pip install astra-assistants-api gradio   ```

2. **Set Up API Clients**:
   ```python
   from openai import OpenAI
   from astra_assistants import patch
   from agency_swarm import set_openai_client

   client = patch(OpenAI())
   set_openai_client(client)   ```

3. **Create Agents with Open-Source Models**:
   ```python
   ceo = Agent(name="CEO", model='ollama/llama3')   ```

4. **Run the Agency**:
   ```python
   agency = Agency([ceo])
   agency.run_demo()   ```

## Limitations

- **Function Calling**: Not supported by most open-source models.
- **Retrieval-Augmented Generation**: Often limited; consider custom implementations.
- **Code Interpreter**: Not supported in current open-source assistants. 