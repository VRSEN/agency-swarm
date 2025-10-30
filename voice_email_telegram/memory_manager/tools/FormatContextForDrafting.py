from agency_swarm.tools import BaseTool
from pydantic import Field
import json
from dotenv import load_dotenv

load_dotenv()

class FormatContextForDrafting(BaseTool):
    """
    Structures user memories and preferences into a format optimized for email drafting.
    Takes raw memory search results and organizes them into actionable context
    that the Email Specialist can use to create personalized, high-quality drafts.
    """

    memories: str = Field(
        ...,
        description="JSON string containing array of memory objects from MEM0_SEARCH or MEM0_GET_ALL"
    )

    recipient: str = Field(
        default="",
        description="Email recipient (used to filter relevant memories)"
    )

    intent: str = Field(
        default="",
        description="Optional JSON string with email intent to help prioritize relevant memories"
    )

    def run(self):
        """
        Organizes memories into structured context for email drafting.
        Returns a JSON string with categorized preferences and suggestions.
        """
        try:
            # Parse memories
            memories_data = json.loads(self.memories)

            # Initialize context structure
            context = {
                "signature": None,
                "tone_preference": "professional",
                "style_notes": [],
                "recipient_info": {},
                "common_phrases": [],
                "subject_preferences": [],
                "relevant_history": [],
                "confidence_score": 0.0
            }

            # Parse intent if provided
            intent_data = {}
            if self.intent:
                try:
                    intent_data = json.loads(self.intent)
                except:
                    pass

            # If no memories provided, return default context
            if not memories_data or (isinstance(memories_data, dict) and "memories" in memories_data and not memories_data["memories"]):
                context["message"] = "No memories found. Using default preferences."
                return json.dumps(context, indent=2)

            # Handle different memory formats
            memory_list = memories_data
            if isinstance(memories_data, dict):
                if "memories" in memories_data:
                    memory_list = memories_data["memories"]
                elif "results" in memories_data:
                    memory_list = memories_data["results"]

            # Process each memory
            total_confidence = 0
            count = 0

            for memory in memory_list:
                if not isinstance(memory, dict):
                    continue

                # Extract memory content
                memory_text = memory.get("text", memory.get("content", ""))
                memory_category = memory.get("category", memory.get("type", "general"))
                memory_confidence = float(memory.get("confidence", 0.5))

                # Update confidence tracking
                total_confidence += memory_confidence
                count += 1

                # Categorize and extract information
                memory_lower = memory_text.lower()

                # Signature detection
                if "sign" in memory_lower or "signature" in memory_lower or "closing" in memory_lower:
                    if memory_confidence > 0.6:
                        # Extract signature from memory
                        for line in memory_text.split("\n"):
                            if any(word in line.lower() for word in ["regards", "sincerely", "thanks", "cheers", "best"]):
                                context["signature"] = line.strip()
                                break

                # Tone preferences
                if "tone" in memory_lower or "casual" in memory_lower or "formal" in memory_lower:
                    if "casual" in memory_lower:
                        context["tone_preference"] = "casual"
                    elif "formal" in memory_lower:
                        context["tone_preference"] = "formal"
                    elif "friendly" in memory_lower:
                        context["tone_preference"] = "friendly"
                    elif "professional" in memory_lower:
                        context["tone_preference"] = "professional"

                # Style notes
                if any(word in memory_lower for word in ["prefer", "always", "never", "style"]):
                    context["style_notes"].append({
                        "note": memory_text,
                        "confidence": memory_confidence
                    })

                # Recipient-specific information
                if self.recipient and self.recipient.lower() in memory_lower:
                    if "recipient_info" not in context or not isinstance(context["recipient_info"], dict):
                        context["recipient_info"] = {}

                    context["recipient_info"]["memory"] = memory_text
                    context["recipient_info"]["confidence"] = memory_confidence

                # Subject line preferences
                if "subject" in memory_lower:
                    context["subject_preferences"].append(memory_text)

                # Common phrases or patterns
                if "always" in memory_lower or "usually" in memory_lower:
                    context["common_phrases"].append(memory_text)

                # Historical context
                if "sent" in memory_lower or "email" in memory_lower:
                    context["relevant_history"].append({
                        "summary": memory_text,
                        "confidence": memory_confidence
                    })

            # Calculate overall confidence
            if count > 0:
                context["confidence_score"] = total_confidence / count

            # Limit arrays to most relevant items
            context["style_notes"] = sorted(
                context["style_notes"],
                key=lambda x: x["confidence"],
                reverse=True
            )[:5]

            context["relevant_history"] = sorted(
                context["relevant_history"],
                key=lambda x: x["confidence"],
                reverse=True
            )[:3]

            # Add summary
            context["summary"] = {
                "total_memories_processed": count,
                "has_signature": bool(context["signature"]),
                "has_recipient_info": bool(context["recipient_info"]),
                "style_notes_count": len(context["style_notes"]),
                "history_items": len(context["relevant_history"])
            }

            return json.dumps(context, indent=2)

        except json.JSONDecodeError as e:
            return json.dumps({
                "error": f"Invalid JSON in memories: {str(e)}",
                "signature": None,
                "tone_preference": "professional"
            })
        except Exception as e:
            return json.dumps({
                "error": f"Error formatting context: {str(e)}",
                "signature": None,
                "tone_preference": "professional"
            })


