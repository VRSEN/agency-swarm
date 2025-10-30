from dotenv import load_dotenv
from agency_swarm import Agency
from ceo import ceo
from voice_handler import voice_handler
from email_specialist import email_specialist
from memory_manager import memory_manager

load_dotenv()

# Agency with Orchestrator-Workers pattern
# CEO coordinates all workflow through sequential handoffs
agency = Agency(
    [
        ceo,  # Entry point
        [ceo, voice_handler],  # CEO <-> Voice Handler
        [ceo, email_specialist],  # CEO <-> Email Specialist
        [ceo, memory_manager],  # CEO <-> Memory Manager
    ],
    shared_instructions="./agency_manifesto.md",
    temperature=0.5,
    max_prompt_tokens=25000,
)

if __name__ == "__main__":
    # This will be wired by qa-tester for demo/run modes
    # Options:
    # 1. agency.demo_gradio() - for web interface testing
    # 2. agency.run_demo() - for CLI testing
    # 3. Custom Telegram webhook integration
    pass
