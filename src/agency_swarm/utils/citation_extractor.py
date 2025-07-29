"""
Citation extraction utilities for Agency Swarm.

This module contains utilities for extracting file citations from different types of
message content and tool call results.
"""

import logging

from agents.items import MessageOutputItem
from agents.run import TResponseInputItem
from agency_swarm.messages.message_formatter import MessageFormatter

logger = logging.getLogger(__name__)


def extract_direct_file_annotations(assistant_messages: list[MessageOutputItem], agent_name: str) -> list[TResponseInputItem]:
    """
    Extract file citations from direct file uploads (annotations in message content).

    When files are attached directly to messages (not via FileSearch tool),
    OpenAI includes annotations in the response content that indicate where citations
    should be placed in the text.

    Args:
        assistant_messages: List of MessageOutputItem objects to examine for annotations

    Returns:
        List of synthetic assistant messages containing extracted annotation data
    """
    synthetic_outputs = []

    for msg_item in assistant_messages:
        message = msg_item.raw_item
        if not hasattr(message, "content") or not message.content:
            continue

        # Look for annotations in each content item
        annotations_found = []
        for content_item in message.content:
            if hasattr(content_item, "annotations") and content_item.annotations:
                # Extract file citations from annotations
                for annotation in content_item.annotations:
                    if hasattr(annotation, "type") and annotation.type == "file_citation":
                        citation_info = {
                            "file_id": getattr(annotation, "file_id", "unknown"),
                            "filename": getattr(annotation, "filename", "unknown"),
                            "index": getattr(annotation, "index", 0),
                            "type": annotation.type,
                        }
                        annotations_found.append(citation_info)

        # Create synthetic message for annotations if any were found
        if annotations_found:
            annotation_content = (
                f"[DIRECT_FILE_CITATIONS] Message ID: {message.id}\nAnnotation Type: direct_file_citations\n"
            )

            for i, citation in enumerate(annotations_found, 1):
                annotation_content += f"Citation {i}:\n"
                annotation_content += f"  File ID: {citation['file_id']}\n"
                annotation_content += f"  Filename: {citation['filename']}\n"
                annotation_content += f"  Text Index: {citation['index']}\n"
                annotation_content += f"  Type: {citation['type']}\n\n"

            synthetic_outputs.append(MessageFormatter.add_agency_metadata({"role": "user", "content": annotation_content}, agent=agent_name, caller_agent=None))
            logger.debug(
                f"Created direct file citations message for message_id: {message.id}, found {len(annotations_found)} citations"
            )

    return synthetic_outputs


def extract_vector_store_citations(run_result):
    """Extract FileSearch tool citations from RunResult.new_items"""
    citations = []

    for item in run_result.new_items:
        if hasattr(item, "raw_item") and hasattr(item.raw_item, "type"):
            if item.raw_item.type == "file_search_call":
                tool_call = item.raw_item
                if hasattr(tool_call, "results") and tool_call.results:
                    for result in tool_call.results:
                        citation = {
                            "method": "vector_store",
                            "file_id": getattr(result, "file_id", "unknown"),
                            "text": getattr(result, "text", ""),
                            "tool_call_id": tool_call.id,
                        }
                        citations.append(citation)

    return citations


def extract_direct_file_citations_from_history(thread_items):
    """Extract direct file citations from thread conversation history"""
    citations = []

    for item in thread_items:
        if item.get("role") == "assistant" and "[DIRECT_FILE_CITATIONS]" in str(item.get("content", "")):
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
