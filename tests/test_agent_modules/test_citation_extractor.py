"""
Unit tests for citation extraction utilities.
"""

from unittest.mock import MagicMock

from agents.items import MessageOutputItem, ToolCallItem
from openai.types.responses.response_file_search_tool_call import (
    ResponseFileSearchToolCall,
    Result as FileSearchResult,
)
from openai.types.responses.response_output_message import ResponseOutputMessage, ResponseOutputText
from openai.types.responses.response_output_text import AnnotationFileCitation, AnnotationURLCitation

from agency_swarm.agent.core import Agent
from agency_swarm.utils.citation_extractor import (
    display_citations,
    extract_direct_file_annotations,
    extract_direct_file_citations_from_history,
    extract_vector_store_citations,
)


class TestExtractDirectFileAnnotations:
    """Test direct file citation extraction from message annotations."""

    @staticmethod
    def _message_item(content: list[ResponseOutputText], message_id: str) -> MessageOutputItem:
        agent = Agent(name="Annotator", instructions="Collect citations")
        message = ResponseOutputMessage(
            id=message_id,
            content=content,
            role="assistant",
            status="completed",
            type="message",
        )
        return MessageOutputItem(agent=agent, raw_item=message)

    def test_extracts_file_citations_from_annotations(self):
        """Ensure annotations backed by SDK models are captured."""
        annotation = AnnotationFileCitation(
            file_id="file-abc123",
            filename="test_document.pdf",
            index=42,
            type="file_citation",
        )
        content_item = ResponseOutputText(annotations=[annotation], text="Here you go", type="output_text")
        msg_item = self._message_item([content_item], message_id="msg_123")

        result = extract_direct_file_annotations([msg_item])

        assert "msg_123" in result
        citation = result["msg_123"][0]
        assert citation["file_id"] == "file-abc123"
        assert citation["filename"] == "test_document.pdf"
        assert citation["index"] == 42
        assert citation["type"] == "file_citation"
        assert citation["method"] == "direct_file"

    def test_handles_multiple_annotations_per_message(self):
        """Handle multiple file citations within a single message."""
        annotations = [
            AnnotationFileCitation(
                file_id=f"file-{i}",
                filename=f"doc_{i}.pdf",
                index=i * 10,
                type="file_citation",
            )
            for i in range(3)
        ]
        content_item = ResponseOutputText(annotations=annotations, text="Multiple refs", type="output_text")
        msg_item = self._message_item([content_item], message_id="msg_multi")

        result = extract_direct_file_annotations([msg_item])

        citations = result["msg_multi"]
        assert len(citations) == 3
        assert {c["file_id"] for c in citations} == {"file-0", "file-1", "file-2"}

    def test_skips_messages_without_content(self):
        """Messages with no content yield no citations."""
        msg_item = self._message_item([], message_id="msg_empty")
        assert extract_direct_file_annotations([msg_item]) == {}

    def test_skips_non_file_citation_annotations(self):
        """Annotations of other types are ignored."""
        url_annotation = AnnotationURLCitation(
            start_index=0,
            end_index=5,
            title="Example",
            type="url_citation",
            url="https://example.com",
        )
        content_item = ResponseOutputText(annotations=[url_annotation], text="See link", type="output_text")
        msg_item = self._message_item([content_item], message_id="msg_no_citations")

        assert extract_direct_file_annotations([msg_item]) == {}


