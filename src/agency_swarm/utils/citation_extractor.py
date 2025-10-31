"""
Citation extraction utilities for Agency Swarm.

This module contains utilities for extracting file citations from different types of
message content and tool call results.
"""

import logging

from agents import RunResult
from agents.items import MessageOutputItem, ToolCallItem
from openai.types.responses import ResponseFileSearchToolCall
from openai.types.responses.response_file_search_tool_call import Result as ResponseFileSearchResult
from openai.types.responses.response_output_message import ResponseOutputMessage
from openai.types.responses.response_output_text import AnnotationFileCitation, ResponseOutputText

logger = logging.getLogger(__name__)


def extract_direct_file_annotations(
    assistant_messages: list[MessageOutputItem], agent_name: str | None = None
) -> dict[str, list[dict]]:
    """
    Extract file citations from direct file uploads (annotations in message content).

    When files are attached directly to messages (not via FileSearch tool),
    OpenAI includes annotations in the response content that indicate where citations
    should be placed in the text.

    Args:
        assistant_messages: List of MessageOutputItem objects to examine for annotations
        agent_name: Agent name (kept for compatibility, not used in new implementation)

    Returns:
        Dictionary mapping message IDs to their citation data
    """
    citations_by_message = {}

    for msg_item in assistant_messages:
        message = msg_item.raw_item
        if not isinstance(message, ResponseOutputMessage):
            continue

        annotations_found: list[dict] = []
        for content_item in message.content:
            if not isinstance(content_item, ResponseOutputText):
                continue
            annotations = content_item.annotations or []
            for annotation in annotations:
                if isinstance(annotation, AnnotationFileCitation):
                    annotations_found.append(_build_file_citation(annotation))

        # Store citations mapped to message ID
        if annotations_found:
            citations_by_message[message.id] = annotations_found
            logger.debug(f"Extracted {len(annotations_found)} direct file citations for message_id: {message.id}")

    return citations_by_message


def extract_vector_store_citations(run_result: RunResult) -> list[dict]:
    """Extract FileSearch tool citations from RunResult.new_items"""
    citations = []

    for item in run_result.new_items:
        if not isinstance(item, ToolCallItem):
            continue

        tool_call = item.raw_item
        if not isinstance(tool_call, ResponseFileSearchToolCall):
            continue

        results: list[ResponseFileSearchResult] = tool_call.results or []
        tool_call_id = tool_call.id

        for result in results:
            file_id, text = _resolve_file_search_result(result)
            citations.append(
                {
                    "method": "vector_store",
                    "file_id": file_id,
                    "text": text,
                    "tool_call_id": tool_call_id,
                }
            )

    return citations


def extract_direct_file_citations_from_history(thread_items):
    """Extract direct file citations from thread conversation history.

    This function now supports both legacy format (synthetic user messages)
    and new format (citations in message metadata).
    """
    citations = []

    for item in thread_items:
        # New format: Check for citations in message metadata
        if item.get("role") == "assistant" and "citations" in item:
            item_citations = item.get("citations", [])
            citations.extend(item_citations)

        # Legacy format: Check for synthetic user messages with [DIRECT_FILE_CITATIONS]
        elif item.get("role") == "user" and "[DIRECT_FILE_CITATIONS]" in str(item.get("content", "")):
            content = item.get("content", "")
            lines = content.split("\n")
            current_citation = {}

            for line in lines:
                line = line.strip()
                if line.startswith("File ID:"):
                    current_citation["file_id"] = line.split(":", 1)[1].strip()
                elif line.startswith("Filename:"):
                    current_citation["filename"] = line.split(":", 1)[1].strip()
                elif line.startswith("Text Index:"):
                    current_citation["index"] = int(line.split(":", 1)[1].strip())
                elif line.startswith("Type:"):
                    current_citation["type"] = line.split(":", 1)[1].strip()
                    # End of citation block
                    if current_citation:
                        current_citation["method"] = "direct_file"
                        citations.append(current_citation.copy())
                        current_citation = {}

    return citations


def display_citations(citations, citation_type=""):
    """Display extracted citations in a readable format"""
    if not citations:
        print(f"❌ No {citation_type} citations found" if citation_type else "❌ No citations found")
        return False

    type_label = f" {citation_type}" if citation_type else ""
    print(f"✅ Found {len(citations)} citation(s){type_label}:")

    for i, citation in enumerate(citations, 1):
        method = citation.get("method", "unknown")
        print(f"   Citation {i} [{method}]:")
        print(f"     File ID: {citation.get('file_id', 'unknown')}")

        if "tool_call_id" in citation:
            print(f"     Tool Call: {citation['tool_call_id']}")
        if "filename" in citation:
            print(f"     Filename: {citation['filename']}")
        if "index" in citation:
            print(f"     Text Index: {citation['index']}")

        # Show content preview for vector store citations
        if citation.get("method") == "vector_store" and "text" in citation:
            content_preview = citation["text"][:100] + "..." if len(citation["text"]) > 100 else citation["text"]
            print(f"     Content: {content_preview}")
        print()
    return True


def _build_file_citation(annotation: AnnotationFileCitation) -> dict:
    return {
        "file_id": annotation.file_id,
        "filename": annotation.filename,
        "index": annotation.index,
        "type": annotation.type,
        "method": "direct_file",
    }


def _resolve_file_search_result(result: ResponseFileSearchResult) -> tuple[str, str]:
    file_id_value = result.file_id
    if isinstance(file_id_value, str) and file_id_value:
        file_id = file_id_value
    elif file_id_value is None:
        file_id = "unknown"
    else:
        file_id = str(file_id_value)

    text = result.text or ""
    return file_id, text
