"""
Tests for citation extraction utilities.

This module tests the citation extraction functionality for different types of
message content and tool call results.
"""

import pytest
from unittest.mock import Mock, MagicMock

from agency_swarm.utils.citation_extractor import (
    extract_direct_file_annotations,
    extract_vector_store_citations,
    extract_direct_file_citations_from_history,
    display_citations,
)


class TestExtractDirectFileAnnotations:
    """Test direct file annotation extraction from assistant messages."""

    def test_extract_direct_file_annotations_empty_messages(self):
        """Test extraction with empty message list."""
        result = extract_direct_file_annotations([])
        assert result == {}

    def test_extract_direct_file_annotations_no_content(self):
        """Test extraction with messages that have no content."""
        mock_message = Mock()
        mock_message.content = None
        
        mock_msg_item = Mock()
        mock_msg_item.raw_item = mock_message
        
        result = extract_direct_file_annotations([mock_msg_item])
        assert result == {}

    def test_extract_direct_file_annotations_no_annotations(self):
        """Test extraction with messages that have content but no annotations."""
        mock_content_item = Mock()
        mock_content_item.annotations = None
        
        mock_message = Mock()
        mock_message.content = [mock_content_item]
        mock_message.id = "msg_123"
        
        mock_msg_item = Mock()
        mock_msg_item.raw_item = mock_message
        
        result = extract_direct_file_annotations([mock_msg_item])
        assert result == {}

    def test_extract_direct_file_annotations_with_file_citations(self):
        """Test extraction with valid file citation annotations."""
        # Create mock annotation
        mock_annotation = Mock()
        mock_annotation.type = "file_citation"
        mock_annotation.file_id = "file_123"
        mock_annotation.filename = "test.pdf"
        mock_annotation.index = 0
        
        # Create mock content item with annotations
        mock_content_item = Mock()
        mock_content_item.annotations = [mock_annotation]
        
        # Create mock message
        mock_message = Mock()
        mock_message.content = [mock_content_item]
        mock_message.id = "msg_123"
        
        # Create mock message item
        mock_msg_item = Mock()
        mock_msg_item.raw_item = mock_message
        
        result = extract_direct_file_annotations([mock_msg_item])
        
        assert "msg_123" in result
        assert len(result["msg_123"]) == 1
        
        citation = result["msg_123"][0]
        assert citation["file_id"] == "file_123"
        assert citation["filename"] == "test.pdf"
        assert citation["index"] == 0
        assert citation["type"] == "file_citation"
        assert citation["method"] == "direct_file"

    def test_extract_direct_file_annotations_multiple_annotations(self):
        """Test extraction with multiple annotations in one message."""
        # Create multiple mock annotations
        mock_annotation1 = Mock()
        mock_annotation1.type = "file_citation"
        mock_annotation1.file_id = "file_123"
        mock_annotation1.filename = "test1.pdf"
        mock_annotation1.index = 0
        
        mock_annotation2 = Mock()
        mock_annotation2.type = "file_citation"
        mock_annotation2.file_id = "file_456"
        mock_annotation2.filename = "test2.pdf"
        mock_annotation2.index = 1
        
        # Create mock content item with annotations
        mock_content_item = Mock()
        mock_content_item.annotations = [mock_annotation1, mock_annotation2]
        
        # Create mock message
        mock_message = Mock()
        mock_message.content = [mock_content_item]
        mock_message.id = "msg_123"
        
        # Create mock message item
        mock_msg_item = Mock()
        mock_msg_item.raw_item = mock_message
        
        result = extract_direct_file_annotations([mock_msg_item])
        
        assert "msg_123" in result
        assert len(result["msg_123"]) == 2
        
        # Check first citation
        citation1 = result["msg_123"][0]
        assert citation1["file_id"] == "file_123"
        assert citation1["filename"] == "test1.pdf"
        
        # Check second citation
        citation2 = result["msg_123"][1]
        assert citation2["file_id"] == "file_456"
        assert citation2["filename"] == "test2.pdf"

    def test_extract_direct_file_annotations_non_file_citation_type(self):
        """Test extraction ignores non-file-citation annotations."""
        # Create mock annotation with different type
        mock_annotation = Mock()
        mock_annotation.type = "other_type"
        
        # Create mock content item with annotations
        mock_content_item = Mock()
        mock_content_item.annotations = [mock_annotation]
        
        # Create mock message
        mock_message = Mock()
        mock_message.content = [mock_content_item]
        mock_message.id = "msg_123"
        
        # Create mock message item
        mock_msg_item = Mock()
        mock_msg_item.raw_item = mock_message
        
        result = extract_direct_file_annotations([mock_msg_item])
        assert result == {}

    def test_extract_direct_file_annotations_missing_attributes(self):
        """Test extraction handles missing attributes gracefully."""
        # Create mock annotation with missing attributes
        mock_annotation = Mock(spec=[])  # Empty spec to prevent auto-creation of attributes
        mock_annotation.type = "file_citation"
        # Missing file_id, filename, index attributes

        # Create mock content item with annotations
        mock_content_item = Mock()
        mock_content_item.annotations = [mock_annotation]

        # Create mock message
        mock_message = Mock()
        mock_message.content = [mock_content_item]
        mock_message.id = "msg_123"

        # Create mock message item
        mock_msg_item = Mock()
        mock_msg_item.raw_item = mock_message

        result = extract_direct_file_annotations([mock_msg_item])

        assert "msg_123" in result
        citation = result["msg_123"][0]
        assert citation["file_id"] == "unknown"
        assert citation["filename"] == "unknown"
        assert citation["index"] == 0


