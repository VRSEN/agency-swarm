import inspect
import json
import os
import queue
import threading
import uuid
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Type,
    TypedDict,
    TypeVar,
    Union,
    Tuple,
)

from openai.lib._parsing._completions import type_to_response_format_param
from openai.types.beta.threads import Message
from openai.types.beta.threads.runs import RunStep
from openai.types.beta.threads.runs.tool_call import (
    CodeInterpreterToolCall,
    FileSearchToolCall,
    FunctionToolCall,
    ToolCall,
)
from pydantic import BaseModel, Field, field_validator, model_validator
from rich.console import Console
from typing_extensions import override

from agency_swarm.agents import Agent
from agency_swarm.messages import MessageOutput
from agency_swarm.messages.message_output import MessageOutputLive
from agency_swarm.threads import Thread
from agency_swarm.threads.thread_async import ThreadAsync
from agency_swarm.tools import BaseTool, CodeInterpreter, FileSearch
from agency_swarm.tools.send_message import SendMessage, SendMessageBase
from agency_swarm.user import User
from agency_swarm.util.errors import RefusalError
from agency_swarm.util.files import get_file_purpose, get_tools
from agency_swarm.util.shared_state import SharedState
from agency_swarm.util.streaming import AgencyEventHandler

console = Console()

T = TypeVar("T", bound=BaseModel)


class SettingsCallbacks(TypedDict):
    load: Callable[[], List[Dict]]
    save: Callable[[List[Dict]], Any]


class ThreadsCallbacks(TypedDict):
    load: Callable[[], Dict]
    save: Callable[[Dict], Any]


