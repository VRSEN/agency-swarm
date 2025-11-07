import json

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class ClassifyIntent(BaseTool):
    """
    Classifies user queries into intent categories for optimal routing.

    This tool performs fast keyword-based intent classification to determine
    how the CEO agent should handle incoming user queries. Classification
    occurs BEFORE routing to specialist agents.

    Intent Categories:
    - EMAIL_FETCH: User wants to read/view existing emails
    - EMAIL_DRAFT: User wants to send/compose new email
    - KNOWLEDGE_QUERY: User asking about stored information (cocktails, recipes, business data)
    - PREFERENCE_QUERY: User asking about their own preferences/settings
    - AMBIGUOUS: Cannot confidently classify

    Performance: Optimized for <500ms classification using keyword matching.
    """

    query: str = Field(
        ...,
        description="The user query to classify",
        min_length=1,
    )

    def run(self):
        """
        Classifies the user query into an intent category.

        Returns:
            JSON string with intent, confidence score (0.0-1.0), reasoning, and original query
        """
        # Normalize query for matching
        query_lower = self.query.lower().strip()

        # Keyword maps for each intent category
        # Order matters: More specific patterns first
        EMAIL_FETCH_KEYWORDS = [
            "what email",
            "show email",
            "check inbox",
            "read email",
            "my messages",
            "unread",
            "last email",
            "recent email",
            "latest email",
            "new email",
            "inbox",
            "email from",
            "what is the last",
            "what is the latest",
            "show me the email",
            "last emails",
            "recent emails",
            "latest emails",
            "what are my emails",
            "what are my last",
            "what are the emails",
            "show me my emails",
            "my last emails",
        ]

        EMAIL_DRAFT_KEYWORDS = [
            "send email",
            "draft email",
            "email to",
            "compose",
            "write to",
            "send to",
            "email about",
            "message to",
            "draft an email",
            "write an email",
        ]

        KNOWLEDGE_QUERY_KEYWORDS = [
            # Recipe queries (both contractions and expansions)
            "what's in", "what is in",
            "recipe for", "recipes for",
            "ingredients for", "ingredients in", "ingredients",

            # Cocktail/drink queries (singular and plural)
            "cocktail", "cocktails",
            "drink", "drinks",
            "beverage", "beverages",

            # Question formats
            "what do we", "what do we have",
            "what are", "what is",
            "do we have", "do you have",

            # Action queries
            "show me", "tell me about",
            "how to make", "how do i make",
            "list of", "list all",

            # Seasonal/category queries (singular and plural)
            "summer cocktails", "summer cocktail", "summer drinks",
            "winter cocktails", "winter cocktail", "winter drinks",
            "spring cocktails", "spring cocktail",
            "fall cocktails", "fall cocktail", "autumn cocktails",

            # Menu queries
            "menu", "our menu", "the menu",
        ]

        PREFERENCE_QUERY_KEYWORDS = [
            "my signature",
            "email signature",
            "how do i sign",
            "my preferences",
            "my style",
            "how do i usually",
            "my settings",
            "my profile",
            "my information",
            "what's my",
            "what is my",
        ]

        # Classification logic with confidence scoring
        matches = {
            "EMAIL_FETCH": 0.0,
            "EMAIL_DRAFT": 0.0,
            "KNOWLEDGE_QUERY": 0.0,
            "PREFERENCE_QUERY": 0.0,
        }

        # Priority order: PREFERENCE > EMAIL_DRAFT > EMAIL_FETCH > KNOWLEDGE
        # This prevents "my email signature" from matching EMAIL_FETCH/DRAFT

        # Count keyword matches for each category
        for keyword in PREFERENCE_QUERY_KEYWORDS:
            if keyword in query_lower:
                matches["PREFERENCE_QUERY"] += 1

        # Only check other categories if PREFERENCE didn't match strongly
        if matches["PREFERENCE_QUERY"] < 2:
            for keyword in EMAIL_DRAFT_KEYWORDS:
                if keyword in query_lower:
                    matches["EMAIL_DRAFT"] += 1

            for keyword in EMAIL_FETCH_KEYWORDS:
                if keyword in query_lower:
                    matches["EMAIL_FETCH"] += 1

            for keyword in KNOWLEDGE_QUERY_KEYWORDS:
                if keyword in query_lower:
                    matches["KNOWLEDGE_QUERY"] += 1

        # Determine intent and confidence
        max_matches = max(matches.values())

        if max_matches == 0:
            # No keywords matched - ambiguous
            result = {
                "intent": "AMBIGUOUS",
                "confidence": 0.0,
                "reasoning": "No keywords matched for any intent category",
                "query": self.query,
            }
        else:
            # Find intent with highest matches
            intent = max(matches, key=matches.get)

            # Calculate confidence (0.0-1.0 scale)
            # Base confidence on number of matches (cap at 3 for normalization)
            confidence = min(max_matches / 3.0, 1.0)

            # Check for competing intents (multiple categories matched)
            competing_intents = sum(1 for count in matches.values() if count > 0)
            if competing_intents > 1:
                # Reduce confidence if multiple intents detected
                confidence *= 0.7

            # Generate reasoning
            matched_category = {
                "EMAIL_FETCH": "email retrieval/viewing",
                "EMAIL_DRAFT": "email composition/sending",
                "KNOWLEDGE_QUERY": "knowledge retrieval from stored data",
                "PREFERENCE_QUERY": "user preference/settings inquiry",
            }

            reasoning = f"Query contains {int(max_matches)} keyword(s) indicating {matched_category[intent]}"

            if competing_intents > 1:
                reasoning += f". Note: {competing_intents} intent categories detected, confidence reduced."

            result = {
                "intent": intent,
                "confidence": round(confidence, 2),
                "reasoning": reasoning,
                "query": self.query,
            }

        return json.dumps(result, indent=2)