class TestExtractVectorStoreCitations:
    """Test vector store citation extraction from run results."""

    def test_extract_vector_store_citations_empty_items(self):
        """Test extraction with empty new_items list."""
        mock_run_result = Mock()
        mock_run_result.new_items = []
        
        result = extract_vector_store_citations(mock_run_result)
        assert result == []

    def test_extract_vector_store_citations_no_file_search_calls(self):
        """Test extraction with items that are not file_search_call type."""
        mock_item = Mock()
        mock_item.raw_item = Mock()
        mock_item.raw_item.type = "other_type"
        
        mock_run_result = Mock()
        mock_run_result.new_items = [mock_item]
        
        result = extract_vector_store_citations(mock_run_result)
        assert result == []

    def test_extract_vector_store_citations_with_results(self):
        """Test extraction with valid file_search_call results."""
        # Create mock result
        mock_result = Mock()
        mock_result.file_id = "file_123"
        mock_result.text = "Sample text content"
        
        # Create mock tool call
        mock_tool_call = Mock()
        mock_tool_call.type = "file_search_call"
        mock_tool_call.id = "call_123"
        mock_tool_call.results = [mock_result]
        
        # Create mock item
        mock_item = Mock()
        mock_item.raw_item = mock_tool_call
        
        mock_run_result = Mock()
        mock_run_result.new_items = [mock_item]
        
        result = extract_vector_store_citations(mock_run_result)
        
        assert len(result) == 1
        citation = result[0]
        assert citation["method"] == "vector_store"
        assert citation["file_id"] == "file_123"
        assert citation["text"] == "Sample text content"
        assert citation["tool_call_id"] == "call_123"

    def test_extract_vector_store_citations_multiple_results(self):
        """Test extraction with multiple results in one tool call."""
        # Create multiple mock results
        mock_result1 = Mock()
        mock_result1.file_id = "file_123"
        mock_result1.text = "First text content"
        
        mock_result2 = Mock()
        mock_result2.file_id = "file_456"
        mock_result2.text = "Second text content"
        
        # Create mock tool call
        mock_tool_call = Mock()
        mock_tool_call.type = "file_search_call"
        mock_tool_call.id = "call_123"
        mock_tool_call.results = [mock_result1, mock_result2]
        
        # Create mock item
        mock_item = Mock()
        mock_item.raw_item = mock_tool_call
        
        mock_run_result = Mock()
        mock_run_result.new_items = [mock_item]
        
        result = extract_vector_store_citations(mock_run_result)
        
        assert len(result) == 2
        assert result[0]["file_id"] == "file_123"
        assert result[1]["file_id"] == "file_456"

    def test_extract_vector_store_citations_missing_attributes(self):
        """Test extraction handles missing attributes gracefully."""
        # Create mock result with missing attributes
        mock_result = Mock(spec=[])  # Empty spec to prevent auto-creation of attributes
        # Missing file_id and text attributes

        # Create mock tool call
        mock_tool_call = Mock()
        mock_tool_call.type = "file_search_call"
        mock_tool_call.id = "call_123"
        mock_tool_call.results = [mock_result]

        # Create mock item
        mock_item = Mock()
        mock_item.raw_item = mock_tool_call

        mock_run_result = Mock()
        mock_run_result.new_items = [mock_item]

        result = extract_vector_store_citations(mock_run_result)

        assert len(result) == 1
        citation = result[0]
        assert citation["file_id"] == "unknown"
        assert citation["text"] == ""