class Agency:
    def __init__(
        self,
        agency_chart: List,
        thread_strategy: Dict[Literal["always_same", "always_new"], List[Tuple]] = {},
        shared_instructions: str = "",
        shared_files: Union[str, List[str]] = None,
        async_mode: Literal["threading", "tools_threading"] = None,
        send_message_tool_class: Type[SendMessageBase] = SendMessage,
        settings_path: str = "./settings.json",
        settings_callbacks: SettingsCallbacks = None,
        threads_callbacks: ThreadsCallbacks = None,
        temperature: float = 0.3,
        top_p: float = 1.0,
        max_prompt_tokens: int = None,
        max_completion_tokens: int = None,
        truncation_strategy: dict = None,
    ):
        """
        Initializes the Agency object, setting up agents, threads, and core functionalities.

        Parameters:
            agency_chart: The structure defining the hierarchy and interaction of agents within the agency.
            thread_strategy (Dict[Literal["always_same", "always_new"], List[Tuple]], optional): The strategy used for retrieving threads when starting a new conversation. Defaults to "always_same".
            shared_instructions (str, optional): A path to a file containing shared instructions for all agents. Defaults to an empty string.
            shared_files (Union[str, List[str]], optional): A path to a folder or a list of folders containing shared files for all agents. Defaults to None.
            async_mode (str, optional): Specifies the mode for asynchronous processing. In "threading" mode, all sub-agents run in separate threads. In "tools_threading" mode, all tools run in separate threads, but agents do not. Defaults to None.
            send_message_tool_class (Type[SendMessageBase], optional): The class to use for the send_message tool. For async communication, use `SendMessageAsyncThreading`. Defaults to SendMessage.
            settings_path (str, optional): The path to the settings file for the agency. Must be json. If file does not exist, it will be created. Defaults to None.
            settings_callbacks (SettingsCallbacks, optional): A dictionary containing functions to load and save settings for the agency. The keys must be "load" and "save". Both values must be defined. Defaults to None.
            threads_callbacks (ThreadsCallbacks, optional): A dictionary containing functions to load and save threads for the agency. The keys must be "load" and "save". Both values must be defined. Defaults to None.
            temperature (float, optional): The temperature value to use for the agents. Agent-specific values will override this. Defaults to 0.3.
            top_p (float, optional): The top_p value to use for the agents. Agent-specific values will override this. Defaults to None.
            max_prompt_tokens (int, optional): The maximum number of tokens allowed in the prompt for each agent. Agent-specific values will override this. Defaults to None.
            max_completion_tokens (int, optional): The maximum number of tokens allowed in the completion for each agent. Agent-specific values will override this. Defaults to None.
            truncation_strategy (dict, optional): The truncation strategy to use for the completion for each agent. Agent-specific values will override this. Defaults to None.

        This constructor initializes various components of the Agency, including CEO, agents, threads, and user interactions. It parses the agency chart to set up the organizational structure and initializes the messaging tools, agents, and threads necessary for the operation of the agency. Additionally, it prepares a main thread for user interactions.
        """
        self.ceo = None
        self.user = User()
        self.agents = []
        self.agents_and_threads = {}
        self.main_recipients = []
        self.main_thread = None
        self.recipient_agents = None  # for autocomplete
        self.thread_strategy = thread_strategy
        self.shared_files = shared_files if shared_files else []
        self.async_mode = async_mode
        self.send_message_tool_class = send_message_tool_class
        self.settings_path = settings_path
        self.settings_callbacks = settings_callbacks
        self.threads_callbacks = threads_callbacks
        self.temperature = temperature
        self.top_p = top_p
        self.max_prompt_tokens = max_prompt_tokens
        self.max_completion_tokens = max_completion_tokens
        self.truncation_strategy = truncation_strategy

        # set thread type based send_message_tool_class async mode
        if (
            hasattr(send_message_tool_class.ToolConfig, "async_mode")
            and send_message_tool_class.ToolConfig.async_mode
        ):
            self._thread_type = ThreadAsync
        else:
            self._thread_type = Thread

        if self.async_mode == "threading":
            from agency_swarm.tools.send_message import SendMessageAsyncThreading

            print(
                "Warning: 'threading' mode is deprecated. Please use send_message_tool_class = SendMessageAsyncThreading to use async communication."
            )
            self.send_message_tool_class = SendMessageAsyncThreading
        elif self.async_mode == "tools_threading":
            Thread.async_mode = "tools_threading"
            print(
                "Warning: 'tools_threading' mode is deprecated. Use tool.ToolConfig.async_mode = 'threading' instead."
            )
        elif self.async_mode is None:
            pass
        else:
            raise Exception(
                "Please select async_mode = 'threading' or 'tools_threading'."
            )

        if os.path.isfile(
            os.path.join(self._get_class_folder_path(), shared_instructions)
        ):
            self._read_instructions(
                os.path.join(self._get_class_folder_path(), shared_instructions)
            )
        elif os.path.isfile(shared_instructions):
            self._read_instructions(shared_instructions)
        else:
            self.shared_instructions = shared_instructions

        self.shared_state = SharedState()

        self._parse_agency_chart(agency_chart)
        self._init_threads()
        self._create_special_tools()
        self._init_agents()

    def get_completion(
        self,
        message: str,
        message_files: List[str] = None,
        yield_messages: bool = False,
        recipient_agent: Agent = None,
        additional_instructions: str = None,
        attachments: List[dict] = None,
        tool_choice: dict = None,
        verbose: bool = False,
        response_format: dict = None,
    ):
        """
        Retrieves the completion for a given message from the main thread.

        Parameters:
            message (str): The message for which completion is to be retrieved.
            message_files (list, optional): A list of file ids to be sent as attachments with the message. When using this parameter, files will be assigned both to file_search and code_interpreter tools if available. It is recommended to assign files to the most sutiable tool manually, using the attachments parameter.  Defaults to None.
            yield_messages (bool, optional): Flag to determine if intermediate messages should be yielded. Defaults to True.
            recipient_agent (Agent, optional): The agent to which the message should be sent. Defaults to the first agent in the agency chart.
            additional_instructions (str, optional): Additional instructions to be sent with the message. Defaults to None.
            attachments (List[dict], optional): A list of attachments to be sent with the message, following openai format. Defaults to None.
            tool_choice (dict, optional): The tool choice for the recipient agent to use. Defaults to None.
            parallel_tool_calls (bool, optional): Whether to enable parallel function calling during tool use. Defaults to True.
            verbose (bool, optional): Whether to print the intermediary messages in console. Defaults to False.
            response_format (dict, optional): The response format to use for the completion.

        Returns:
            Generator or final response: Depending on the 'yield_messages' flag, this method returns either a generator yielding intermediate messages or the final response from the main thread.
        """
        if verbose and yield_messages:
            raise Exception("Verbose mode is not compatible with yield_messages=True")

        res = self.main_thread.get_completion(
            message=message,
            message_files=message_files,
            attachments=attachments,
            recipient_agent=recipient_agent,
            additional_instructions=additional_instructions,
            tool_choice=tool_choice,
            yield_messages=yield_messages or verbose,
            response_format=response_format,
        )

        if not yield_messages or verbose:
            while True:
                try:
                    message = next(res)
                    if verbose:
                        message.cprint()
                except StopIteration as e:
                    return e.value

        return res

    def get_completion_stream(
        self,
        message: str,
        event_handler: type(AgencyEventHandler),
        message_files: List[str] = None,
        recipient_agent: Agent = None,
        additional_instructions: str = None,
        attachments: List[dict] = None,
        tool_choice: dict = None,
        response_format: dict = None,
    ):
        """
        Generates a stream of completions for a given message from the main thread.

        Parameters:
            message (str): The message for which completion is to be retrieved.
            event_handler (type(AgencyEventHandler)): The event handler class to handle the completion stream. https://github.com/openai/openai-python/blob/main/helpers.md
            message_files (list, optional): A list of file ids to be sent as attachments with the message. When using this parameter, files will be assigned both to file_search and code_interpreter tools if available. It is recommended to assign files to the most sutiable tool manually, using the attachments parameter.  Defaults to None.
            recipient_agent (Agent, optional): The agent to which the message should be sent. Defaults to the first agent in the agency chart.
            additional_instructions (str, optional): Additional instructions to be sent with the message. Defaults to None.
            attachments (List[dict], optional): A list of attachments to be sent with the message, following openai format. Defaults to None.
            tool_choice (dict, optional): The tool choice for the recipient agent to use. Defaults to None.
            parallel_tool_calls (bool, optional): Whether to enable parallel function calling during tool use. Defaults to True.

        Returns:
            Final response: Final response from the main thread.
        """
        if not inspect.isclass(event_handler):
            raise Exception("Event handler must not be an instance.")

        res = self.main_thread.get_completion_stream(
            message=message,
            message_files=message_files,
            event_handler=event_handler,
            attachments=attachments,
            recipient_agent=recipient_agent,
            additional_instructions=additional_instructions,
            tool_choice=tool_choice,
            response_format=response_format,
        )

        while True:
            try:
                next(res)
            except StopIteration as e:
                event_handler.on_all_streams_end()

                return e.value

    def get_completion_parse(
        self,
        message: str,
        response_format: Type[T],
        message_files: List[str] = None,
        recipient_agent: Agent = None,
        additional_instructions: str = None,
        attachments: List[dict] = None,
        tool_choice: dict = None,
        verbose: bool = False,
    ) -> T:
        """
        Retrieves the completion for a given message from the main thread and parses the response using the provided pydantic model.

        Parameters:
            message (str): The message for which completion is to be retrieved.
            response_format (type(BaseModel)): The response format to use for the completion.
            message_files (list, optional): A list of file ids to be sent as attachments with the message. When using this parameter, files will be assigned both to file_search and code_interpreter tools if available. It is recommended to assign files to the most sutiable tool manually, using the attachments parameter.  Defaults to None.
            recipient_agent (Agent, optional): The agent to which the message should be sent. Defaults to the first agent in the agency chart.
            additional_instructions (str, optional): Additional instructions to be sent with the message. Defaults to None.
            attachments (List[dict], optional): A list of attachments to be sent with the message, following openai format. Defaults to None.
            tool_choice (dict, optional): The tool choice for the recipient agent to use. Defaults to None.
            verbose (bool, optional): Whether to print the intermediary messages in console. Defaults to False.

        Returns:
            Final response: The final response from the main thread, parsed using the provided pydantic model.
        """
        response_model = None
        if isinstance(response_format, type):
            response_model = response_format
            response_format = type_to_response_format_param(response_format)

        res = self.get_completion(
            message=message,
            message_files=message_files,
            recipient_agent=recipient_agent,
            additional_instructions=additional_instructions,
            attachments=attachments,
            tool_choice=tool_choice,
            response_format=response_format,
            verbose=verbose,
        )

        try:
            return response_model.model_validate_json(res)
        except:
            parsed_res = json.loads(res)
            if "refusal" in parsed_res:
                raise RefusalError(parsed_res["refusal"])
            else:
                raise Exception("Failed to parse response: " + res)

    def demo_gradio(self, height=450, dark_mode=True, **kwargs):
        """
        Launches a Gradio-based demo interface for the agency chatbot.

        Parameters:
            height (int, optional): The height of the chatbot widget in the Gradio interface. Default is 600.
            dark_mode (bool, optional): Flag to determine if the interface should be displayed in dark mode. Default is True.
            **kwargs: Additional keyword arguments to be passed to the Gradio interface.
        This method sets up and runs a Gradio interface, allowing users to interact with the agency's chatbot. It includes a text input for the user's messages and a chatbot interface for displaying the conversation. The method handles user input and chatbot responses, updating the interface dynamically.
        """

        try:
            import gradio as gr
        except ImportError:
            raise Exception("Please install gradio: pip install gradio")

        js = """function () {
          gradioURL = window.location.href
          if (!gradioURL.endsWith('?__theme={theme}')) {
            window.location.replace(gradioURL + '?__theme={theme}');
          }
        }"""

        if dark_mode:
            js = js.replace("{theme}", "dark")
        else:
            js = js.replace("{theme}", "light")

        attachments = []
        images = []
        message_file_names = None
        uploading_files = False
        recipient_agent_names = [agent.name for agent in self.main_recipients]
        recipient_agent = self.main_recipients[0]

        with gr.Blocks(js=js) as demo:
            chatbot_queue = queue.Queue()
            chatbot = gr.Chatbot(height=height)
            with gr.Row():
                with gr.Column(scale=9):
                    dropdown = gr.Dropdown(
                        label="Recipient Agent",
                        choices=recipient_agent_names,
                        value=recipient_agent.name,
                    )
                    msg = gr.Textbox(label="Your Message", lines=4)
                with gr.Column(scale=1):
                    file_upload = gr.Files(label="OpenAI Files", type="filepath")
            button = gr.Button(value="Send", variant="primary")

            def handle_dropdown_change(selected_option):
                nonlocal recipient_agent
                recipient_agent = self._get_agent_by_name(selected_option)

            def handle_file_upload(file_list):
                nonlocal attachments
                nonlocal message_file_names
                nonlocal uploading_files
                nonlocal images
                uploading_files = True
                attachments = []
                message_file_names = []
                if file_list:
                    try:
                        for file_obj in file_list:
                            purpose = get_file_purpose(file_obj.name)

                            with open(file_obj.name, "rb") as f:
                                # Upload the file to OpenAI
                                file = self.main_thread.client.files.create(
                                    file=f, purpose=purpose
                                )

                            if purpose == "vision":
                                images.append(
                                    {
                                        "type": "image_file",
                                        "image_file": {"file_id": file.id},
                                    }
                                )
                            else:
                                attachments.append(
                                    {
                                        "file_id": file.id,
                                        "tools": get_tools(file.filename),
                                    }
                                )

                            message_file_names.append(file.filename)
                            print(f"Uploaded file ID: {file.id}")
                        return attachments
                    except Exception as e:
                        print(f"Error: {e}")
                        return str(e)
                    finally:
                        uploading_files = False

                uploading_files = False
                return "No files uploaded"

            def user(user_message, history):
                if not user_message.strip():
                    return user_message, history

                nonlocal message_file_names
                nonlocal uploading_files
                nonlocal images
                nonlocal attachments
                nonlocal recipient_agent

                # Check if attachments contain file search or code interpreter types
                def check_and_add_tools_in_attachments(attachments, recipient_agent):
                    for attachment in attachments:
                        for tool in attachment.get("tools", []):
                            if tool["type"] == "file_search":
                                if not any(
                                    isinstance(t, FileSearch)
                                    for t in recipient_agent.tools
                                ):
                                    # Add FileSearch tool if it does not exist
                                    recipient_agent.tools.append(FileSearch)
                                    recipient_agent.client.beta.assistants.update(
                                        recipient_agent.id,
                                        tools=recipient_agent.get_oai_tools(),
                                    )
                                    print(
                                        "Added FileSearch tool to recipient agent to analyze the file."
                                    )
                            elif tool["type"] == "code_interpreter":
                                if not any(
                                    isinstance(t, CodeInterpreter)
                                    for t in recipient_agent.tools
                                ):
                                    # Add CodeInterpreter tool if it does not exist
                                    recipient_agent.tools.append(CodeInterpreter)
                                    recipient_agent.client.beta.assistants.update(
                                        recipient_agent.id,
                                        tools=recipient_agent.get_oai_tools(),
                                    )
                                    print(
                                        "Added CodeInterpreter tool to recipient agent to analyze the file."
                                    )
                    return None

                check_and_add_tools_in_attachments(attachments, recipient_agent)

                if history is None:
                    history = []

                original_user_message = user_message

                # Append the user message with a placeholder for bot response
                if recipient_agent:
                    user_message = (
                        f"👤 User 🗣️ @{recipient_agent.name}:\n" + user_message.strip()
                    )
                else:
                    user_message = f"👤 User:" + user_message.strip()

                nonlocal message_file_names
                if message_file_names:
                    user_message += "\n\n📎 Files:\n" + "\n".join(message_file_names)

                return original_user_message, history + [[user_message, None]]

            class GradioEventHandler(AgencyEventHandler):
                message_output = None

                @classmethod
                def change_recipient_agent(cls, recipient_agent_name):
                    nonlocal chatbot_queue
                    chatbot_queue.put("[change_recipient_agent]")
                    chatbot_queue.put(recipient_agent_name)

                @override
                def on_message_created(self, message: Message) -> None:
                    if message.role == "user":
                        full_content = ""
                        for content in message.content:
                            if content.type == "image_file":
                                full_content += (
                                    f"🖼️ Image File: {content.image_file.file_id}\n"
                                )
                                continue

                            if content.type == "image_url":
                                full_content += f"\n{content.image_url.url}\n"
                                continue

                            if content.type == "text":
                                full_content += content.text.value + "\n"

                        self.message_output = MessageOutput(
                            "text",
                            self.agent_name,
                            self.recipient_agent_name,
                            full_content,
                        )

                    else:
                        self.message_output = MessageOutput(
                            "text", self.recipient_agent_name, self.agent_name, ""
                        )

                    chatbot_queue.put("[new_message]")
                    chatbot_queue.put(self.message_output.get_formatted_content())

                @override
                def on_text_delta(self, delta, snapshot):
                    chatbot_queue.put(delta.value)

                @override
                def on_tool_call_created(self, tool_call: ToolCall):
                    if isinstance(tool_call, dict):
                        if "type" not in tool_call:
                            tool_call["type"] = "function"

                        if tool_call["type"] == "function":
                            tool_call = FunctionToolCall(**tool_call)
                        elif tool_call["type"] == "code_interpreter":
                            tool_call = CodeInterpreterToolCall(**tool_call)
                        elif (
                            tool_call["type"] == "file_search"
                            or tool_call["type"] == "retrieval"
                        ):
                            tool_call = FileSearchToolCall(**tool_call)
                        else:
                            raise ValueError(
                                "Invalid tool call type: " + tool_call["type"]
                            )

                    # TODO: add support for code interpreter and retrieval tools
                    if tool_call.type == "function":
                        chatbot_queue.put("[new_message]")
                        self.message_output = MessageOutput(
                            "function",
                            self.recipient_agent_name,
                            self.agent_name,
                            str(tool_call.function),
                        )
                        chatbot_queue.put(
                            self.message_output.get_formatted_header() + "\n"
                        )

                @override
                def on_tool_call_done(self, snapshot: ToolCall):
                    if isinstance(snapshot, dict):
                        if "type" not in snapshot:
                            snapshot["type"] = "function"

                        if snapshot["type"] == "function":
                            snapshot = FunctionToolCall(**snapshot)
                        elif snapshot["type"] == "code_interpreter":
                            snapshot = CodeInterpreterToolCall(**snapshot)
                        elif snapshot["type"] == "file_search":
                            snapshot = FileSearchToolCall(**snapshot)
                        else:
                            raise ValueError(
                                "Invalid tool call type: " + snapshot["type"]
                            )

                    self.message_output = None

                    # TODO: add support for code interpreter and retrieval tools
                    if snapshot.type != "function":
                        return

                    chatbot_queue.put(str(snapshot.function))

                    if snapshot.function.name == "SendMessage":
                        try:
                            args = eval(snapshot.function.arguments)
                            recipient = args["recipient"]
                            self.message_output = MessageOutput(
                                "text",
                                self.recipient_agent_name,
                                recipient,
                                args["message"],
                            )

                            chatbot_queue.put("[new_message]")
                            chatbot_queue.put(
                                self.message_output.get_formatted_content()
                            )
                        except Exception as e:
                            pass

                    self.message_output = None

                @override
                def on_run_step_done(self, run_step: RunStep) -> None:
                    if run_step.type == "tool_calls":
                        for tool_call in run_step.step_details.tool_calls:
                            if tool_call.type != "function":
                                continue

                            if tool_call.function.name == "SendMessage":
                                continue

                            self.message_output = None
                            chatbot_queue.put("[new_message]")

                            self.message_output = MessageOutput(
                                "function_output",
                                tool_call.function.name,
                                self.recipient_agent_name,
                                tool_call.function.output,
                            )

                            chatbot_queue.put(
                                self.message_output.get_formatted_header() + "\n"
                            )
                            chatbot_queue.put(tool_call.function.output)

                @override
                @classmethod
                def on_all_streams_end(cls):
                    cls.message_output = None
                    chatbot_queue.put("[end]")

            def bot(original_message, history, dropdown):
                nonlocal attachments
                nonlocal message_file_names
                nonlocal recipient_agent
                nonlocal recipient_agent_names
                nonlocal images
                nonlocal uploading_files

                if not original_message:
                    return (
                        "",
                        history,
                        gr.update(
                            value=recipient_agent.name,
                            choices=set([*recipient_agent_names, recipient_agent.name]),
                        ),
                    )

                if uploading_files:
                    history.append([None, "Uploading files... Please wait."])
                    yield (
                        "",
                        history,
                        gr.update(
                            value=recipient_agent.name,
                            choices=set([*recipient_agent_names, recipient_agent.name]),
                        ),
                    )
                    return (
                        "",
                        history,
                        gr.update(
                            value=recipient_agent.name,
                            choices=set([*recipient_agent_names, recipient_agent.name]),
                        ),
                    )

                print("Message files: ", attachments)
                print("Images: ", images)

                if images and len(images) > 0:
                    original_message = [
                        {
                            "type": "text",
                            "text": original_message,
                        },
                        *images,
                    ]

                completion_thread = threading.Thread(
                    target=self.get_completion_stream,
                    args=(
                        original_message,
                        GradioEventHandler,
                        [],
                        recipient_agent,
                        "",
                        attachments,
                        None,
                    ),
                )
                completion_thread.start()

                attachments = []
                message_file_names = []
                images = []
                uploading_files = False

                new_message = True
                while True:
                    try:
                        bot_message = chatbot_queue.get(block=True)

                        if bot_message == "[end]":
                            completion_thread.join()
                            break

                        if bot_message == "[new_message]":
                            new_message = True
                            continue

                        if bot_message == "[change_recipient_agent]":
                            new_agent_name = chatbot_queue.get(block=True)
                            recipient_agent = self._get_agent_by_name(new_agent_name)
                            yield (
                                "",
                                history,
                                gr.update(
                                    value=new_agent_name,
                                    choices=set(
                                        [*recipient_agent_names, recipient_agent.name]
                                    ),
                                ),
                            )
                            continue

                        if new_message:
                            history.append([None, bot_message])
                            new_message = False
                        else:
                            history[-1][1] += bot_message

                        yield (
                            "",
                            history,
                            gr.update(
                                value=recipient_agent.name,
                                choices=set(
                                    [*recipient_agent_names, recipient_agent.name]
                                ),
                            ),
                        )
                    except queue.Empty:
                        break

            button.click(user, inputs=[msg, chatbot], outputs=[msg, chatbot]).then(
                bot, [msg, chatbot, dropdown], [msg, chatbot, dropdown]
            )
            dropdown.change(handle_dropdown_change, dropdown)
            file_upload.change(handle_file_upload, file_upload)
            msg.submit(user, [msg, chatbot], [msg, chatbot], queue=False).then(
                bot, [msg, chatbot, dropdown], [msg, chatbot, dropdown]
            )

            # Enable queuing for streaming intermediate outputs
            demo.queue(default_concurrency_limit=10)

        # Launch the demo
        demo.launch(**kwargs)
        return demo

    def _recipient_agent_completer(self, text, state):
        """
        Autocomplete completer for recipient agent names.
        """
        options = [
            agent
            for agent in self.recipient_agents
            if agent.lower().startswith(text.lower())
        ]
        if state < len(options):
            return options[state]
        else:
            return None

    def _setup_autocomplete(self):
        """
        Sets up readline with the completer function.
        """
        try:
            import readline
        except ImportError:
            # Attempt to import pyreadline for Windows compatibility
            try:
                import pyreadline as readline
            except ImportError:
                print(
                    "Module 'readline' not found. Autocomplete will not work. If you are using Windows, try installing 'pyreadline3'."
                )
                return

        if not readline:
            return

        try:
            readline.set_completer(self._recipient_agent_completer)
            readline.parse_and_bind("tab: complete")
        except Exception as e:
            print(
                f"Error setting up autocomplete for agents in terminal: {e}. Autocomplete will not work."
            )

    def run_demo(self):
        """
        Executes agency in the terminal with autocomplete for recipient agent names.
        """
        outer_self = self
        from agency_swarm import AgencyEventHandler

        class TermEventHandler(AgencyEventHandler):
            message_output = None

            @override
            def on_message_created(self, message: Message) -> None:
                if message.role == "user":
                    self.message_output = MessageOutputLive(
                        "text", self.agent_name, self.recipient_agent_name, ""
                    )
                    self.message_output.cprint_update(message.content[0].text.value)
                else:
                    self.message_output = MessageOutputLive(
                        "text", self.recipient_agent_name, self.agent_name, ""
                    )

            @override
            def on_message_done(self, message: Message) -> None:
                self.message_output = None

            @override
            def on_text_delta(self, delta, snapshot):
                self.message_output.cprint_update(snapshot.value)

            @override
            def on_tool_call_created(self, tool_call):
                if isinstance(tool_call, dict):
                    if "type" not in tool_call:
                        tool_call["type"] = "function"

                    if tool_call["type"] == "function":
                        tool_call = FunctionToolCall(**tool_call)
                    elif tool_call["type"] == "code_interpreter":
                        tool_call = CodeInterpreterToolCall(**tool_call)
                    elif (
                        tool_call["type"] == "file_search"
                        or tool_call["type"] == "retrieval"
                    ):
                        tool_call = FileSearchToolCall(**tool_call)
                    else:
                        raise ValueError("Invalid tool call type: " + tool_call["type"])

                # TODO: add support for code interpreter and retirieval tools

                if tool_call.type == "function":
                    self.message_output = MessageOutputLive(
                        "function",
                        self.recipient_agent_name,
                        self.agent_name,
                        str(tool_call.function),
                    )

            @override
            def on_tool_call_delta(self, delta, snapshot):
                if isinstance(snapshot, dict):
                    if "type" not in snapshot:
                        snapshot["type"] = "function"

                    if snapshot["type"] == "function":
                        snapshot = FunctionToolCall(**snapshot)
                    elif snapshot["type"] == "code_interpreter":
                        snapshot = CodeInterpreterToolCall(**snapshot)
                    elif snapshot["type"] == "file_search":
                        snapshot = FileSearchToolCall(**snapshot)
                    else:
                        raise ValueError("Invalid tool call type: " + snapshot["type"])

                self.message_output.cprint_update(str(snapshot.function))

            @override
            def on_tool_call_done(self, snapshot):
                self.message_output = None

                # TODO: add support for code interpreter and retrieval tools
                if snapshot.type != "function":
                    return

                if snapshot.function.name == "SendMessage" and not (
                    hasattr(
                        outer_self.send_message_tool_class.ToolConfig,
                        "output_as_result",
                    )
                    and outer_self.send_message_tool_class.ToolConfig.output_as_result
                ):
                    try:
                        args = eval(snapshot.function.arguments)
                        recipient = args["recipient"]
                        self.message_output = MessageOutputLive(
                            "text", self.recipient_agent_name, recipient, ""
                        )

                        self.message_output.cprint_update(args["message"])
                    except Exception as e:
                        pass

                self.message_output = None

            @override
            def on_run_step_done(self, run_step: RunStep) -> None:
                if run_step.type == "tool_calls":
                    for tool_call in run_step.step_details.tool_calls:
                        if tool_call.type != "function":
                            continue

                        if tool_call.function.name == "SendMessage":
                            continue

                        self.message_output = None
                        self.message_output = MessageOutputLive(
                            "function_output",
                            tool_call.function.name,
                            self.recipient_agent_name,
                            tool_call.function.output,
                        )
                        self.message_output.cprint_update(tool_call.function.output)

                    self.message_output = None

            @override
            def on_end(self):
                self.message_output = None

        self.recipient_agents = [str(agent.name) for agent in self.main_recipients]

        self._setup_autocomplete()  # Prepare readline for autocomplete

        while True:
            console.rule()
            text = input("👤 USER: ")

            if not text:
                continue

            if text.lower() == "exit":
                break

            recipient_agent = None
            if "@" in text:
                recipient_agent = text.split("@")[1].split(" ")[0]
                text = text.replace(f"@{recipient_agent}", "").strip()
                try:
                    recipient_agent = [
                        agent
                        for agent in self.recipient_agents
                        if agent.lower() == recipient_agent.lower()
                    ][0]
                    recipient_agent = self._get_agent_by_name(recipient_agent)
                except Exception as e:
                    print(f"Recipient agent {recipient_agent} not found.")
                    continue

            self.get_completion_stream(
                message=text,
                event_handler=TermEventHandler,
                recipient_agent=recipient_agent,
            )

    def get_customgpt_schema(self, url: str):
        """Returns the OpenAPI schema for the agency from the CEO agent, that you can use to integrate with custom gpts.

        Parameters:
            url (str): Your server url where the api will be hosted.
        """

        return self.ceo.get_openapi_schema(url)

    def plot_agency_chart(self):
        pass

    def _init_agents(self):
        """
        Initializes all agents in the agency with unique IDs, shared instructions, and OpenAI models.

        This method iterates through each agent in the agency, assigns a unique ID, adds shared instructions, and initializes the OpenAI models for each agent.

        There are no input parameters.

        There are no output parameters as this method is used for internal initialization purposes within the Agency class.
        """
        if self.settings_callbacks:
            loaded_settings = self.settings_callbacks["load"]()
            with open(self.settings_path, "w") as f:
                json.dump(loaded_settings, f, indent=4)

        for agent in self.agents:
            assert isinstance(agent, Agent)
            print(f"Initializing agent... {agent.name}")
            if "temp_id" in agent.id:
                agent.id = None

            agent.agency = self
            agent.add_shared_instructions(self.shared_instructions)
            agent.settings_path = self.settings_path

            if self.shared_files:
                if isinstance(self.shared_files, str):
                    self.shared_files = [self.shared_files]

                if isinstance(agent.files_folder, str):
                    agent.files_folder = [agent.files_folder]
                    agent.files_folder += self.shared_files
                elif isinstance(agent.files_folder, list):
                    agent.files_folder += self.shared_files

            if self.temperature is not None and agent.temperature is None:
                agent.temperature = self.temperature
            if self.top_p and agent.top_p is None:
                agent.top_p = self.top_p
            if self.max_prompt_tokens is not None and agent.max_prompt_tokens is None:
                agent.max_prompt_tokens = self.max_prompt_tokens
            if (
                self.max_completion_tokens is not None
                and agent.max_completion_tokens is None
            ):
                agent.max_completion_tokens = self.max_completion_tokens
            if (
                self.truncation_strategy is not None
                and agent.truncation_strategy is None
            ):
                agent.truncation_strategy = self.truncation_strategy

            if not agent.shared_state:
                agent.shared_state = self.shared_state

            agent.init_oai()

        if self.settings_callbacks:
            with open(self.agents[0].get_settings_path(), "r") as f:
                settings = f.read()
            settings = json.loads(settings)
            self.settings_callbacks["save"](settings)

    def _init_threads(self):
        """
        Initializes threads for communication between agents within the agency.

        This method creates Thread objects for each pair of interacting agents as defined in the agents_and_threads attribute of the Agency. Each thread facilitates communication and task execution between an agent and its designated recipient agent.

        No input parameters.

        Output Parameters:
            This method does not return any value but updates the agents_and_threads attribute with initialized Thread objects.
        """
        self.main_thread = Thread(self.user, self.ceo)

        # load thread ids
        loaded_thread_ids = {}
        if self.threads_callbacks:
            loaded_thread_ids = self.threads_callbacks["load"]()
            if "main_thread" in loaded_thread_ids and loaded_thread_ids["main_thread"]:
                self.main_thread.id = loaded_thread_ids["main_thread"]
            else:
                self.main_thread.init_thread()

        # Save main_thread into agents_and_threads
        self.agents_and_threads["main_thread"] = self.main_thread

        # initialize threads
        for agent_name, threads in self.agents_and_threads.items():
            if agent_name == "main_thread":
                continue
            for other_agent, items in threads.items():
                # create thread class
                self.agents_and_threads[agent_name][other_agent] = self._thread_type(
                    self._get_agent_by_name(items["agent"]),
                    self._get_agent_by_name(items["recipient_agent"]),
                )

                # load thread id if available
                if (
                    agent_name in loaded_thread_ids
                    and other_agent in loaded_thread_ids[agent_name]
                ):
                    self.agents_and_threads[agent_name][
                        other_agent
                    ].id = loaded_thread_ids[agent_name][other_agent]
                # init threads if threre are threads callbacks so the ids are saved for later use
                elif self.threads_callbacks:
                    self.agents_and_threads[agent_name][other_agent].init_thread()

        # save thread ids
        if self.threads_callbacks:
            loaded_thread_ids = {}
            for agent_name, threads in self.agents_and_threads.items():
                if agent_name == "main_thread":
                    continue
                loaded_thread_ids[agent_name] = {}
                for other_agent, thread in threads.items():
                    loaded_thread_ids[agent_name][other_agent] = thread.id

            loaded_thread_ids["main_thread"] = self.main_thread.id

            self.threads_callbacks["save"](loaded_thread_ids)

    def _parse_agency_chart(self, agency_chart):
        """
        Parses the provided agency chart to initialize and organize agents within the agency.

        Parameters:
            agency_chart: A structure representing the hierarchical organization of agents within the agency.
                    It can contain Agent objects and lists of Agent objects.

        This method iterates through each node in the agency chart. If a node is an Agent, it is set as the CEO if not already assigned.
        If a node is a list, it iterates through the agents in the list, adding them to the agency and establishing communication
        threads between them. It raises an exception if the agency chart is invalid or if multiple CEOs are defined.
        """
        if not isinstance(agency_chart, list):
            raise Exception("Invalid agency chart.")

        if len(agency_chart) == 0:
            raise Exception("Agency chart cannot be empty.")

        for node in agency_chart:
            if isinstance(node, Agent):
                if not self.ceo:
                    self.ceo = node
                    self._add_agent(self.ceo)
                else:
                    self._add_agent(node)
                self._add_main_recipient(node)

            elif isinstance(node, list):
                for i, agent in enumerate(node):
                    print(f"checking {agent.name}...")
                    if not isinstance(agent, Agent):
                        raise Exception("Invalid agency chart.")

                    index = self._add_agent(agent)

                    if i == len(node) - 1:
                        continue

                    if agent.name not in self.agents_and_threads.keys():
                        self.agents_and_threads[agent.name] = {}

                    if i < len(node) - 1:
                        other_agent = node[i + 1]
                        if other_agent.name == agent.name:
                            continue
                        if (
                            other_agent.name
                            not in self.agents_and_threads[agent.name].keys()
                        ):
                            self.agents_and_threads[agent.name][other_agent.name] = {
                                "agent": agent.name,
                                "recipient_agent": other_agent.name,
                            }
            else:
                raise Exception("Invalid agency chart.")

    def _add_agent(self, agent):
        """
        Adds an agent to the agency, assigning a temporary ID if necessary.

        Parameters:
            agent (Agent): The agent to be added to the agency.

        Returns:
            int: The index of the added agent within the agency's agents list.

        This method adds an agent to the agency's list of agents. If the agent does not have an ID, it assigns a temporary unique ID. It checks for uniqueness of the agent's name before addition. The method returns the index of the agent in the agency's agents list, which is used for referencing the agent within the agency.
        """
        if not agent.id:
            # assign temp id
            agent.id = "temp_id_" + str(uuid.uuid4())
        if agent.id not in self._get_agent_ids():
            if agent.name in self._get_agent_names():
                raise Exception("Agent names must be unique.")
            self.agents.append(agent)
            return len(self.agents) - 1
        else:
            return self._get_agent_ids().index(agent.id)

    def _add_main_recipient(self, agent):
        """
        Adds an agent to the agency's list of main recipients.

        Parameters:
            agent (Agent): The agent to be added to the agency's list of main recipients.

        This method adds an agent to the agency's list of main recipients. These are agents that can be directly contacted by the user.
        """
        main_recipient_ids = [agent.id for agent in self.main_recipients]

        if agent.id not in main_recipient_ids:
            self.main_recipients.append(agent)

    def _read_instructions(self, path):
        """
        Reads shared instructions from a specified file and stores them in the agency.

        Parameters:
            path (str): The file path from which to read the shared instructions.

        This method opens the file located at the given path, reads its contents, and stores these contents in the 'shared_instructions' attribute of the agency. This is used to provide common guidelines or instructions to all agents within the agency.
        """
        path = path
        with open(path, "r") as f:
            self.shared_instructions = f.read()

    def _create_special_tools(self):
        """
        Creates and assigns 'SendMessage' tools to each agent based on the agency's structure.

        This method iterates through the agents and threads in the agency, creating SendMessage tools for each agent. These tools enable agents to send messages to other agents as defined in the agency's structure. The SendMessage tools are tailored to the specific recipient agents that each agent can communicate with.

        No input parameters.

        No output parameters; this method modifies the agents' toolset internally.
        """
        for agent_name, threads in self.agents_and_threads.items():
            if agent_name == "main_thread":
                continue
            recipient_names = list(threads.keys())
            recipient_agents = self._get_agents_by_names(recipient_names)
            if len(recipient_agents) == 0:
                continue
            agent = self._get_agent_by_name(agent_name)
            agent.add_tool(self._create_send_message_tool(agent, recipient_agents))
            if self._thread_type == ThreadAsync:
                agent.add_tool(self._create_get_response_tool(agent, recipient_agents))

    def _create_send_message_tool(self, agent: Agent, recipient_agents: List[Agent]):
        """
        Creates a SendMessage tool to enable an agent to send messages to specified recipient agents.


        Parameters:
            agent (Agent): The agent who will be sending messages.
            recipient_agents (List[Agent]): A list of recipient agents who can receive messages.

        Returns:
            SendMessage: A SendMessage tool class that is dynamically created and configured for the given agent and its recipient agents. This tool allows the agent to send messages to the specified recipients, facilitating inter-agent communication within the agency.
        """
        recipient_names = [agent.name for agent in recipient_agents]
        recipients = Enum("recipient", {name: name for name in recipient_names})

        agent_descriptions = ""
        for recipient_agent in recipient_agents:
            if not recipient_agent.description:
                continue
            agent_descriptions += recipient_agent.name + ": "
            agent_descriptions += recipient_agent.description + "\n"

        class SendMessage(self.send_message_tool_class):
            recipient: recipients = Field(..., description=agent_descriptions)

            @field_validator("recipient")
            @classmethod
            def check_recipient(cls, value):
                if value.value not in recipient_names:
                    raise ValueError(
                        f"Recipient {value} is not valid. Valid recipients are: {recipient_names}"
                    )
                return value

        SendMessage._caller_agent = agent
        SendMessage._agents_and_threads = self.agents_and_threads

        return SendMessage

    def _create_get_response_tool(self, agent: Agent, recipient_agents: List[Agent]):
        """
        Creates a CheckStatus tool to enable an agent to check the status of a task with a specified recipient agent.
        """
        recipient_names = [agent.name for agent in recipient_agents]
        recipients = Enum("recipient", {name: name for name in recipient_names})

        outer_self = self

        class GetResponse(BaseTool):
            """This tool allows you to check the status of a task or get a response from a specified recipient agent, if the task has been completed. You must always use 'SendMessage' tool with the designated agent first."""

            recipient: recipients = Field(
                ...,
                description=f"Recipient agent that you want to check the status of. Valid recipients are: {recipient_names}",
            )

            @field_validator("recipient")
            def check_recipient(cls, value):
                if value.value not in recipient_names:
                    raise ValueError(
                        f"Recipient {value} is not valid. Valid recipients are: {recipient_names}"
                    )
                return value

            def run(self):
                thread = outer_self.agents_and_threads[self._caller_agent.name][
                    self.recipient.value
                ]

                return thread.check_status()

        GetResponse._caller_agent = agent

        return GetResponse

    def _get_agent_by_name(self, agent_name):
        """
        Retrieves an agent from the agency based on the agent's name.

        Parameters:
            agent_name (str): The name of the agent to be retrieved.

        Returns:
            Agent: The agent object with the specified name.

        Raises:
            Exception: If no agent with the given name is found in the agency.
        """
        for agent in self.agents:
            if agent.name == agent_name:
                return agent
        raise Exception(f"Agent {agent_name} not found.")

    def _get_agents_by_names(self, agent_names):
        """
        Retrieves a list of agent objects based on their names.

        Parameters:
            agent_names: A list of strings representing the names of the agents to be retrieved.

        Returns:
            A list of Agent objects corresponding to the given names.
        """
        return [self._get_agent_by_name(agent_name) for agent_name in agent_names]

    def _get_agent_ids(self):
        """
        Retrieves the IDs of all agents currently in the agency.

        Returns:
            List[str]: A list containing the unique IDs of all agents.
        """
        return [agent.id for agent in self.agents]

    def _get_agent_names(self):
        """
        Retrieves the names of all agents in the agency.

        Returns:
            List[str]: A list of names of all agents currently part of the agency.
        """
        return [agent.name for agent in self.agents]

    def _get_class_folder_path(self):
        """
        Retrieves the absolute path of the directory containing the class file.

        Returns:
            str: The absolute path of the directory where the class file is located.
        """
        return os.path.abspath(os.path.dirname(inspect.getfile(self.__class__)))

    def delete(self):
        """
        This method deletes the agency and all its agents, cleaning up any files and vector stores associated with each agent.
        """
        for agent in self.agents:
            agent.delete()
    
    def _init_file(self, file_path):
        try:
            with open(file_path, "w", encoding='utf-8') as f:
                pass
        except Exception as e:
            print(f"Creating {file_path}...")
    def _init_dir(self, dir_path):
        import shutil
        try:
            shutil.rmtree(dir_path)
        except:
            pass
        os.mkdir(dir_path)
    
    files_path = os.path.join("agents", "files")
    completed_step_path = os.path.join(files_path, "completed_steps.json")
    completed_subtask_path = os.path.join(files_path, "completed_sub_tasks.json")
    completed_task_path = os.path.join(files_path, "completed_tasks.json")
    context_index_path = os.path.join(files_path, "context_index.json")
    contexts_path = os.path.join(files_path, "api_results")
    error_path = os.path.join(files_path, "error.json")

    def init_files(self):
        # self._init_dir(self.files_path)
        # self._init_dir(self.contexts_path)
        self._init_file(self.error_path)
        self._init_file(self.completed_step_path)
        self._init_file(self.completed_subtask_path)
        self._init_file(self.completed_task_path)
        # self._init_file(self.context_index_path)

    def create_cap_group_agent_threads(self, cap_group_agents: Dict[str, List]) -> Dict[str, List[Thread]]:
        capgroup_thread = {}
        for key in cap_group_agents.keys():
            capgroup_thread[key] = []
            for agent in cap_group_agents[key]:
                capgroup_thread[key].append(Thread(self.user, agent))
        return capgroup_thread
    
    def create_cap_agent_thread(self, cap_group: str, cap_agents: Dict[str, List]) -> Dict[str, Thread]:
        cap_agent_thread = {}
        for agent in cap_agents[cap_group]:
            cap_agent_thread[agent.name] = Thread(self.user, agent)
        return cap_agent_thread

    def test_single_cap_agent(self, step: dict, cap_group: str, plan_agents: Dict[str, Agent], cap_group_agents: Dict[str, List], cap_agents: Dict[str, List]):
        """
        用户请求 -> 事务*n1 -> 子任务*n2 -> 步骤*n3
        事务是不可分割（指完成过程中）的任务，如安装软件等，必须完成之后才能进行其他操作；
        子任务是对事务进行拆分，按照能力群拆分，类似于流水线；
        步骤对应能力，指具体操作步骤，和能力Agent关联
        """
        self._setup_autocomplete()  # Prepare readline for autocomplete

        self.init_files()

        print("Initialization Successful.\n")
        
        cap_agent_threads = {}
        for key in cap_agents:
            cap_agent_threads[key] = self.create_cap_agent_thread(cap_group=key, cap_agents=cap_agents)

        # task_id = 0
        result, new_context = self.capability_agents_processor(step=step, cap_group=cap_group, cap_agent_threads=cap_agent_threads)

    def task_planning(self, original_request: str, plan_agents: Dict[str, Agent], cap_group_agents: Dict[str, List], cap_agents: Dict[str, List]):
        """
        用户请求 -> 事务*n1 -> 子任务*n2 -> 步骤*n3
        事务是不可分割（指完成过程中）的任务，如安装软件等，必须完成之后才能进行其他操作；
        子任务是对事务进行拆分，按照能力群拆分，类似于流水线；
        步骤对应能力，指具体操作步骤，和能力Agent关联
        """
        self._setup_autocomplete()  # Prepare readline for autocomplete

        self.init_files()

        print("Initialization Successful.\n")

        code_scheduling = os.getenv("DEBUG_CODE_SCHEDULING")
        if code_scheduling is None or code_scheduling.lower() != "true":
            code_scheduling = False
        else:
            code_scheduling = True

        task_planner = plan_agents["task_planner"]
        task_inspector = plan_agents["task_inspector"]
        subtask_planner = plan_agents["subtask_planner"]
        subtask_inspector = plan_agents["subtask_inspector"]
        step_inspector = plan_agents["step_inspector"]
        task_planner_thread = Thread(self.user, task_planner)
        task_inspector_thread = Thread(self.user, task_inspector)
        subtask_planner_thread = Thread(self.user, subtask_planner)
        subtask_inspector_thread = Thread(self.user, subtask_inspector)
        step_inspector_thread = Thread(self.user, step_inspector)

        if not code_scheduling:
            task_scheduler = plan_agents["task_scheduler"]
            subtask_scheduler = plan_agents["subtask_scheduler"]
            task_scheduler_thread = Thread(self.user, task_scheduler)
            subtask_scheduler_thread = Thread(self.user, subtask_scheduler)

        cap_group_thread = self.create_cap_group_agent_threads(cap_group_agents=cap_group_agents)
        # cap_group_thread[能力群名称] = [该能力群的planner的Thread, 该能力群的scheduler的Thread]

        cap_agent_threads = {}
        for key in cap_agents:
            cap_agent_threads[key] = self.create_cap_agent_thread(cap_group=key, cap_agents=cap_agents)
        # cap_agent_threads[能力群名称][能力agent名称] = 该能力agent的Thread

        # task_id = 0
        context_id = 0
        original_request_error_flag = False
        original_request_error_message = ""
        error_id = 0
        while True: # 规划用户需求，拆分task流程图
            # task_id = task_id + 1
            task_graph, tasks_need_scheduled = self.planning_layer(message=original_request, original_request=original_request, planner_thread=task_planner_thread, error_message=original_request_error_message, inspector_thread=task_inspector_thread, node_color='lightblue', overall_id="original request")
            original_request_error_flag = False
            self._init_file(self.error_path)

            id2task = {}
            task_graph_json = json.loads(task_graph)
            for key in task_graph_json.keys():
                task = task_graph_json[key]
                id2task[task['id']] = task
            completed_task_ids = []

            while True: # task调度
                if code_scheduling:
                    next_task_list = self.code_scheduling_layer(overall_id="original request", graph=task_graph_json, completed_ids=completed_task_ids)
                else:
                    tasks_scheduled = self.scheduling_layer(scheduler_thread=task_scheduler_thread, message=tasks_need_scheduled)
                    tasks_scheduled_json = json.loads(tasks_scheduled)
                    next_task_list = tasks_scheduled_json['next_tasks']
                
                if not next_task_list: # 当task全部完成，退出
                    break

                for next_task_id in next_task_list:
                    # 规划并执行单个task，不可中途终止。如果出现错误则重新规划task。
                    task_error_flag = False
                    task_error_message = ""

                    next_task = id2task[next_task_id]
                    subtask_input = {
                        "title": next_task['title'],
                        "description": next_task['description'],
                        "total_task_graph": task_graph_json,
                    }

                    console.rule()
                    print(f"completed tasks: {(', '.join([str(id)+' ('+task_graph_json[id]['title']+')' for id in completed_task_ids])) if completed_task_ids else 'none'}")
                    print(f"next task -> {next_task_id} ({next_task['title']})")

                    while True: # 规划一个task，拆分出subtask（能力群相关）流程图
                        subtask_graph, subtasks_need_scheduled = self.planning_layer(message=json.dumps(subtask_input, ensure_ascii=False), original_request=next_task['description'], planner_thread=subtask_planner_thread, error_message=task_error_message, inspector_thread=subtask_inspector_thread, node_color='lightgreen', overall_id=next_task_id)
                        task_error_flag = False
                        
                        id2subtask = {}
                        subtask_graph_json = json.loads(subtask_graph)
                        for key in subtask_graph_json.keys():
                            subtask = subtask_graph_json[key]
                            id2subtask[subtask['id']] = subtask
                        completed_subtask_ids = []
                        
                        while True: # subtask调度
                            if code_scheduling:
                                next_subtask_list = self.code_scheduling_layer(overall_id=next_task_id, graph=subtask_graph_json, completed_ids=completed_subtask_ids)
                            else:
                                subtasks_scheduled = self.scheduling_layer(scheduler_thread=subtask_scheduler_thread, message=subtasks_need_scheduled)
                                subtasks_scheduled_json = json.loads(subtasks_scheduled)
                                next_subtask_list = subtasks_scheduled_json['next_subtasks']
                            
                            if not next_subtask_list: # 当subtask全部完成，退出
                                break

                            for next_subtask_id in next_subtask_list:
                                # 规划并执行单个subtask，如出错重新规划task。
                                subtask_error_flag = False
                                subtask_error_message = ""

                                next_subtask = id2subtask[next_subtask_id]
                                steps_input = {
                                    "title": next_subtask['title'],
                                    "description": next_subtask['description'],
                                    "total_subtask_graph": subtask_graph_json,
                                }

                                console.rule()
                                print(f"completed tasks: {(', '.join([str(id)+' ('+task_graph_json[id]['title']+')' for id in completed_task_ids])) if completed_task_ids else 'none'}")
                                print(f"this task -> {next_task_id} ({next_task['title']})")
                                print(f"├ completed subtasks: {(', '.join([str(id)+' ('+subtask_graph_json[id]['title']+')' for id in completed_subtask_ids])) if completed_subtask_ids else 'none'}")
                                print(f"└ next subtask -> {next_subtask_id} ({next_subtask['title']})")
                                next_subtask_cap_group = next_subtask['capability_group']

                                # if next_subtask_cap_group == "简单任务处理能力群":
                                #     steps_input_simple = {
                                #         "user_request": original_request,
                                #         "title": next_subtask['title'],
                                #         "description": next_subtask['description'],
                                #     }
                                #     subtask_result_context = self.json_get_completion(cap_group_thread[next_subtask_cap_group][0], json.dumps(steps_input_simple, ensure_ascii=False))
                                #     subtask_result_context_json = json.loads(subtask_result_context)
                                #     context_file_path = subtask_result_context_json['context']
                                #     context_id = context_id + 1
                                #     self.update_context(context_id=context_id, context=context_file_path, step=next_subtask)
                                #     self.update_completed_sub_task(next_subtask_id, next_subtask)
                                #     continue

                                while True: # 规划一个subtask，拆分出step（能力相关）流程图
                                    steps_graph, steps_need_scheduled = self.planning_layer(message=json.dumps(steps_input, ensure_ascii=False), original_request=next_subtask['description'], planner_thread=cap_group_thread[next_subtask_cap_group][0], error_message=subtask_error_message, inspector_thread=step_inspector_thread, node_color='white', overall_id=next_subtask_id)
                                    subtask_error_flag = False

                                    id2step = {}
                                    steps_graph_json = json.loads(steps_graph)
                                    for key in steps_graph_json.keys():
                                        step = steps_graph_json[key]
                                        id2step[step['id']] = step
                                    completed_step_ids = []

                                    while True: # step调度
                                        if code_scheduling:
                                            next_step_list = self.code_scheduling_layer(overall_id=next_subtask_id, graph=steps_graph_json, completed_ids=completed_step_ids)
                                        else:
                                            steps_scheduled = self.scheduling_layer(scheduler_thread=cap_group_thread[next_subtask_cap_group][1], message=steps_need_scheduled)
                                            steps_scheduled_json = json.loads(steps_scheduled)
                                            next_step_list = steps_scheduled_json['next_steps']
                                        
                                        if not next_step_list:  # 当step全部完成，退出
                                            break
                                        
                                        for next_step_id in next_step_list:
                                            # 执行单个step，如出错重新规划task。
                                            step_error_flag = False
                                            step_error_message = ""

                                            next_step = id2step[next_step_id]

                                            console.rule()
                                            print(f"completed tasks: {(', '.join([str(id)+' ('+task_graph_json[id]['title']+')' for id in completed_task_ids])) if completed_task_ids else 'none'}")
                                            print(f"this task -> {next_task_id} ({next_task['title']})")
                                            print(f"├ completed subtasks: {(', '.join([str(id)+' ('+subtask_graph_json[id]['title']+')' for id in completed_subtask_ids])) if completed_subtask_ids else 'none'}")
                                            print(f"└ this subtask -> {next_subtask_id} ({next_subtask['title']})")
                                            print(f"  ├ completed steps: {(', '.join([str(id)+' ('+steps_graph_json[id]['title']+')' for id in completed_step_ids])) if completed_step_ids else 'none'}")
                                            print(f"  └ next step -> {next_step_id} ({next_step['title']})")
                                            
                                            while True: # 能力agent执行单个step
                                                try:
                                                    result, new_context = self.capability_agents_processor(step=next_step, cap_group=next_subtask_cap_group, cap_agent_threads=cap_agent_threads)
                                                    assert result == 'SUCCESS' or result == 'FAIL', f"Unknown result: {result}"
                                                    if result == 'SUCCESS':
                                                        # 更新已完成step和context
                                                        context_id = context_id + 1
                                                        self.update_context(context_id=context_id, context=new_context, step=next_step)
                                                        self.update_completed_step(step_id=next_step_id, step=next_step)
                                                    elif result == 'FAIL':
                                                        # 更新error
                                                        error_id = error_id + 1
                                                        step_error_flag = True
                                                        step_error_message = new_context
                                                        # self.update_error(error_id=error_id, error=new_context, step=next_step)
                                                except Exception as e:
                                                    # 更新error
                                                    error_id = error_id + 1
                                                    step_error_flag = True
                                                    step_error_message = str(e)
                                                
                                                if not step_error_flag:
                                                    console.rule()
                                                    print(f"    {next_step_id} ({next_step['title']}) complete")
                                                    break
                                                else:
                                                    console.rule()
                                                    print(f"    {next_step_id} ({next_step['title']}) failed, error: {step_error_message}")
                                                    # continue # 重新执行step
                                                    subtask_error_flag = True
                                                    subtask_error_message = step_error_message
                                                    break # 重新规划subtask
                                            
                                            if subtask_error_flag:
                                                break
                                            # 本step完成
                                            completed_step_ids.append(next_step_id)

                                        if subtask_error_flag:
                                            break
                                        # 本次step调度结束
                                    
                                    # 本subtask的所有step结束

                                    self._init_file(self.completed_step_path)
                                    if not subtask_error_flag:
                                        # 如果step全都正常完成，更新已完成subtask
                                        console.rule()
                                        print(f"  {next_subtask_id} ({next_subtask['title']}) complete")
                                        self.update_completed_sub_task(next_subtask_id, next_subtask)
                                        break
                                    else:
                                        console.rule()
                                        print(f"  {next_subtask_id} ({next_subtask['title']}) failed, error: {subtask_error_message}")
                                        # continue # 重新规划subtask
                                        task_error_flag = True
                                        task_error_message = subtask_error_message
                                        break
                                
                                if task_error_flag:
                                    break
                                # 本subtask完成
                                completed_subtask_ids.append(next_subtask_id)

                            if task_error_flag:
                                break
                            # 本次subtask调度结束
                        
                        # 本task的所有subtask结束

                        self._init_file(self.completed_subtask_path)
                        if not task_error_flag:
                            # 如果subtask全都正常完成，更新已完成task
                            console.rule()
                            print(f"{next_task_id} ({next_task['title']}) complete")
                            self.update_completed_task(next_task_id, next_task)
                            break
                        else:
                            console.rule()
                            print(f"{next_task_id} ({next_task['title']}) failed, error: {task_error_message}")
                            continue # 重新规划task
                    
                    # 本task完成
                    completed_task_ids.append(next_task_id)

                if original_request_error_flag:
                    break
                # 本次task调度结束
            
            # 本用户请求的所有task结束

            if not original_request_error_flag:
                console.rule()
                print(f"original request complete")
                break
            else:
                console.rule()
                print(f"original request failed, error: {original_request_error_message}")
                continue # 重新规划用户请求
    
    def update_error(self, error_id: int, error: str, step: dict):
        with open(self.error_path, 'r', encoding='utf-8') as file:
            try:    # 尝试读取 JSON 数据
                data = json.load(file)
            except json.JSONDecodeError:    # 如果文件为空或格式错误，则创建一个空字典
                data = {}
        data[error_id] = {
            "step": step,
            "error": error
        }
        with open(self.error_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
    
    def update_context(self, context_id: int, context: str, step: dict):
        with open(self.context_index_path, 'r', encoding='utf-8') as file:
            try:    # 尝试读取 JSON 数据
                data = json.load(file)
            except json.JSONDecodeError:    # 如果文件为空或格式错误，则创建一个空字典
                data = {}
        data["index_" + str(context_id)] = {
            "task_information": step,
            "context": context
        }
        with open(self.context_index_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=4, ensure_ascii=False)

    def update_completed_step(self, step_id: str, step: dict):
        with open(self.completed_step_path, 'r', encoding='utf-8') as file:
            try:    # 尝试读取 JSON 数据
                data = json.load(file)
            except json.JSONDecodeError:    # 如果文件为空或格式错误，则创建一个空字典
                data = {}
        data['step_id'] = {
            "step": step
        }
        with open(self.completed_step_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
    
    def update_completed_sub_task(self, subtask_id: str, subtask: dict):
        with open(self.completed_subtask_path, 'r', encoding='utf-8') as file:
            try:    # 尝试读取 JSON 数据
                data = json.load(file)
            except json.JSONDecodeError:    # 如果文件为空或格式错误，则创建一个空字典
                data = {}
        data[subtask_id] = {
            "subtask": subtask
        }
        with open(self.completed_subtask_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=4, ensure_ascii=False)

    def update_completed_task(self, task_id: str, task: dict):
        with open(self.completed_task_path, 'r', encoding='utf-8') as file:
            try:    # 尝试读取 JSON 数据
                data = json.load(file)
            except json.JSONDecodeError:    # 如果文件为空或格式错误，则创建一个空字典
                data = {}
        data[task_id] = {
            "task": task
        }
        with open(self.completed_task_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=4, ensure_ascii=False)

    def capability_agents_processor(self, step: dict, cap_group: str, cap_agent_threads: dict):
        """能力agent执行任务，目前只考虑单个能力agent的情况"""
        cap_agents = step['agent']
        for agent_name in cap_agents:
            console.rule()
            print(f"{agent_name} EXECUTING {step['id']}...\n")
            cap_agent_thread = cap_agent_threads[cap_group][agent_name]
            cap_agent_result = self.json_get_completion(cap_agent_thread, json.dumps(step, ensure_ascii=False))
            # print(f"{agent_name} results of execution:\n{cap_agent_result}")
            cap_agent_result_json = json.loads(cap_agent_result)
        result = cap_agent_result_json['result']
        context = cap_agent_result_json['context']
        return result, context

    def scheduling_layer(self, message: str, scheduler_thread: Thread):
        console.rule()
        print(f"{scheduler_thread.recipient_agent.name} SCHEDULING...\n")
        scheduler_res = self.json_get_completion(scheduler_thread, message)
        return scheduler_res
    
    def code_scheduling_layer(self, overall_id: str, graph: Dict[str, Dict[str, Any]], completed_ids: List[str]) -> List[str]:
        console.rule()
        print(f"SCHEDULING {overall_id}...\n")
        next_ids = []
        completed_id_set = set(completed_ids)
        for id_key, info in graph.items():
            if id_key in completed_id_set:
                continue
            deps = info.get('dep', [])
            all_deps_met = all(dep_id in completed_id_set for dep_id in deps)
            if all_deps_met:
                next_ids.append(id_key)
        print(f"completed: {(', '.join([str(id)+' ('+graph[id]['title']+')' for id in completed_ids])) if completed_ids else 'none'}")
        print(f"scheduled: {(', '.join([str(id)+' ('+graph[id]['title']+')' for id in next_ids])) if next_ids else 'none'}")
        pending_ids = []
        for id_key in graph.keys():
            if id_key not in completed_id_set and id_key not in next_ids:
                pending_ids.append(id_key)
        print(f"pending: {(', '.join([str(id)+' ('+graph[id]['title']+')' for id in pending_ids])) if pending_ids else 'none'}")
        return next_ids

    def planning_layer(self, message: str, original_request:str, planner_thread: Thread, error_message: str = "", inspector_thread: Thread = None, node_color: str = 'lightblue', overall_id: str = ''):
        """将返回1. 规划结果, 2. 对应scheduler的输入"""
        console.rule()
        print(f"{planner_thread.recipient_agent.name} PLANNING {overall_id}...\n")
        print(original_request)
        if error_message != "":
            message = message + "\n\nThe error occurred when executing the previous plan: \n" + error_message
        planmessage = self.json_get_completion(planner_thread, message, original_request, inspector_thread)
        planmessage_json = json.loads(planmessage)
        plan_json = {}
        plan_json['main_task'] = original_request
        plan_json['plan_graph'] = planmessage_json
        # self.json2graph(planmessage, "TASK_PLAN", node_color)
        return planmessage, json.dumps(plan_json, ensure_ascii=False)

    def json2graph(self, data, title, node_color: str = 'blue'):
        import networkx as nx
        import matplotlib.pyplot as plt
        try:
            json_data = json.loads(data)
            graph = nx.DiGraph()
            heads = []
            edges = []
            layout = {}
            for key in json_data.keys():
                idnow = json_data[key]['id']
                layout[idnow] = 0
                if json_data[key]['dep'] == []:
                    heads.append(idnow)
                else:
                    for id in json_data[key]['dep']:
                        edges.append((id, idnow))
                        layout[idnow] = max(layout[idnow], layout[id] + 1) 

            layers = {}
            for key in layout.keys():
                layerid = layout[key]
                if layerid not in layers:
                    layers[layerid] = []
                layers[layerid].append(key)
            print(layers)
            for layer, nodes in layers.items():
                graph.add_nodes_from(nodes, layer=layer)
            graph.add_edges_from(edges)
            pos = nx.multipartite_layout(graph, subset_key="layer")
            nx.draw(graph, pos=pos, with_labels=True, node_color=node_color, arrowsize=20)
            plt.title(title)
            plt.show()
        except json.decoder.JSONDecodeError:
            print("WRONG FORMAT!")
            return
                
    def json_get_completion(self, thread: Thread, message: str, inspector_request: str = None, inspector_thread: Thread = None):
        _ = False
        original_message = message
        while True:
            res = thread.get_completion(message=message, response_format='auto')
            response_information = self.my_get_completion(res)

            # try to extract json from str
            _, result = self.get_json_from_str(message=response_information)
            print(f"THREAD output:\n{result}")
            if _ == False:
                # found no json, try to get completion again
                message = "用户原始输入为: \n```\n" + original_message + "\n```\n" + "你之前的回答是:\n```\n" + result + "\n```\n" + "你之前的回答用户评价为: \n```\n" + "Your output format is wrong." + "\n```\n"
                continue

            if inspector_thread is not None:
                # seek for inspector's opinion
                inspector_type = os.getenv("DEBUG_INSPECTOR_TYPE")
                if inspector_type is not None and inspector_type == "off": # 不使用inspector
                    return result

                if _ == True:
                    inspect_query = {
                        "user_request": inspector_request,
                        "task_graph": json.loads(result)
                    }
                else:
                    inspect_query = {
                        "user_request": inspector_request,
                        "task_graph": result
                    }
                inspector_res = inspector_thread.get_completion(message=json.dumps(inspect_query, ensure_ascii=False), response_format='auto')
                inspector_result = self.my_get_completion(inspector_res)
                print(inspector_result)
                __ = self.get_inspector_review(inspector_result)

                if inspector_type is None or inspector_type == "user": # inspector回复后由用户决定
                    user_advice = input("User: [\"agree\": You agree with inspector.\n\"YES\": You agree with planner, and you should input your advice.\n\"NO\": You disagree with planner, and you should input your advice.]\n")
                    if user_advice != "agree":
                        explain = input("explain: ")
                        inspector_result = json.dumps(
                            {
                                "review": user_advice,
                                "explain": explain
                            }
                        )
                        __ = self.get_inspector_review(inspector_result)
                
                if __ == True:
                    return result
                message = "用户原始输入为: \n```\n" + original_message + "\n```\n" + "你之前的回答是:\n```\n" + result + "\n```\n" + "你之前的回答用户评价为: \n```\n" + inspector_result + "\n```\n"
                continue
            
            return result
                
    def get_inspector_review(self, message: str):
        try:
            json_res = json.loads(message)
            return json_res['review'] == "YES"
        except:
            yes_str = "YES"
            try:
                yes_index = message.index(yes_str)
                return True
            except ValueError:
                return False

    def get_json_from_str(self, message: str):
        try:
            json_res = json.loads(message)
            return True, message
        except json.decoder.JSONDecodeError:
            start_str = "```json\n"
            end_str = "\n```"
            try:
                start_index = message.rfind(start_str) + len(start_str)
                end_index = message.index(end_str, start_index)
                return True, message[start_index: end_index]
            except ValueError:
                return False, message
    
    def my_get_completion(self, res):
        while True:
            try:
                next(res)
            except StopIteration as e:
                return e.value
    
    def langgraph_test(self, repeater: Agent, rander: Agent, palindromist: Agent):
        from typing import Annotated
        from typing_extensions import TypedDict

        from langgraph.graph import StateGraph, START, END
        from langgraph.graph.message import add_messages

        from langchain_openai import ChatOpenAI
        from langchain_community.tools.tavily_search import TavilySearchResults

        class State(TypedDict):
            # Messages have the type "list". The `add_messages` function
            # in the annotation defines how this state key should be updated
            # (in this case, it appends messages to the list, rather than overwriting them)
            messages: Annotated[list, add_messages]
        graph_builder = StateGraph(State)

        repeater_thread = Thread(self.user, repeater)
        rander_thread = Thread(self.user, rander)
        palindromist_thread = Thread(self.user, palindromist)
        from langchain_core.messages.ai import AIMessage
        def chatbot_0(state: State):
            message = state["messages"][-1]
            res = rander_thread.get_completion(message.content)
            ans = self.my_get_completion(res)
            return {"messages": [AIMessage(ans)]}

        def chatbot_1(state: State):
            message = state["messages"][-1]
            res = repeater_thread.get_completion(message.content)
            ans = self.my_get_completion(res)
            return {"messages": [AIMessage(ans)]}

        
        def chatbot_2(state: State):
            message = state["messages"][-1]
            res = palindromist_thread.get_completion(message.content)
            ans = self.my_get_completion(res)
            return {"messages": [AIMessage(ans)]}

        
        graph_builder.add_node("rander", chatbot_0)
        graph_builder.add_node("repeater", chatbot_1)
        graph_builder.add_node("palindromist", chatbot_2)

        graph_builder.add_edge(START, "rander")
        graph_builder.add_edge("repeater", END)
        graph_builder.add_edge("palindromist", END)

        def route(
                state: State,
        ):
            if isinstance(state, list):
                ai_message = state[-1]
            elif messages := state.get("messages", []):
                ai_message = messages[-1]
            else:
                raise ValueError(f"No messages found in input state: {state}")
            import re
            try:
                print(ai_message)
                text = ai_message.content
                number = re.findall(r"\d+\.?\d*", text[-1])
                if int(number[-1]) < 5:
                    return "repeater"
                return "palindromist"
            except:
                return "repeater"
            
        graph_builder.add_conditional_edges(
            "rander",
            route,
            {"repeater": "repeater", "palindromist": "palindromist"},
        )
        graph = graph_builder.compile()
        import matplotlib.pyplot as plt
        from PIL import Image
        import io

        # ... (你的 graph 对象和相关代码) ...
        image_data = graph.get_graph().draw_mermaid_png()  # 获取图像字节流数据
        img = Image.open(io.BytesIO(image_data))  # 使用 PIL 读取 PNG 图像
        plt.imshow(img)  # 使用 matplotlib 显示图像
        plt.axis('off')  # 可选：隐藏坐标轴
        plt.show()
        def stream_graph_updates(user_input: str):
            for event in graph.stream({"messages": [("user", user_input)]}):
                for value in event.values():
                    print("Assistant:", value["messages"][-1].content)


        while True:
            try:
                user_input = input("User: ")
                if user_input.lower() in ["quit", "exit", "q"]:
                    print("Goodbye!")
                    break

                stream_graph_updates(user_input)
            except:
                # fallback if input() is not available
                user_input = "What do you know about LangGraph?"
                print("User: " + user_input)
                stream_graph_updates(user_input)
                break
