import gradio as gr

from agency_swarm import set_openai_key
from agency_swarm.agency.agency import Agency
from tests.ceo.ceo import Ceo
from tests.test_agent.test_agent import TestAgent
from tests.test_agent2.test_agent2 import TestAgent2
import sys
sys.path.insert(0, '../agency_swarm')

set_openai_key("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")

test_agent1 = TestAgent()
test_agent2 = TestAgent2()
ceo = Ceo()

agency = Agency([
    ceo,
    [ceo, test_agent1, test_agent2],
    [ceo, test_agent2],
], shared_instructions="./manifesto.md")

with gr.Blocks() as demo:
    chatbot = gr.Chatbot()
    msg = gr.Textbox()
    clear = gr.Button("Clear")

    def user(user_message, history):
        # Append the user message with a placeholder for bot response
        user_message = "👤 User: " + user_message.strip()
        return "", history + [[user_message, None]]

    def bot(history):
        # Replace this with your actual chatbot logic
        gen = agency.yield_completions(message=history[-1][0])

        try:
            # Yield each message from the generator
            for bot_message in gen:
                if bot_message.sender_name.lower() == "user":
                    continue

                message = bot_message.get_sender_emoji() + " " + bot_message.get_formatted_content()

                history.append((None, message))
                yield history
        except StopIteration:
            # Handle the end of the conversation if necessary
            pass

    # Chain the events
    msg.submit(user, [msg, chatbot], [msg, chatbot], queue=False).then(
        bot, chatbot, chatbot
    )
    clear.click(lambda: None, None, chatbot, queue=False)

    # Enable queuing for streaming intermediate outputs
    demo.queue()

# Launch the demo
demo.launch()

