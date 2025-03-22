import json
import os
import sys
from uuid import uuid4

import gradio as gr
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath("."))

from agency_swarm import Agency, Agent, set_openai_key
from agency_swarm.tools import FileSearch

# Load environment variables
load_dotenv()

# Set OpenAI key
openai_key = os.getenv("OPENAI_API_KEY")
if not openai_key:
    raise ValueError("OPENAI_API_KEY not found in environment variables")
set_openai_key(openai_key)

# Demo data - simple product list
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


# Simple agent definitions with minimal instructions
class ProductExpertAgent(Agent):
    def __init__(self):
        super().__init__(
            name="ProductExpert",
            description="Technical product expert with deep knowledge of specifications and features",
            instructions="""You are a Product Expert with technical knowledge.
1. Focus on technical specifications and factual product information
2. Provide objective comparisons between products
3. Explain technical features without making personal recommendations
Be precise and technical but understandable.""",
            tools=[FileSearch],
        )


class CustomerAdvisorAgent(Agent):
    def __init__(self):
        super().__init__(
            name="CustomerAdvisor",
            description="Customer-focused advisor who understands user needs",
            instructions="""You are a Customer Advisor focused on user needs.
1. Understand what the customer is looking for and why
2. Consult with the Product Expert when you need technical information
3. Make personalized recommendations that match customer needs
4. Explain benefits in customer-friendly language
Be empathetic, helpful, and focused on customer satisfaction.""",
            tools=[FileSearch],
        )


class SmartShopperAgency:
    def __init__(self):
        # Initialize agents
        self.advisor = CustomerAdvisorAgent()
        self.expert = ProductExpertAgent()

        # Create agency with communication flows
        self.agency = Agency(
            [
                self.advisor,  # Entry point - customer talks to advisor first
                [self.advisor, self.expert],  # Advisor can consult the product expert
            ],
            shared_instructions="""Help customers find the right products through natural collaboration.
The Customer Advisor understands customer needs and makes personalized recommendations.
The Product Expert provides technical details and specifications when needed.""",
        )

    def get_response(self, message, user_id=None):
        """Process message and return response"""
        if user_id:
            message = f"[User: {user_id}] {message}"

        response = self.agency.get_completion(message)
        return response


def main():
    """Run the Smart Shopper demo"""

    # Create temporary product data file in current directory
    with open("products.json", "w") as f:
        json.dump(PRODUCTS, f, indent=2)
    print(f"Created products.json with {len(PRODUCTS)} products")

    # Create agency
    agency = SmartShopperAgency()

    # Create simple Gradio interface
    with gr.Blocks(theme=gr.themes.Soft(primary_hue="blue")) as demo:
        gr.Markdown("# 🛍️ Smart Shopper Virtual Assistant")
        gr.Markdown("""Ask about products and get personalized recommendations from our virtual shopping assistants.

Our system combines:
- A **Customer Advisor** who understands your needs
- A **Product Expert** who provides technical details

Together, they help you find the perfect product!""")

        # User ID for context
        user_id = gr.Textbox(
            label="Your name (optional)",
            placeholder="Enter your name or leave blank",
            value="customer_" + str(uuid4())[:4],
        )

        # Chat interface
        chatbot = gr.Chatbot(height=500, type="messages")

        with gr.Row():
            msg = gr.Textbox(
                label="Your message",
                placeholder="Tell us what you're looking for, e.g., 'I need durable headphones for my daily commute'",
            )
            send = gr.Button("Ask assistants")

        def process_message(message, chat_history, user_id_val):
            """Process user message and update chat history"""
            if not message:
                return "", chat_history

            # Get response
            response = agency.get_response(
                message=message, user_id=user_id_val if user_id_val.strip() else None
            )

            # Update chat history
            chat_history.append({"role": "user", "content": message})
            chat_history.append({"role": "assistant", "content": response})

            return "", chat_history

        # Connect UI components
        send.click(process_message, [msg, chatbot, user_id], [msg, chatbot])
        msg.submit(process_message, [msg, chatbot, user_id], [msg, chatbot])

    # Print instructions
    print("\n🛍️ Smart Shopper Virtual Assistant")
    print("\nExample questions:")
    print("  - 'I'm looking for headphones for my daily commute on the subway'")
    print("  - 'I need a smartphone with a great camera for social media'")
    print("  - 'What laptop would be good for a design student on a budget?'")

    # Launch demo
    try:
        demo.launch()
    finally:
        # Clean up temporary file when done
        if os.path.exists("products.json"):
            os.remove("products.json")
            print("Cleaned up products.json")


if __name__ == "__main__":
    main()
