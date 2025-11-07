#!/usr/bin/env python3
"""
Email Writing Pattern Analysis Tool
Analyzes Ashley's past emails to extract writing style patterns
and stores them in Mem0 for the email specialist agent to use.
"""
import re
from collections import Counter
from typing import Dict, List, Optional

from pydantic import Field

from agency_swarm.tools import BaseTool


class AnalyzeWritingPatterns(BaseTool):
    """
    Analyzes past emails from Gmail to extract Ashley's writing style patterns.

    This tool:
    1. Fetches sent emails from Gmail using GmailSearchMessages
    2. Analyzes greetings, closings, tone, vocabulary, emoji usage
    3. Categorizes patterns by email type (wedding, corporate, invoice, etc.)
    4. Stores patterns in Mem0 for future email drafting

    The patterns are used by DraftEmailFromVoice to replicate Ashley's authentic voice.
    """

    email_type: str = Field(
        ...,
        description="Type of emails to analyze: 'wedding', 'corporate', 'invoice', 'existing_client', or 'all'"
    )

    max_emails: int = Field(
        default=50,
        description="Maximum number of emails to analyze (default: 50)"
    )

    def run(self) -> str:
        """
        Analyze writing patterns from past emails and store in Mem0.
        """
        try:
            # Import required tools
            from .GmailFetchEmails import GmailFetchEmails
            from .GmailSearchMessages import GmailSearchMessages
            from .Mem0AddMemory import Mem0AddMemory

            # Build search query based on email type
            search_queries = {
                'wedding': 'from:me (wedding OR bride OR ceremony OR reception OR cocktail bar)',
                'corporate': 'from:me (corporate OR company OR business OR team OR professional)',
                'invoice': 'from:me (invoice OR payment OR bill OR balance)',
                'existing_client': 'from:me (confirmed OR all set OR see you)',
                'all': 'from:me'
            }

            query = search_queries.get(self.email_type, search_queries['all'])

            self._log(f"🔍 Searching for {self.email_type} emails with query: {query}")

            # Search for emails
            search_tool = GmailSearchMessages(
                query=query,
                max_results=self.max_emails
            )

            search_result = search_tool.run()

            if "No messages found" in search_result or "Error" in search_result:
                return f"❌ Failed to find emails: {search_result}"

            # Parse message IDs from search result
            message_ids = self._extract_message_ids(search_result)

            if not message_ids:
                return "❌ No message IDs found in search results"

            self._log(f"✓ Found {len(message_ids)} emails to analyze")

            # Fetch and analyze emails
            patterns = {
                'greetings': Counter(),
                'closings': Counter(),
                'tone_indicators': Counter(),
                'vocabulary': Counter(),
                'emoji_usage': Counter(),
                'structure': {
                    'short': 0,  # < 100 words
                    'medium': 0,  # 100-300 words
                    'long': 0  # > 300 words
                },
                'punctuation': {
                    'exclamation': 0,
                    'question': 0,
                    'period': 0
                }
            }

            analyzed_count = 0

            for msg_id in message_ids[:self.max_emails]:
                try:
                    fetch_tool = GmailFetchEmails(
                        message_ids=[msg_id],
                        max_results=1
                    )

                    email_content = fetch_tool.run()

                    if email_content and "Error" not in email_content:
                        self._analyze_email(email_content, patterns)
                        analyzed_count += 1

                        if analyzed_count % 10 == 0:
                            self._log(f"  Analyzed {analyzed_count}/{len(message_ids)} emails...")

                except Exception as e:
                    self._log(f"⚠️ Error analyzing email {msg_id}: {str(e)}")
                    continue

            if analyzed_count == 0:
                return "❌ Failed to analyze any emails"

            self._log(f"✓ Analyzed {analyzed_count} emails")

            # Generate pattern summary
            summary = self._generate_pattern_summary(patterns, analyzed_count)

            # Store patterns in Mem0
            self._log("💾 Storing patterns in Mem0...")

            mem0_tool = Mem0AddMemory(
                memory_text=summary,
                category=f"writing_style_{self.email_type}"
            )

            mem0_result = mem0_tool.run()

            if "successfully" in mem0_result.lower():
                return f"""✅ Writing Pattern Analysis Complete!

📊 Analyzed {analyzed_count} {self.email_type} emails

{summary}

✓ Patterns stored in Mem0 under category: writing_style_{self.email_type}

The email specialist agent can now use these patterns to draft emails in your authentic voice!
"""
            else:
                return f"""⚠️ Analysis complete but storage failed:

{summary}

Error storing in Mem0: {mem0_result}
"""

        except Exception as e:
            return f"❌ Error during analysis: {str(e)}"

    def _extract_message_ids(self, search_result: str) -> List[str]:
        """Extract message IDs from Gmail search results."""
        # Look for message IDs in the format "Message ID: ..."
        ids = re.findall(r'Message ID:\s*([a-zA-Z0-9]+)', search_result)

        # Alternative format: "id": "..."
        if not ids:
            ids = re.findall(r'"id":\s*"([a-zA-Z0-9]+)"', search_result)

        return list(set(ids))  # Remove duplicates

    def _analyze_email(self, email_content: str, patterns: Dict):
        """Analyze a single email and update pattern counters."""
        # Extract body text
        body = self._extract_body(email_content)

        if not body:
            return

        # Analyze greetings
        greeting = self._extract_greeting(body)
        if greeting:
            patterns['greetings'][greeting] += 1

        # Analyze closings
        closing = self._extract_closing(body)
        if closing:
            patterns['closings'][closing] += 1

        # Analyze tone indicators
        if '!' in body:
            patterns['tone_indicators']['enthusiastic'] += body.count('!')
            patterns['punctuation']['exclamation'] += body.count('!')

        if '?' in body:
            patterns['punctuation']['question'] += body.count('?')

        patterns['punctuation']['period'] += body.count('.')

        # Detect warmth indicators
        warmth_words = ['love', 'excited', 'happy', 'great', 'wonderful', 'amazing']
        for word in warmth_words:
            if word.lower() in body.lower():
                patterns['tone_indicators']['warm'] += 1

        # Detect professional indicators
        professional_words = ['professional', 'service', 'investment', 'regarding', 'please']
        for word in professional_words:
            if word.lower() in body.lower():
                patterns['tone_indicators']['professional'] += 1

        # Analyze emojis
        emojis = re.findall(r'[\U0001F300-\U0001F9FF]', body)
        for emoji in emojis:
            patterns['emoji_usage'][emoji] += 1

        # Analyze structure
        word_count = len(body.split())
        if word_count < 100:
            patterns['structure']['short'] += 1
        elif word_count < 300:
            patterns['structure']['medium'] += 1
        else:
            patterns['structure']['long'] += 1

        # Extract key vocabulary (excluding common words)
        common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'is', 'are', 'was', 'were', 'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'my', 'your', 'his', 'her', 'our', 'their'}

        words = re.findall(r'\b[a-z]+\b', body.lower())
        for word in words:
            if word not in common_words and len(word) > 3:
                patterns['vocabulary'][word] += 1

    def _extract_body(self, email_content: str) -> Optional[str]:
        """Extract email body from email content."""
        # Try to find body between common markers
        body_patterns = [
            r'Body:(.*?)(?:Subject:|From:|To:|$)',
            r'Content:(.*?)(?:Subject:|From:|To:|$)',
            r'Message:(.*?)(?:Subject:|From:|To:|$)'
        ]

        for pattern in body_patterns:
            match = re.search(pattern, email_content, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # If no markers found, use entire content
        return email_content

    def _extract_greeting(self, body: str) -> Optional[str]:
        """Extract greeting from email body."""
        # Common greeting patterns
        greeting_patterns = [
            r'^(Hey[^,\n]*)[,\n]',
            r'^(Hi[^,\n]*)[,\n]',
            r'^(Hello[^,\n]*)[,\n]',
            r'^(Bonjour[^,\n]*)[,\n]',
            r'^(Good morning[^,\n]*)[,\n]',
            r'^(Good afternoon[^,\n]*)[,\n]'
        ]

        for pattern in greeting_patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _extract_closing(self, body: str) -> Optional[str]:
        """Extract closing from email body."""
        # Common closing patterns
        closing_patterns = [
            r'(Cheers[^,\n]*)[,\n]?\s*Ashley',
            r'(Best[^,\n]*)[,\n]?\s*Ashley',
            r'(Thanks[^,\n]*)[,\n]?\s*Ashley',
            r'(À bientôt[^,\n]*)[,\n]?\s*Ashley',
            r'(Best regards[^,\n]*)[,\n]?\s*Ashley',
            r'(Warm regards[^,\n]*)[,\n]?\s*Ashley'
        ]

        for pattern in closing_patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Check for standalone closings
        standalone_patterns = [
            r'\n(Cheers!?)\s*$',
            r'\n(Best!?)\s*$',
            r'\n(Thanks!?)\s*$',
            r'\n(À bientôt!?)\s*$'
        ]

        for pattern in standalone_patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _generate_pattern_summary(self, patterns: Dict, analyzed_count: int) -> str:
        """Generate a human-readable summary of writing patterns."""
        summary_parts = []

        summary_parts.append(f"## Ashley's {self.email_type.title()} Email Writing Patterns")
        summary_parts.append(f"Based on analysis of {analyzed_count} emails\n")

        # Greetings
        if patterns['greetings']:
            top_greetings = patterns['greetings'].most_common(3)
            summary_parts.append("### Greetings")
            for greeting, count in top_greetings:
                percentage = (count / analyzed_count) * 100
                summary_parts.append(f"- **{greeting}**: {percentage:.0f}% of emails")
            summary_parts.append("")

        # Closings
        if patterns['closings']:
            top_closings = patterns['closings'].most_common(3)
            summary_parts.append("### Closings")
            for closing, count in top_closings:
                percentage = (count / analyzed_count) * 100
                summary_parts.append(f"- **{closing}**: {percentage:.0f}% of emails")
            summary_parts.append("")

        # Tone
        summary_parts.append("### Tone Characteristics")

        total_exclamations = patterns['punctuation']['exclamation']
        avg_exclamations = total_exclamations / analyzed_count
        summary_parts.append(f"- **Enthusiasm level**: {avg_exclamations:.1f} exclamation marks per email")

        warmth_count = patterns['tone_indicators'].get('warm', 0)
        if warmth_count > 0:
            summary_parts.append(f"- **Warmth**: Uses warm language in {(warmth_count/analyzed_count)*100:.0f}% of emails")

        professional_count = patterns['tone_indicators'].get('professional', 0)
        if professional_count > 0:
            summary_parts.append(f"- **Professionalism**: Uses professional language in {(professional_count/analyzed_count)*100:.0f}% of emails")
        summary_parts.append("")

        # Structure
        summary_parts.append("### Email Structure")
        total_structure = sum(patterns['structure'].values())
        if total_structure > 0:
            for length, count in patterns['structure'].items():
                percentage = (count / total_structure) * 100
                summary_parts.append(f"- **{length.title()} emails** (< 100 / 100-300 / >300 words): {percentage:.0f}%")
        summary_parts.append("")

        # Emoji usage
        if patterns['emoji_usage']:
            summary_parts.append("### Emoji Usage")
            top_emojis = patterns['emoji_usage'].most_common(5)
            for emoji, count in top_emojis:
                summary_parts.append(f"- {emoji}: Used {count} times")
            summary_parts.append("")

        # Key vocabulary
        if patterns['vocabulary']:
            summary_parts.append("### Key Vocabulary")
            top_words = patterns['vocabulary'].most_common(10)
            vocab_list = [f"'{word}'" for word, _ in top_words]
            summary_parts.append(f"- Most used words: {', '.join(vocab_list)}")
            summary_parts.append("")

        return "\n".join(summary_parts)

    def _log(self, message: str):
        """Log a message (helper for debugging)."""
        print(f"[AnalyzeWritingPatterns] {message}")


if __name__ == "__main__":
    # Test the tool
    tool = AnalyzeWritingPatterns(
        email_type="wedding",
        max_emails=10
    )
    print(tool.run())
