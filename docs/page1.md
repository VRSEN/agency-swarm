# Google Colab Guide

### [Assistant API](https://platform.openai.com/docs/assistants/overview/agents) working


The Assistant API is quite different from the previous chat completions approach. In this new Api, there are threads that represent conversations, messages that represent individual messages within the threads, and agents that execute the threads to generate new messages.
It can be a bit confusing. So, the general process is as follows: 
1. Create an agent. 
2. Create a thread. 
3. Add a message to the thread. 
4. After that, you have to create a run for this thread and agent ids. 
The big change here is that runs execute asynchronously, so you have to continuously check for the updates until the run is finished. 
5. Once that's done, if the run is in completed status, the run goes into requires_action or completed status. 

If it is, completed it means that you safely retrieve the thread with the new assistant message, when if it in requires_action, it means that you have to run your function, pass the output back and run the thread again. 

Get completion.
But to simplify the entire process and make it familiar for all of us who are used to the previous version of the OpenAI API, I have created a function called get_completion that essentially goes through all the steps that I have just described until the final assistant response is received. 
Check out the doc string for more details, because you might wanna copy this function for your own projects.

{get completion} 

### Coding Agent

Now let's go ahead and create our first code assistant agent, which will be responsible for generating and executing code locally. We'll begin with the tools that this agent will utilize, defined with the instructor library. 

The first tool is `ExecutePyFile`,
class ExecutePyFile(OpenAISchema):
```python
    """Run existing python file from local disc."""

    file_name: str = Field(

        ..., description="The path to the .py file to be executed."

    )
```
 will run an existing Python file from the disk, taking the file name as a parameter. 

### Capturing outputs and errors
In the `run` function inside this model, we'll execute the file with Python 3 using the subprocess module and capture any outputs or errors. 
```python
 def run(self):

      """Executes a Python script at the given file path and captures its output and errors."""

      try:

          result = subprocess.run(

              ['python3', self.file_name],

              text=True,

              capture_output=True,

              check=True

          )

          return result.stdout

      except subprocess.CalledProcessError as e:

          return f"An error occurred: {e.stderr}"
         
```
Our second function, named `File`, serves to write a file onto the disk for later execution. 



Accurate function descriptions are crucial here; and as you can see by using the {instructor} library, you can define them directly in the docstrings or the field descriptions associated with each specific parameter, which is extremely convenient.
```python
class File(OpenAISchema):

    """

    Python file with an appropriate name, containing code that can be saved and executed locally at a later time. This environment has access to all standard Python packages and the internet.

    """

    chain_of_thought: str = Field(...,

        description="Think step by step to determine the correct actions that are needed to be taken in order to complete the task.")

    file_name: str = Field(

        ..., description="The name of the file including the extension"

    )

    body: str = Field(..., description="Correct contents of a file")

  

    def run(self):

        with open(self.file_name, "w") as f:

            f.write(self.body)

  

        return "File written to " + self.file_name
```

### Chain of thought

We will also add an additional parameter 'chain of thought'. This is another ingenious technique introduced by Jason Liu.
This parameter forces the model to map out each action, step by step before, proceeding with the function execution itself.
This increases accuracy.


Next, we'll add both of these functions into an array to be used later in our get completion function and create our code assistant using the new beta assistants API. 

```python
from openai import OpenAI

client = OpenAI(api_key=openai.api_key)

  

code_assistant_funcs = [File, ExecutePyFile]

  

code_assistant = client.beta.assistants.create(

  name='Code Assistant Agent',

  instructions="As a top-tier programming AI, you are adept at creating accurate Python scripts. You will properly name files and craft precise Python code with the appropriate imports to fulfill the user's request. Ensure to execute the necessary code before responding to the user.",

  model="gpt-4-1106-preview",

  tools=[{"type": "function", "function": File.openai_schema},

         {"type": "function", "function": ExecutePyFile.openai_schema},]

)
```

### Design 

This system is designed by following a typical Cubernetes cluster architecture, where the user proxy agent is essentially acting as a load balancer that distributes requests to specialized individual agents and converses with them until the task is executed. 

### Tools

The only tool that the user proxy agent will need is a sendMessage tool to send messages to other agents. 
It has two parameters: a recipient and a message. The run call in this function actually calls our previous method, getCompletion, with a separate thread for each agent, making our system sort of recusrsive. I say sort of because it has only one level of recursion, after the main loop that also uses the getCompletion function. 

To ensure that our proxy agent has a separate conversation with each of the other agents in the group chat, we will store separate threads for each agent in a global object called agents_and_threads. 

```python
agents_and_threads = {

    "code_assistant": {

        "agent": code_assistant,

        "thread": None,

        "funcs": code_assistant_funcs

    }

}
```

### Instructions User proxy agent

Finally, we can define the user proxy agent itself with some instructions. The most important part here is that the user proxy agent must maintain ongoing communication with other agents until the task is completed. This parameter has a huge impact on the behaviour of the whole system, so definitely make sure to play around with that. 

To launch this system, simply create a new thread and start an infinite loop that prompts for a user message, gets a completion from the user proxy agent and prints a response. Now we are ready to test. 

```python
thread = client.beta.threads.create()

while True:

  user_message = input("User: ")

  

  message = get_completion(user_message, user_proxy, user_proxy_tools, thread)

  

  wprint(f"\033[34m{user_proxy.name}: ", message,'\033[0m')
```

### Result

The user proxy agent immediately calls the code agent with a given task.  After the code assistant agent writes the code to the file, it executes and returns the current date to the user proxy assistant, which then prints it for us below. So in this conversation, the user proxy agent converses with other agents through the send message function. Basically when it needs to chat with another agent, it calls this function with the message, which the other agent than receives as the user message. After the other agent responds, we pass it back as the output of the send message function. This allows for a more natural conversation flow, where the user proxy agent can chat with the other agents as much as needed directly from the main chat with the user. Let's try to run the second question. Compare the year-to-date gain for Meta and Tesla. Now the user proxy agent immediately asks the code assistant to provide the YTD gain, and then the code assistant proceeds with creating the chain of thought prompt and writing the code itself. As you can see, it gets it on the first try and returns the actual numbers using the yFinance library. 


For the final question let s ask the user proxy to plot the stock price change and save it to the stockpriceytd.png file. After the Code Assistant executes the necessary code, the User Proxy confirms that the file has been successfully saved. You can verify this by browsing the files on the left. As you can see, the resulting graph looks exactly like the one generated by AutoGen. However, our system actually did in far less tokens wasted. 

Then, after running all the cells again, run the main loop, and your second task execution assistant should now be operational. In conclusion, the best thing about creating custom agent swarms with the assistants API is that they're actually usable in production. Unlike other multi-agent systems, here you have complete control over the creation of new agents and tools. You can easily add any guardrails for you specific use case or even implement any custom logic, making this system easily steerable and adaptable. For instance, I decided to design this example with the Single Responsibility Principle in mind. This is a common practice for building scalable systems, and it implies that each component should have only one specific responsibility, which allows for easy addition of more components or replacement of the existing ones in case of any errors.
