"""
Unit tests for citation extraction utilities.

Tests individual citation extraction functions in isolation using mocks
to ensure proper behavior without external dependencies.
"""

from unittest.mock import MagicMock

from agents.items import MessageOutputItem

from agency_swarm.utils.citation_extractor import (
    display_citations,
    extract_direct_file_annotations,
    extract_direct_file_citations_from_history,
    extract_vector_store_citations,
)


class TestExtractDirectFileAnnotations:
    """Test direct file citation extraction from message annotations."""

    def test_extracts_file_citations_from_annotations(self):
        """Test extraction of file citations from message annotations."""
        # Create mock message with file citation annotations
        mock_annotation = MagicMock()
        mock_annotation.type = "file_citation"
        mock_annotation.file_id = "file-abc123"
        mock_annotation.filename = "test_document.pdf"
        mock_annotation.index = 42

        mock_content_item = MagicMock()
        mock_content_item.annotations = [mock_annotation]

        mock_message = MagicMock()
        mock_message.id = "msg_123"
        mock_message.content = [mock_content_item]

        mock_msg_item = MagicMock(spec=MessageOutputItem)
        mock_msg_item.raw_item = mock_message

        # Test extraction
        result = extract_direct_file_annotations([mock_msg_item])

        assert "msg_123" in result
        citations = result["msg_123"]
        assert len(citations) == 1

        citation = citations[0]
        assert citation["file_id"] == "file-abc123"
        assert citation["filename"] == "test_document.pdf"
        assert citation["index"] == 42
        assert citation["type"] == "file_citation"
        assert citation["method"] == "direct_file"

    def test_handles_multiple_annotations_per_message(self):
        """Test handling multiple file citations in a single message."""
        # Create multiple annotations
        annotations = []
        for i in range(3):
            mock_annotation = MagicMock()
            mock_annotation.type = "file_citation"
            mock_annotation.file_id = f"file-{i}"
            mock_annotation.filename = f"doc_{i}.pdf"
            mock_annotation.index = i * 10
            annotations.append(mock_annotation)

        mock_content_item = MagicMock()
        mock_content_item.annotations = annotations

        mock_message = MagicMock()
        mock_message.id = "msg_multi"
        mock_message.content = [mock_content_item]

        mock_msg_item = MagicMock(spec=MessageOutputItem)
        mock_msg_item.raw_item = mock_message

        result = extract_direct_file_annotations([mock_msg_item])

        assert "msg_multi" in result
        citations = result["msg_multi"]
        assert len(citations) == 3

        # Verify each citation
        for i, citation in enumerate(citations):
            assert citation["file_id"] == f"file-{i}"
            assert citation["filename"] == f"doc_{i}.pdf"
            assert citation["index"] == i * 10

    def test_skips_messages_without_content(self):
        """Test that messages without content are skipped."""
        mock_message = MagicMock()
        mock_message.content = None

        mock_msg_item = MagicMock(spec=MessageOutputItem)
        mock_msg_item.raw_item = mock_message

        result = extract_direct_file_annotations([mock_msg_item])
        assert result == {}

    def test_skips_non_file_citation_annotations(self):
        """Test that non-file-citation annotations are ignored."""
        mock_annotation = MagicMock()
        mock_annotation.type = "image_file"  # Not a file citation

        mock_content_item = MagicMock()
        mock_content_item.annotations = [mock_annotation]

        mock_message = MagicMock()
        mock_message.id = "msg_no_citations"
        mock_message.content = [mock_content_item]

        mock_msg_item = MagicMock(spec=MessageOutputItem)
        mock_msg_item.raw_item = mock_message

        result = extract_direct_file_annotations([mock_msg_item])
        assert result == {}

    def test_handles_missing_annotation_attributes(self):
        """Test graceful handling of annotations with missing attributes."""
        mock_annotation = MagicMock()
        mock_annotation.type = "file_citation"
        # Explicitly delete the attributes to simulate missing attributes
        del mock_annotation.file_id
        del mock_annotation.filename
        del mock_annotation.index

        mock_content_item = MagicMock()
        mock_content_item.annotations = [mock_annotation]

        mock_message = MagicMock()
        mock_message.id = "msg_incomplete"
        mock_message.content = [mock_content_item]

        mock_msg_item = MagicMock(spec=MessageOutputItem)
        mock_msg_item.raw_item = mock_message

        result = extract_direct_file_annotations([mock_msg_item])

        citations = result["msg_incomplete"]
        citation = citations[0]
        assert citation["file_id"] == "unknown"
        assert citation["filename"] == "unknown"
        assert citation["index"] == 0  # Default value


class TestExtractVectorStoreCitations:
    """Test vector store citation extraction from run results."""

    def test_extracts_file_search_citations(self):
        """Test extraction of FileSearch tool citations."""
        # Create mock file search result
        mock_search_result = MagicMock()
        mock_search_result.file_id = "vs-file-123"
        mock_search_result.text = "This is the retrieved text content from the file."

        # Create mock file search tool call
        mock_tool_call = MagicMock()
        mock_tool_call.type = "file_search_call"
        mock_tool_call.id = "call_abc123"
        mock_tool_call.results = [mock_search_result]

        # Create mock run result item
        mock_item = MagicMock()
        mock_item.raw_item = mock_tool_call

        # Create mock run result
        mock_run_result = MagicMock()
        mock_run_result.new_items = [mock_item]

        result = extract_vector_store_citations(mock_run_result)

        assert len(result) == 1
        citation = result[0]
        assert citation["method"] == "vector_store"
        assert citation["file_id"] == "vs-file-123"
        assert citation["text"] == "This is the retrieved text content from the file."
        assert citation["tool_call_id"] == "call_abc123"

    def test_handles_multiple_search_results(self):
        """Test handling multiple search results from a single tool call."""
        # Create multiple search results
        search_results = []
        for i in range(3):
            mock_result = MagicMock()
            mock_result.file_id = f"vs-file-{i}"
            mock_result.text = f"Content from file {i}"
            search_results.append(mock_result)

        mock_tool_call = MagicMock()
        mock_tool_call.type = "file_search_call"
        mock_tool_call.id = "call_multi"
        mock_tool_call.results = search_results

        mock_item = MagicMock()
        mock_item.raw_item = mock_tool_call

        mock_run_result = MagicMock()
        mock_run_result.new_items = [mock_item]

        result = extract_vector_store_citations(mock_run_result)

        assert len(result) == 3
        for i, citation in enumerate(result):
            assert citation["file_id"] == f"vs-file-{i}"
            assert citation["text"] == f"Content from file {i}"
            assert citation["tool_call_id"] == "call_multi"

    def test_skips_non_file_search_items(self):
        """Test that non-file-search items are ignored."""
        mock_tool_call = MagicMock()
        mock_tool_call.type = "function_call"  # Not a file search

        mock_item = MagicMock()
        mock_item.raw_item = mock_tool_call

        mock_run_result = MagicMock()
        mock_run_result.new_items = [mock_item]

        result = extract_vector_store_citations(mock_run_result)
        assert result == []

    def test_handles_missing_results(self):
        """Test handling of file search calls without results."""
        mock_tool_call = MagicMock()
        mock_tool_call.type = "file_search_call"
        mock_tool_call.results = None

        mock_item = MagicMock()
        mock_item.raw_item = mock_tool_call

        mock_run_result = MagicMock()
        mock_run_result.new_items = [mock_item]

        result = extract_vector_store_citations(mock_run_result)
        assert result == []


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
