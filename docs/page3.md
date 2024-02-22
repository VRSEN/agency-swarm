# Improvements

There are a few things that you can still improve. 

First of all, the current system does not support conversations between the agents that execute the tasks. It only supports the conversation between the user proxy with these agents. This is not necessarily a bad thing; however, because this improves the overall steerability of the system and helps to prevent infinite loops. However, you can easily adjust this, by adding more threads into the agent_and_threads object and also allowing other agents to use the sendMessage function. 

Second, sometimes, it feels like the user proxy agent doesn't fully understand the instructions. I've experimented with the prompt for a bit, but it could certainly use some improvement. And third, as I said before, you could actually make a tool for the user proxy agent that would allow it to create other agents and tools. If you actually manage to do this, I believe it could lead to exponential growth and a complete humanity extinction in the next few months. Now, adding new agents to this system is pretty straightforward. First, create the tools the agent will use with the Pydantic schemas using Instructor. You can simply copy the code for the code assistant agent, replacing any tools as needed. Then, add this new agent to the agents and threads object and create the assistant using the new beta assistants API. 

You can also include out-of-the-box tools like web browsing and code interpreter, but note that the code interpreter can't execute local files and has limitations. After creating your new agent, add its name to the recipient literal in the send message function and describe what this agent should do in the property description. 

### Future Enhancements

 Creation of agencies that can autonomously create other agencies.- DONE
 Asynchronous communication and task handling.                    - DONE
 Inter-agency communication for a self-expanding system