class TestExtractVectorStoreCitations:
    """Test vector store citation extraction from run results."""

    def test_extracts_file_search_citations(self):
        """Extract citations from a typed FileSearch tool call."""
        tool_call = ResponseFileSearchToolCall(
            id="call_sdk",
            queries=["report"],
            status="completed",
            type="file_search_call",
            results=[FileSearchResult(file_id="file-sdk", text="Findings content")],
        )

        run_result = MagicMock()
        run_result.new_items = [ToolCallItem(agent=MagicMock(), raw_item=tool_call)]

        result = extract_vector_store_citations(run_result)

        assert result[0]["file_id"] == "file-sdk"
        assert result[0]["text"] == "Findings content"
        assert result[0]["tool_call_id"] == "call_sdk"

    def test_handles_multiple_search_results(self):
        """Handle multiple search results within a single tool call."""
        tool_call = ResponseFileSearchToolCall(
            id="call_multi",
            queries=["reports"],
            status="completed",
            type="file_search_call",
            results=[FileSearchResult(file_id=f"vs-file-{i}", text=f"Content from file {i}") for i in range(3)],
        )

        run_result = MagicMock()
        run_result.new_items = [ToolCallItem(agent=MagicMock(), raw_item=tool_call)]

        citations = extract_vector_store_citations(run_result)

        assert len(citations) == 3
        assert {c["file_id"] for c in citations} == {"vs-file-0", "vs-file-1", "vs-file-2"}

    def test_missing_file_id_defaults_to_unknown(self):
        """Fallback to 'unknown' when file_id is absent in the tool result."""
        tool_call = ResponseFileSearchToolCall(
            id="call_unknown",
            queries=["reports"],
            status="completed",
            type="file_search_call",
            results=[FileSearchResult(file_id=None, text="Content without identifier")],
        )

        run_result = MagicMock()
        run_result.new_items = [ToolCallItem(agent=MagicMock(), raw_item=tool_call)]

        citations = extract_vector_store_citations(run_result)

        assert len(citations) == 1
        assert citations[0]["file_id"] == "unknown"

    def test_handles_missing_results(self):
        """Gracefully handle file search calls without results."""
        tool_call = ResponseFileSearchToolCall(
            id="call_empty",
            queries=["anything"],
            status="completed",
            type="file_search_call",
            results=None,
        )

        run_result = MagicMock()
        run_result.new_items = [ToolCallItem(agent=MagicMock(), raw_item=tool_call)]

        assert extract_vector_store_citations(run_result) == []

    def test_skips_non_file_search_items(self):
        """Ignore items that are not file-search tool calls."""
        tool_call = MagicMock()
        tool_call.type = "function_call"

        run_result = MagicMock()
        run_result.new_items = [ToolCallItem(agent=MagicMock(), raw_item=tool_call)]

        assert extract_vector_store_citations(run_result) == []


class TestExtractDirectFileCitationsFromHistory:
    """Test citation extraction from thread conversation history."""

    def test_extracts_new_format_citations(self):
        """Test extraction from new format (citations in message metadata)."""
        thread_items = [
            {
                "role": "assistant",
                "content": "Here's the information from the file.",
                "citations": [
                    {"file_id": "file-new123", "filename": "new_format.pdf", "index": 15, "method": "direct_file"}
                ],
            }
        ]

        result = extract_direct_file_citations_from_history(thread_items)

        assert len(result) == 1
        citation = result[0]
        assert citation["file_id"] == "file-new123"
        assert citation["filename"] == "new_format.pdf"
        assert citation["index"] == 15
        assert citation["method"] == "direct_file"

    def test_extracts_legacy_format_citations(self):
        """Test extraction from legacy format (synthetic user messages)."""
        thread_items = [
            {
                "role": "user",
                "content": """[DIRECT_FILE_CITATIONS]
File ID: file-legacy456
Filename: legacy_document.docx
Text Index: 25
Type: file_citation

File ID: file-legacy789
Filename: another_doc.pdf
Text Index: 50
Type: file_citation
""",
            }
        ]

        result = extract_direct_file_citations_from_history(thread_items)

        assert len(result) == 2

        first_citation = result[0]
        assert first_citation["file_id"] == "file-legacy456"
        assert first_citation["filename"] == "legacy_document.docx"
        assert first_citation["index"] == 25
        assert first_citation["type"] == "file_citation"
        assert first_citation["method"] == "direct_file"

        second_citation = result[1]
        assert second_citation["file_id"] == "file-legacy789"
        assert second_citation["filename"] == "another_doc.pdf"
        assert second_citation["index"] == 50

    def test_handles_mixed_message_types(self):
        """Test handling thread with both citation and non-citation messages."""
        thread_items = [
            {"role": "user", "content": "What's in this file?"},
            {
                "role": "assistant",
                "content": "According to the document...",
                "citations": [{"file_id": "file-mixed", "filename": "mixed.pdf"}],
            },
            {"role": "user", "content": "Thanks for the info!"},
        ]

        result = extract_direct_file_citations_from_history(thread_items)

        assert len(result) == 1
        assert result[0]["file_id"] == "file-mixed"

    def test_handles_empty_thread(self):
        """Test handling of empty thread items."""
        result = extract_direct_file_citations_from_history([])
        assert result == []

    def test_handles_malformed_legacy_format(self):
        """Test graceful handling of malformed legacy citation format."""
        thread_items = [
            {
                "role": "user",
                "content": """[DIRECT_FILE_CITATIONS]
File ID: incomplete-citation
Filename: test.pdf
# Missing Text Index and Type fields
""",
            }
        ]

        result = extract_direct_file_citations_from_history(thread_items)
        # Should not crash, but may not extract complete citation
        assert isinstance(result, list)


