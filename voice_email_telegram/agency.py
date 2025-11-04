from ceo.ceo import ceo
from dotenv import load_dotenv
from email_specialist.email_specialist import email_specialist
from memory_manager.memory_manager import memory_manager
from voice_handler.voice_handler import voice_handler
from routing_preprocessor import RouterPreprocessor

from agency_swarm import Agency

load_dotenv()

# Agency with Orchestrator-Workers pattern
# CEO coordinates all workflow through sequential handoffs
agency = Agency(
    agency_chart=[
        ceo,  # Entry point
        [ceo, voice_handler],  # CEO <-> Voice Handler
        [ceo, email_specialist],  # CEO <-> Email Specialist
        [ceo, memory_manager],  # CEO <-> Memory Manager
    ],
    shared_instructions="./agency_manifesto.md",
)

# Initialize routing preprocessor for deterministic intent classification
router = RouterPreprocessor()


def get_completion_with_routing(user_query: str) -> str:
    """
    Process user query with deterministic routing via preprocessor.

    This wrapper ensures that ClassifyIntent ALWAYS runs before CEO
    makes routing decisions, solving the LLM instruction-following issue.

    Args:
        user_query: Raw user query string

    Returns:
        Agency response string, or error message if processing fails
    """
    try:
        # Step 1: Deterministic classification (always happens)
        routing_result = router.preprocess(user_query)

        # Step 2: Pass enhanced query with explicit routing directive to CEO
        response = agency.get_completion(routing_result["enhanced_query"])

        return response

    except Exception as e:
        # Log error and return user-friendly message
        error_msg = f"I encountered an error processing your request: {str(e)}"
        print(f"❌ get_completion_with_routing error: {type(e).__name__}: {str(e)}")

        # Fallback: Try without routing preprocessor
        try:
            print("⚠️ Falling back to direct agency completion")
            return agency.get_completion(user_query)
        except Exception as fallback_error:
            print(f"❌ Fallback also failed: {str(fallback_error)}")
            return f"I'm having trouble processing your request. Please try rephrasing or contact support. Error: {str(e)}"


# Convenience: Allow both old and new calling patterns
def get_completion(user_query: str, use_routing: bool = True) -> str:
    """
    Get completion from agency with optional routing preprocessor.

    Args:
        user_query: User query string
        use_routing: If True, use routing preprocessor (default: True)

    Returns:
        Agency response string
    """
    if use_routing:
        return get_completion_with_routing(user_query)
    else:
        return agency.get_completion(user_query)

if __name__ == "__main__":
    from datetime import datetime

    # Test queries to validate the complete workflow
    test_queries = [
        {
            "id": 1,
            "name": "Simple Voice-to-Email (Happy Path)",
            "query": (
                "I just received a voice message saying: 'Hey, I need to email John at john@example.com about the "
                "Q4 project update. Tell him we're on track and the deliverables will be ready by end of month. "
                "Keep it professional but friendly.' Please process this and draft an email."
            ),
            "expected": "Complete workflow: transcribe -> get context -> draft -> show for approval",
        },
        {
            "id": 2,
            "name": "Email with Missing Information",
            "query": (
                "I want to send an email to Sarah about the meeting tomorrow. I think we need to reschedule because "
                "I have a conflict. Can you draft this?"
            ),
            "expected": "System should identify missing email address and ask for clarification",
        },
        {
            "id": 3,
            "name": "Draft Rejection with Revision Request",
            "query": (
                "I need to email Mike at mike@company.com. Tell him the budget proposal looks good but we need to "
                "cut 10% from the marketing line. Make it sound diplomatic. Actually, after seeing the draft, "
                "I want you to make it more direct and mention specific numbers: reduce from $100k to $90k."
            ),
            "expected": "Draft revision workflow: initial draft -> user feedback -> revised draft",
        },
        {
            "id": 4,
            "name": "Multiple Recipients",
            "query": (
                "Send an email to the team at team@startup.com, and CC alice@startup.com and bob@startup.com. "
                "Subject should be 'Weekly Standup Recap'. Tell them we completed 3 user stories, deployed to "
                "staging, and the production release is scheduled for Friday. Keep it brief and bullet-pointed."
            ),
            "expected": "Handle multiple recipients (To, CC) and structured content",
        },
        {
            "id": 5,
            "name": "Learning from Preferences",
            "query": (
                "Email Jennifer at jennifer@consulting.com about our consultation call. I prefer a warm, "
                "personable tone and always sign off with 'Best regards'. Tell her I enjoyed our discussion about "
                "the AI strategy and I'm excited to collaborate. Suggest we schedule a follow-up next week."
            ),
            "expected": "Memory manager should learn preferences (tone, signature) and use them",
        },
    ]

    print("=" * 80)
    print("VOICE EMAIL TELEGRAM AGENCY - QA TEST SUITE")
    print("=" * 80)
    print(f"Test Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total Test Queries: {len(test_queries)}")
    print("=" * 80)

    results = []

    for test in test_queries:
        print(f"\n{'=' * 80}")
        print(f"TEST {test['id']}: {test['name']}")
        print(f"{'=' * 80}")
        print(f"\nQuery: {test['query']}")
        print(f"\nExpected Behavior: {test['expected']}")
        print(f"\n{'-' * 80}")
        print("Response:")
        print(f"{'-' * 80}\n")

        try:
            response = agency.get_completion(test["query"])
            print(response)

            results.append(
                {
                    "test_id": test["id"],
                    "test_name": test["name"],
                    "status": "COMPLETED",
                    "query": test["query"],
                    "response": response,
                    "expected": test["expected"],
                }
            )

        except Exception as e:
            error_msg = f"ERROR: {str(e)}"
            print(error_msg)

            results.append(
                {
                    "test_id": test["id"],
                    "test_name": test["name"],
                    "status": "FAILED",
                    "query": test["query"],
                    "error": error_msg,
                    "expected": test["expected"],
                }
            )

        print(f"\n{'-' * 80}")
        print(f"Test {test['id']} Status: {'COMPLETED' if results[-1]['status'] == 'COMPLETED' else 'FAILED'}")
        print(f"{'=' * 80}\n")

    # Summary
    print(f"\n{'=' * 80}")
    print("TEST SUMMARY")
    print(f"{'=' * 80}")
    completed = sum(1 for r in results if r["status"] == "COMPLETED")
    failed = sum(1 for r in results if r["status"] == "FAILED")
    print(f"Total Tests: {len(results)}")
    print(f"Completed: {completed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {(completed / len(results) * 100):.1f}%")
    print(f"{'=' * 80}\n")

    # Save detailed results
    results_file = "/home/user/agency-swarm/voice_email_telegram/qa_test_results.md"
    print(f"Saving detailed results to: {results_file}")

    # Results will be saved by a separate call after execution