if __name__ == "__main__":
    # Test context formatting with various memory scenarios
    print("Testing FormatContextForDrafting...")

    # Test 1: Complete set of memories
    print("\n1. Complete memory set:")
    memories = json.dumps({
        "memories": [
            {
                "text": "User prefers casual tone when emailing Sarah at supplier.com",
                "category": "tone_preference",
                "confidence": 0.9
            },
            {
                "text": "Always signs emails with 'Best regards, John Smith'",
                "category": "signature",
                "confidence": 0.95
            },
            {
                "text": "Prefers brief, direct emails without long introductions",
                "category": "style",
                "confidence": 0.8
            },
            {
                "text": "Successfully sent shipment update to john@acmecorp.com using professional tone",
                "category": "history",
                "confidence": 0.7
            }
        ]
    })
    tool = FormatContextForDrafting(memories=memories, recipient="sarah@supplier.com")
    result = tool.run()
    print(result)

    # Test 2: Recipient-specific memories
    print("\n2. Recipient-specific memories:")
    memories = json.dumps({
        "memories": [
            {
                "text": "Sarah at supplier.com prefers casual communication",
                "confidence": 0.85
            },
            {
                "text": "When emailing Sarah, always mention order quantities upfront",
                "confidence": 0.9
            },
            {
                "text": "Sarah responds best to friendly tone with 'Thanks' closing",
                "confidence": 0.8
            }
        ]
    })
    tool = FormatContextForDrafting(
        memories=memories,
        recipient="sarah@supplier.com"
    )
    result = tool.run()
    print(result)

    # Test 3: No memories found
    print("\n3. No memories:")
    memories = json.dumps({"memories": []})
    tool = FormatContextForDrafting(memories=memories)
    result = tool.run()
    print(result)

    # Test 4: Subject line preferences
    print("\n4. Subject line preferences:")
    memories = json.dumps({
        "memories": [
            {
                "text": "Always include [URGENT] in subject line for time-sensitive emails",
                "category": "subject_preference",
                "confidence": 0.9
            },
            {
                "text": "Subject lines should be clear and action-oriented",
                "confidence": 0.75
            }
        ]
    })
    tool = FormatContextForDrafting(memories=memories)
    result = tool.run()
    print(result)

    # Test 5: With email intent
    print("\n5. With email intent:")
    memories = json.dumps({
        "memories": [
            {
                "text": "User prefers professional tone for client emails",
                "confidence": 0.85
            },
            {
                "text": "Signs client emails with 'Best regards, Sarah Johnson, Account Manager'",
                "confidence": 0.9
            }
        ]
    })
    intent = json.dumps({
        "recipient": "client@example.com",
        "subject": "Project Update",
        "tone": "professional"
    })
    tool = FormatContextForDrafting(memories=memories, intent=intent)
    result = tool.run()
    print(result)

    # Test 6: Mixed confidence levels
    print("\n6. Mixed confidence memories:")
    memories = json.dumps({
        "memories": [
            {
                "text": "Maybe prefers formal tone?",
                "confidence": 0.3
            },
            {
                "text": "Definitely uses 'Cheers' for informal emails",
                "confidence": 0.95
            },
            {
                "text": "Possibly likes bullet points",
                "confidence": 0.5
            },
            {
                "text": "Always includes phone number in signature for urgent matters",
                "confidence": 0.88
            }
        ]
    })
    tool = FormatContextForDrafting(memories=memories)
    result = tool.run()
    print(result)

    # Test 7: Alternative memory format
    print("\n7. Alternative memory format (results array):")
    memories = json.dumps({
        "results": [
            {
                "content": "User tone is professional",
                "type": "preference",
                "confidence": 0.8
            }
        ]
    })
    tool = FormatContextForDrafting(memories=memories)
    result = tool.run()
    print(result)

    print("\nAll tests completed!")