class TestDisplayCitations:
    """Test citation display functionality."""

    def test_displays_vector_store_citations(self, capsys):
        """Test display of vector store citations."""
        citations = [
            {
                "method": "vector_store",
                "file_id": "vs-123",
                "text": (
                    "This is a long piece of text that should be truncated in the preview "
                    "because it exceeds the 100 character limit for display purposes."
                ),
                "tool_call_id": "call_123",
            }
        ]

        result = display_citations(citations, "vector store")
        captured = capsys.readouterr()

        assert result is True
        assert "✅ Found 1 citation(s) vector store:" in captured.out
        assert "Citation 1 [vector_store]:" in captured.out
        assert "File ID: vs-123" in captured.out
        assert "Tool Call: call_123" in captured.out
        assert (
            "Content: This is a long piece of text that should be truncated in the preview "
            "because it exceeds the 100 char..."
        ) in captured.out

    def test_displays_direct_file_citations(self, capsys):
        """Test display of direct file citations."""
        citations = [
            {
                "method": "direct_file",
                "file_id": "file-456",
                "filename": "document.pdf",
                "index": 42,
                "type": "file_citation",
            }
        ]

        result = display_citations(citations)
        captured = capsys.readouterr()

        assert result is True
        assert "✅ Found 1 citation(s):" in captured.out
        assert "Citation 1 [direct_file]:" in captured.out
        assert "File ID: file-456" in captured.out
        assert "Filename: document.pdf" in captured.out
        assert "Text Index: 42" in captured.out

    def test_handles_no_citations(self, capsys):
        """Test display when no citations are provided."""
        result = display_citations([])
        captured = capsys.readouterr()

        assert result is False
        assert "❌ No citations found" in captured.out

    def test_handles_no_citations_with_type(self, capsys):
        """Test display when no citations with specific type."""
        result = display_citations([], "direct file")
        captured = capsys.readouterr()

        assert result is False
        assert "❌ No direct file citations found" in captured.out

    def test_displays_multiple_citations(self, capsys):
        """Test display of multiple citations."""
        citations = [
            {"method": "direct_file", "file_id": "file-1", "filename": "doc1.pdf"},
            {"method": "vector_store", "file_id": "vs-2", "text": "Short text", "tool_call_id": "call_2"},
        ]

        result = display_citations(citations)
        captured = capsys.readouterr()

        assert result is True
        assert "✅ Found 2 citation(s):" in captured.out
        assert "Citation 1 [direct_file]:" in captured.out
        assert "Citation 2 [vector_store]:" in captured.out
        assert "Content: Short text" in captured.out  # Short text not truncated

    def test_handles_missing_citation_fields(self, capsys):
        """Test display with citations missing some fields."""
        citations = [
            {
                "method": "unknown",
                # Missing most fields
            }
        ]

        result = display_citations(citations)
        captured = capsys.readouterr()

        assert result is True
        assert "Citation 1 [unknown]:" in captured.out
        assert "File ID: unknown" in captured.out
