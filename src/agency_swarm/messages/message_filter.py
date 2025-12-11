"""Message filtering functionality for removing unwanted message types."""

import logging

from agents.items import TResponseInputItem
from agents.models.fake_id import FAKE_RESPONSES_ID

logger = logging.getLogger(__name__)


class MessageFilter:
    """Handles filtering of messages based on type and content."""

    # Message types that should be filtered out
    FILTERED_TYPES = {"mcp_list_tools", "openai_list_tools"}

    # === PATTERN 1: call_id linking ===
    # These message pairs are linked by call_id field
    CALL_ID_CALL_TYPES = {
        # OpenAI types
        "function_call",
        "computer_call",
        "apply_patch_call",
        "custom_tool_call",
        "shell_call",
        "local_shell_call",
        # Agents SDK item types
        "tool_call_item",
        "handoff_call_item",
    }

    CALL_ID_OUTPUT_TYPES = {
        # OpenAI types
        "function_call_output",
        "computer_call_output",
        "apply_patch_call_output",
        "custom_tool_call_output",
        "shell_call_output",
        "local_shell_call_output",
        # Agents SDK item types
        "tool_call_output_item",
        "handoff_output_item",
    }

    # === PATTERN 2: approval_request_id linking ===
    # Response references request's id via approval_request_id field
    MCP_APPROVAL_REQUEST_TYPES = {"mcp_approval_request", "mcp_approval_request_item"}
    MCP_APPROVAL_RESPONSE_TYPES = {"mcp_approval_response", "mcp_approval_response_item"}

    @staticmethod
    def should_filter(message: TResponseInputItem) -> bool:
        """Determine if a message should be filtered out.

        Args:
            message: The input response item to check

        Returns:
            bool: True if the message should be filtered out, False otherwise
        """
        message_type = message.get("type")
        if message_type in MessageFilter.FILTERED_TYPES:
            logger.debug(f"Filtering out message with type: {message_type}")
            return True
        return False

    @staticmethod
    def filter_messages(messages: list[TResponseInputItem]) -> list[TResponseInputItem]:
        """Filter out unwanted message types from a message list.

        Args:
            messages: List of message dictionaries to filter

        Returns:
            list[TResponseInputItem]: Filtered list of messages
        """
        original_count = len(messages)
        filtered = [msg for msg in messages if not MessageFilter.should_filter(msg)]

        if len(filtered) < original_count:
            logger.info(f"Filtered out {original_count - len(filtered)} messages")

        return filtered

    @staticmethod
    def remove_orphaned_messages(
        messages: list[TResponseInputItem],
    ) -> list[TResponseInputItem]:
        """Remove paired-message violations (missing outputs or context neighbors).

        OpenAI requires that every call-type message has a matching output, and that
        certain items (e.g. reasoning summaries) keep their original follower. If
        either side is missing, the API raises an error. This function strips any
        invalid fragments to keep histories safe to replay.

        Pattern 1 (call_id linking):
            Call types: function_call, computer_call, shell_call, local_shell_call,
                apply_patch_call, custom_tool_call, tool_call_item, handoff_call_item
            Output types: function_call_output, computer_call_output, shell_call_output,
                local_shell_call_output, apply_patch_call_output, custom_tool_call_output,
                tool_call_output_item, handoff_output_item

        Pattern 2 (approval_request_id linking):
            mcp_approval_request[_item] <-> mcp_approval_response[_item]

        Pattern 3 (reasoning chains):
            Every `reasoning` item must be followed by its originally adjacent item.

        Args:
            messages: List of message dictionaries

        Returns:
            list[TResponseInputItem]: Messages with orphaned messages removed
        """
        # === PATTERN 1: call_id linking ===
        call_ids_from_calls: set[str] = set()
        call_ids_from_outputs: set[str] = set()

        # === PATTERN 2: approval_request_id linking ===
        approval_request_ids: set[str] = set()  # mcp_approval_request.id
        approval_response_ids: set[str] = set()  # mcp_approval_response.approval_request_id

        for msg in messages:
            msg_type = msg.get("type")

            # Pattern 1: call_id linking
            # Both call types and output types use 'call_id' for linking
            if msg_type in MessageFilter.CALL_ID_CALL_TYPES:
                call_id = msg.get("call_id")
                if isinstance(call_id, str) and call_id:
                    call_ids_from_calls.add(call_id)
            elif msg_type in MessageFilter.CALL_ID_OUTPUT_TYPES:
                # For outputs, the reference is in 'call_id' field
                call_id = msg.get("call_id")
                if isinstance(call_id, str) and call_id:
                    call_ids_from_outputs.add(call_id)

            # Pattern 2: approval_request_id linking
            if msg_type in MessageFilter.MCP_APPROVAL_REQUEST_TYPES:
                msg_id = msg.get("id")
                if isinstance(msg_id, str) and msg_id:
                    approval_request_ids.add(msg_id)
            elif msg_type in MessageFilter.MCP_APPROVAL_RESPONSE_TYPES:
                approval_id = msg.get("approval_request_id")
                if isinstance(approval_id, str) and approval_id:
                    approval_response_ids.add(approval_id)

        # Find matched IDs
        matched_call_ids = call_ids_from_calls & call_ids_from_outputs
        matched_approval_ids = approval_request_ids & approval_response_ids

        # Log orphaned messages
        orphaned_calls = call_ids_from_calls - matched_call_ids
        orphaned_outputs = call_ids_from_outputs - matched_call_ids
        orphaned_requests = approval_request_ids - matched_approval_ids
        orphaned_responses = approval_response_ids - matched_approval_ids

        if orphaned_calls:
            logger.info(f"Removing {len(orphaned_calls)} orphaned calls: {orphaned_calls}")
        if orphaned_outputs:
            logger.info(f"Removing {len(orphaned_outputs)} orphaned outputs: {orphaned_outputs}")
        if orphaned_requests:
            logger.info(f"Removing {len(orphaned_requests)} orphaned MCP requests: {orphaned_requests}")
        if orphaned_responses:
            logger.info(f"Removing {len(orphaned_responses)} orphaned MCP responses: {orphaned_responses}")

        # All paired types for quick lookup
        all_call_types = MessageFilter.CALL_ID_CALL_TYPES | MessageFilter.MCP_APPROVAL_REQUEST_TYPES
        all_output_types = MessageFilter.CALL_ID_OUTPUT_TYPES | MessageFilter.MCP_APPROVAL_RESPONSE_TYPES

        # Filter out orphaned messages, but keep original indexes so we can enforce
        # reasoning-item requirements after the fact.
        kept_entries: list[tuple[int, TResponseInputItem]] = []
        for idx, msg in enumerate(messages):
            msg_type = msg.get("type")

            # Keep messages that are not paired types
            if msg_type not in all_call_types | all_output_types:
                kept_entries.append((idx, msg))
                continue

            # Pattern 1: call_id linked types
            if msg_type in MessageFilter.CALL_ID_CALL_TYPES:
                call_id = msg.get("call_id")
                if isinstance(call_id, str) and call_id in matched_call_ids:
                    kept_entries.append((idx, msg))
                else:
                    logger.debug(f"Removing orphaned {msg_type} with call_id={call_id}")
                continue

            if msg_type in MessageFilter.CALL_ID_OUTPUT_TYPES:
                # For outputs, check 'call_id' field
                call_id = msg.get("call_id")
                if isinstance(call_id, str) and call_id in matched_call_ids:
                    kept_entries.append((idx, msg))
                else:
                    logger.debug(f"Removing orphaned {msg_type} with call_id={call_id}")
                continue

            # Pattern 2: approval_request_id linked types
            if msg_type in MessageFilter.MCP_APPROVAL_REQUEST_TYPES:
                msg_id = msg.get("id")
                if isinstance(msg_id, str) and msg_id in matched_approval_ids:
                    kept_entries.append((idx, msg))
                else:
                    logger.debug(f"Removing orphaned {msg_type} with id={msg_id}")
                continue

            if msg_type in MessageFilter.MCP_APPROVAL_RESPONSE_TYPES:
                approval_id = msg.get("approval_request_id")
                if isinstance(approval_id, str) and approval_id in matched_approval_ids:
                    kept_entries.append((idx, msg))
                else:
                    logger.debug(f"Removing orphaned {msg_type} with approval_request_id={approval_id}")
                continue

        # Pattern 3: reasoning items must be followed by their original next item,
        # AND items following a reasoning must have that reasoning present.
        # First pass: identify which reasoning items to remove (missing follower)
        kept_index_set = {idx for idx, _ in kept_entries}
        removed_reasoning_indices: set[int] = set()

        for idx, msg in kept_entries:
            if msg.get("type") == "reasoning":
                required_idx = idx + 1
                if required_idx >= len(messages) or required_idx not in kept_index_set:
                    logger.info(
                        "Removing reasoning item %s because its required following item was dropped",
                        msg.get("id"),
                    )
                    removed_reasoning_indices.add(idx)

        # Second pass: build final list, removing:
        # 1. Reasoning items without their followers
        # 2. Items that immediately followed a removed reasoning item
        final_messages: list[TResponseInputItem] = []
        for idx, msg in kept_entries:
            # Skip removed reasoning items
            if idx in removed_reasoning_indices:
                continue
            # Skip items that were supposed to follow a removed reasoning
            prev_idx = idx - 1
            if prev_idx in removed_reasoning_indices:
                logger.info(
                    "Removing item %s (type=%s) because its required preceding reasoning was dropped",
                    msg.get("id"),
                    msg.get("type"),
                )
                continue
            final_messages.append(msg)

        return final_messages

    @staticmethod
    def remove_duplicates(messages: list[TResponseInputItem]) -> list[TResponseInputItem]:
        """Remove duplicate messages based on their 'id' field.

        When the same item is added multiple times (e.g., from 'added' and 'done' events),
        this keeps only the first occurrence.

        Note: Skips placeholder IDs (FAKE_RESPONSES_ID) from LiteLLM/Chat Completions
        models since multiple distinct items share that placeholder.

        Args:
            messages: List of message dictionaries

        Returns:
            list[TResponseInputItem]: Messages with duplicates removed
        """
        seen_ids: set[str] = set()
        result: list[TResponseInputItem] = []

        for msg in messages:
            msg_id = msg.get("id")
            # Skip placeholder IDs - multiple distinct items share it
            if isinstance(msg_id, str) and msg_id and msg_id != FAKE_RESPONSES_ID:
                if msg_id in seen_ids:
                    logger.debug(f"Removing duplicate message with id={msg_id}")
                    continue
                seen_ids.add(msg_id)
            result.append(msg)

        return result