class TestExtractDirectFileCitationsFromHistory:
    """Test direct file citation extraction from thread history."""

    def test_extract_direct_file_citations_from_history_empty(self):
        """Test extraction with empty thread items."""
        result = extract_direct_file_citations_from_history([])
        assert result == []

    def test_extract_direct_file_citations_from_history_new_format(self):
        """Test extraction with new format (citations in message metadata)."""
        thread_items = [
            {
                "role": "assistant",
                "content": "Some response",
                "citations": [
                    {
                        "file_id": "file_123",
                        "filename": "test.pdf",
                        "method": "direct_file"
                    }
                ]
            }
        ]
        
        result = extract_direct_file_citations_from_history(thread_items)
        
        assert len(result) == 1
        assert result[0]["file_id"] == "file_123"
        assert result[0]["filename"] == "test.pdf"

    def test_extract_direct_file_citations_from_history_legacy_format(self):
        """Test extraction with legacy format (synthetic user messages)."""
        thread_items = [
            {
                "role": "user",
                "content": """[DIRECT_FILE_CITATIONS]
File ID: file_123
Filename: test.pdf
Text Index: 0
Type: file_citation"""
            }
        ]
        
        result = extract_direct_file_citations_from_history(thread_items)
        
        assert len(result) == 1
        citation = result[0]
        assert citation["file_id"] == "file_123"
        assert citation["filename"] == "test.pdf"
        assert citation["index"] == 0
        assert citation["type"] == "file_citation"
        assert citation["method"] == "direct_file"

    def test_extract_direct_file_citations_from_history_no_citations(self):
        """Test extraction with thread items that have no citations."""
        thread_items = [
            {
                "role": "user",
                "content": "Regular user message"
            },
            {
                "role": "assistant",
                "content": "Regular assistant response"
            }
        ]
        
        result = extract_direct_file_citations_from_history(thread_items)
        assert result == []


class TestDisplayCitations:
    """Test citation display functionality."""

    def test_display_citations_empty_list(self, capsys):
        """Test display with empty citations list."""
        result = display_citations([])
        captured = capsys.readouterr()
        
        assert result is False
        assert "❌ No citations found" in captured.out

    def test_display_citations_with_type_label(self, capsys):
        """Test display with citation type label."""
        result = display_citations([], citation_type="direct")
        captured = capsys.readouterr()
        
        assert result is False
        assert "❌ No direct citations found" in captured.out

    def test_display_citations_single_citation(self, capsys):
        """Test display with single citation."""
        citations = [
            {
                "method": "direct_file",
                "file_id": "file_123",
                "filename": "test.pdf",
                "index": 0
            }
        ]
        
        result = display_citations(citations)
        captured = capsys.readouterr()
        
        assert result is True
        assert "✅ Found 1 citation(s)" in captured.out
        assert "Citation 1 [direct_file]" in captured.out
        assert "File ID: file_123" in captured.out
        assert "Filename: test.pdf" in captured.out
        assert "Text Index: 0" in captured.out

    def test_display_citations_vector_store_with_content(self, capsys):
        """Test display with vector store citation including content preview."""
        citations = [
            {
                "method": "vector_store",
                "file_id": "file_123",
                "tool_call_id": "call_123",
                "text": "This is a very long text content that should be truncated when displayed as a preview in the citation output"
            }
        ]
        
        result = display_citations(citations)
        captured = capsys.readouterr()
        
        assert result is True
        assert "Citation 1 [vector_store]" in captured.out
        assert "Tool Call: call_123" in captured.out
        assert "Content: This is a very long text content that should be truncated when displayed as a preview in the citatio..." in captured.out

    def test_display_citations_multiple_citations(self, capsys):
        """Test display with multiple citations."""
        citations = [
            {
                "method": "direct_file",
                "file_id": "file_123",
                "filename": "test1.pdf"
            },
            {
                "method": "vector_store",
                "file_id": "file_456",
                "tool_call_id": "call_456"
            }
        ]
        
        result = display_citations(citations, citation_type="mixed")
        captured = capsys.readouterr()
        
        assert result is True
        assert "✅ Found 2 citation(s) mixed" in captured.out
        assert "Citation 1 [direct_file]" in captured.out
        assert "Citation 2 [vector_store]" in captured.out
