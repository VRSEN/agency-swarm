import logging
import os
import shutil
import sys

import gradio as gr
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath("."))

from agency_swarm import Agency, Agent, set_openai_key
from agency_swarm.tools import FileSearch
from agency_swarm.util import init_tracking

# Configure logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

openai_key = os.getenv("OPENAI_API_KEY")
if not openai_key:
    raise ValueError("OPENAI_API_KEY not found in environment variables")
set_openai_key(openai_key)

PRODUCTS = [
    {
        "name": "Sony WH-1000XM4",
        "category": "Headphones",
        "price": 349,
        "features": ["Noise cancellation", "Wireless", "30h battery"],
    },
    {
        "name": "Bose QuietComfort 45",
        "category": "Headphones",
        "price": 329,
        "features": ["Premium noise cancellation", "Wireless", "24h battery"],
    },
    {
        "name": "Apple AirPods Pro",
        "category": "Headphones",
        "price": 249,
        "features": ["Active noise cancellation", "Wireless", "Water resistant"],
    },
    {
        "name": "JBL Tune 510BT",
        "category": "Headphones",
        "price": 49,
        "features": ["Wireless", "40h battery", "Budget friendly"],
    },
    {
        "name": "iPhone 14 Pro",
        "category": "Smartphones",
        "price": 999,
        "features": ["A16 chip", "48MP camera", "Dynamic Island"],
    },
    {
        "name": "Samsung Galaxy S23",
        "category": "Smartphones",
        "price": 799,
        "features": ["Snapdragon 8 Gen 2", "50MP camera", "Adaptive display"],
    },
    {
        "name": "Google Pixel 7",
        "category": "Smartphones",
        "price": 599,
        "features": ["Tensor G2 chip", "Great camera", "Pure Android"],
    },
    {
        "name": "MacBook Pro 16",
        "category": "Laptops",
        "price": 2499,
        "features": ["M2 Pro/Max chip", "Up to 32 GPU cores", "Liquid Retina XDR"],
    },
    {
        "name": "Dell XPS 15",
        "category": "Laptops",
        "price": 1899,
        "features": ["12th Gen Intel i7/i9", "NVIDIA RTX 3050/3050 Ti", '15.6" OLED'],
    },
    {
        "name": "ASUS ROG Zephyrus G14",
        "category": "Laptops",
        "price": 1399,
        "features": ["AMD Ryzen 9", "NVIDIA RTX 3060", "Compact gaming"],
    },
]


class CustomerAdvisorAgent(Agent):
    def __init__(self):
        super().__init__(
            name="CustomerAdvisor",
            description="Friendly advisor who understands customer needs and use cases",
            instructions="""You are a Customer Advisor focused on understanding people.
1. Understand the customer's lifestyle and needs
2. Ask about their use cases and requirements
3. Translate technical features into real-world benefits
4. Consult the Product Expert when technical details are needed
5. Make recommendations based on how people will actually use the product
Be friendly and focus on real-world usage scenarios.""",
        )


class ProductExpertAgent(Agent):
    def __init__(self):
        super().__init__(
            name="ProductExpert",
            description="Technical product expert who provides accurate specifications and comparisons",
            instructions="""You are a Product Expert focused on technical accuracy.
1. Provide detailed technical specifications when asked
2. Make objective product comparisons based on features
3. Explain technical terms in clear language
4. Focus on facts and specifications, not personal opinions
Be precise and technical, but explain things clearly.""",
            tools=[FileSearch],
            files_folder="./product_data",
        )


def main():
    # Setup product data
    if os.path.exists("product_data"):
        shutil.rmtree("product_data")
    os.makedirs("product_data")

    # Create products.txt file with basic product information
    with open("product_data/products.txt", "w") as f:
        for product in PRODUCTS:
            f.write(f"Product: {product['name']}\n")
            f.write(f"Category: {product['category']}\n")
            f.write(f"Price: ${product['price']}\n")
            f.write(f"Features: {', '.join(product['features'])}\n")
            f.write("\n")
    print(f"Created products.txt with {len(PRODUCTS)} products")

    # Initialize observability tracking
    init_tracking("langfuse")  # Initialize Langfuse tracking
    init_tracking(
        "local", db_path="smart_shopper.db"
    )  # Initialize local tracking with custom db path

    try:
        # Create agents
        advisor = CustomerAdvisorAgent()
        expert = ProductExpertAgent()

        # Create agency with clear role distinction
        agency = Agency(
            [
                advisor,
                [advisor, expert],
            ],
            shared_instructions="""Work together to help customers find the right products:
- Customer Advisor: Understand needs and translate them into product requirements
- Product Expert: Provide accurate technical information when needed
Use the products.txt file to access the product catalog.""",
        )

        with gr.Blocks(theme=gr.themes.Soft(primary_hue="blue")) as demo:
            gr.Markdown("# 🛍️ Smart Shopper Virtual Assistant")
            gr.Markdown("""Ask about products and get personalized recommendations from our virtual shopping assistants:

- A **Customer Advisor** who understands your needs and lifestyle
- A **Product Expert** who knows all the technical details

Together, they combine understanding with expertise to help you find the perfect product!""")

            chatbot = gr.Chatbot(height=500, type="messages")

            with gr.Row():
                with gr.Column(scale=8):
                    msg = gr.Textbox(
                        label="Your message",
                        placeholder="Tell us what you're looking for, e.g., 'I need headphones for my daily commute' or 'Can you explain the camera specs of the iPhone 14 Pro?'",
                        container=False,
                    )
                with gr.Column(scale=1):
                    send = gr.Button("Ask assistants", size="lg", variant="primary")

            # Add loading status text
            status = gr.Markdown("", elem_id="status")

            def process_message(message, chat_history):
                if not message:
                    yield "", chat_history, ""
                    return

                # Immediately update the chat with the user's message and show thinking status
                chat_history.append({"role": "user", "content": message})
                yield "", chat_history, ""

                try:
                    # Get the response from the agency
                    response = agency.get_completion(message)
                    chat_history.append({"role": "assistant", "content": response})
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    chat_history.append(
                        {
                            "role": "assistant",
                            "content": f"Sorry, an error occurred: {str(e)}",
                        }
                    )

                yield "", chat_history, ""

            # Update the click and submit handlers to include the status component
            send.click(process_message, [msg, chatbot], [msg, chatbot, status])
            msg.submit(process_message, [msg, chatbot], [msg, chatbot, status])

        print("\n🛍️ Smart Shopper Virtual Assistant")
        print("\nExample questions:")
        print(
            "  - 'I need headphones for my daily commute' (Customer Advisor will understand your needs)"
        )
        print(
            "  - 'What's the battery life of the Sony WH-1000XM4?' (Product Expert will provide specs)"
        )
        print(
            "  - 'I need a laptop for video editing' (Both agents will help - needs + specs)"
        )
        print("\nObservability:")
        print("  - Check Langfuse dashboard for detailed analytics")
        print("  - Local tracking data is stored in smart_shopper.db")

        demo.launch()
    finally:
        # Clean up resources
        if os.path.exists("product_data"):
            shutil.rmtree("product_data")
            print("Cleaned up product_data directory")


if __name__ == "__main__":
    main()