if __name__ == "__main__":
    # Test ClassifyIntent with specific queries
    print("Testing ClassifyIntent tool...\n")
    print("=" * 80)

    test_cases = [
        {
            "query": "What's in the butterfly?",
            "expected_intent": "KNOWLEDGE_QUERY",
            "description": "Knowledge query about cocktail ingredients",
        },
        {
            "query": "What summer cocktails do we have?",
            "expected_intent": "KNOWLEDGE_QUERY",
            "description": "Knowledge query about available cocktails",
        },
        {
            "query": "What is the last email?",
            "expected_intent": "EMAIL_FETCH",
            "description": "Email retrieval request",
        },
        {
            "query": "Send email to John",
            "expected_intent": "EMAIL_DRAFT",
            "description": "Email composition request",
        },
        {
            "query": "What's my email signature?",
            "expected_intent": "PREFERENCE_QUERY",
            "description": "User preference inquiry",
        },
        {
            "query": "Random query about nothing specific",
            "expected_intent": "AMBIGUOUS",
            "description": "Ambiguous query with no clear intent",
        },
        {
            "query": "Show me the recipe for margarita",
            "expected_intent": "KNOWLEDGE_QUERY",
            "description": "Recipe knowledge request",
        },
        {
            "query": "Draft an email to Sarah about the meeting",
            "expected_intent": "EMAIL_DRAFT",
            "description": "Email drafting with context",
        },
        {
            "query": "Check my inbox for unread messages",
            "expected_intent": "EMAIL_FETCH",
            "description": "Inbox check request",
        },
        {
            "query": "How do I usually sign my emails?",
            "expected_intent": "PREFERENCE_QUERY",
            "description": "User signature preference query",
        },
    ]

    passed = 0
    failed = 0

    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test['description']}")
        print(f"Query: '{test['query']}'")
        print(f"Expected: {test['expected_intent']}\n")

        tool = ClassifyIntent(query=test["query"])
        result_str = tool.run()
        result = json.loads(result_str)

        print(f"Result: {result['intent']}")
        print(f"Confidence: {result['confidence']}")
        print(f"Reasoning: {result['reasoning']}")

        # Validate result
        if result["intent"] == test["expected_intent"]:
            print("✓ PASSED")
            passed += 1
        else:
            print(f"✗ FAILED (got {result['intent']}, expected {test['expected_intent']})")
            failed += 1

        print("-" * 80)

    print(f"\n{'=' * 80}")
    print(f"Test Summary: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print(f"Success Rate: {(passed/len(test_cases)*100):.1f}%")
    print(f"{'=' * 80}\n")

    # Performance note
    print("\nPerformance Note:")
    print("This tool uses keyword matching for fast classification (<500ms).")
    print("For production use, consider implementing caching for frequent queries.")
    print("\nAll tests completed!")
