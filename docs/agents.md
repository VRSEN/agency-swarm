# Agents

### Web browsing Agent

Example From The Video
Testing oai-widget.com

```py
from agency_swarm import set_openai_key
set_openai_key("YOUR_OPENAI_API_KEY")
```
```py
from agency_swarm.agents.browsing import BrowsingAgent
from agency_swarm import Agency, Agent
browsing_agent = BrowsingAgent()
qa_manager = Agent(name="QA Manager",
            description="The QA Manager Agent is an advanced digital entity designed to oversee and enhance the quality of processes for our SaaS product.",
            instructions="As a Quality Assurance (QA) Manager, your role involves direct interaction and oversight of the BrowsingAgent's operations. Your primary duty is to guarantee that the user's task is comprehensively and accurately completed. Achieve this by methodically issuing each step of the task as a distinct message to the BrowsingAgent. It's crucial to confirm the successful execution of one step before advancing to the next. This procedure forms part of an integration test, which will be conducted in a live production environment. Importantly, ensure to provide the BrowsingAgent with the actual credentials related to the task, enabling authentic testing scenarios.")
agency = Agency([qa_manager,
                 [qa_manager, browsing_agent]])
```


```py
demo = agency.demo_gradio(height=700) # reload the notebook each time you run this cell

```

Import from existing agents:

```python
from agency_swarm.agents.browsing import BrowsingAgent

browsing_agent = BrowsingAgent()

browsing_agent.instructions += "\n\nYou can add additional instructions here."