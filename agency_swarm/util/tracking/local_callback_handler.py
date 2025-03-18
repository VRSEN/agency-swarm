import json
import logging
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Sequence, Union
from uuid import UUID

import tiktoken
from langchain.schema import AgentAction, AgentFinish, BaseMessage, Document, LLMResult

from agency_swarm.constants import DEFAULT_MODEL

logger = logging.getLogger(__name__)


class LocalCallbackHandler:
    """
    A local callback handler that logs every event into a single 'events' table,
    creating a new row for each callback. This table can later be queried or exported
    for analysis of usage, latencies, error rates, etc.
    """

    TABLE_COLUMNS = {
        "event_id": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "run_id": "TEXT",
        "parent_run_id": "TEXT",
        "event_time": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "callback_type": "TEXT",
        "serialized": "TEXT",
        "inputs": "TEXT",
        "outputs": "TEXT",
        "error": "TEXT",
        "metadata": "TEXT",
        "prompts": "TEXT",
        "file_search_query": "TEXT",
        "documents": "TEXT",
        "prompt_tokens": "INTEGER",
        "completion_tokens": "INTEGER",
        "tags": "TEXT",
    }

    def __init__(self, db_path: str = "usage.db"):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._closed = False
        self._connect()

    def _connect(self) -> None:
        """Connect to database and create tables if needed."""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._create_tables()
        except sqlite3.Error as e:
            logger.error(f"Database error during connect: {e}")
            raise

    def _create_tables(self) -> None:
        """Create 'events' table if it does not exist."""
        columns_sql = ", ".join(
            f"{col} {type_}" for col, type_ in self.TABLE_COLUMNS.items()
        )
        with self.conn:
            self.conn.execute(f"""
                CREATE TABLE IF NOT EXISTS events (
                    {columns_sql}
                )
            """)

    def _insert_event(
        self,
        callback_type: str,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        serialized: Optional[dict] = None,
        inputs: Optional[Any] = None,
        outputs: Optional[Any] = None,
        error: Optional[str] = None,
        metadata: Optional[dict] = None,
        prompts: Optional[List[str]] = None,
        file_search_query: Optional[str] = None,
        documents: Optional[Any] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """
        Insert a new event row for the given callback. Each event is logged separately.
        """
        sql = """
            INSERT INTO events (
                run_id, parent_run_id, callback_type,
                serialized, inputs, outputs, error, metadata, prompts,
                file_search_query, documents, prompt_tokens, completion_tokens, tags
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        def _json_dumps(value):
            if isinstance(value, str):
                return value
            return json.dumps(value) if value is not None else None

        params = (
            str(run_id),
            str(parent_run_id) if parent_run_id else None,
            callback_type,
            _json_dumps(serialized),
            _json_dumps(inputs),
            _json_dumps(outputs),
            error,
            _json_dumps(metadata),
            _json_dumps(prompts),
            file_search_query,
            _json_dumps(documents),
            prompt_tokens,
            completion_tokens,
            _json_dumps(tags),
        )

        try:
            with self.conn:
                self.conn.execute(sql, params)
        except sqlite3.Error as e:
            logger.error(f"Database error inserting event: {e}")
            raise

    def _count_tokens(self, text: str, model: str = DEFAULT_MODEL) -> int:
        """Count tokens in a given text for a particular model."""
        if not text:
            return 0
        try:
            encoding = tiktoken.encoding_for_model(model)
            return len(encoding.encode(text))
        except Exception as e:
            logger.error(f"Error counting tokens: {e}")
            return 0

    def _count_message_tokens(
        self, messages: List[Dict[str, Any]], model: str = DEFAULT_MODEL
    ) -> int:
        """Count tokens in a list of message dicts (e.g. role/content pairs)."""
        total_tokens = 0
        try:
            encoding = tiktoken.encoding_for_model(model)
            for msg in messages:
                content = msg.get("content", "")
                if content:
                    total_tokens += len(encoding.encode(str(content)))
        except Exception as e:
            logger.error(f"Error counting message tokens: {e}")
        return total_tokens

    #
    # Public Callback Methods
    #

    def on_chain_start(
        self,
        serialized: Optional[Dict[str, Any]],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        self._insert_event(
            callback_type="chain_start",
            run_id=run_id,
            parent_run_id=parent_run_id,
            serialized=serialized,
            inputs=inputs,
            tags=tags,
            metadata=metadata,
        )

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        # Attempt to count tokens in "response" if present
        response_text = outputs.get("response", "")
        completion_tokens = self._count_tokens(response_text)

        self._insert_event(
            callback_type="chain_end",
            run_id=run_id,
            parent_run_id=parent_run_id,
            outputs=outputs,
            completion_tokens=completion_tokens,
        )

    def on_chain_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        self._insert_event(
            callback_type="chain_error",
            run_id=run_id,
            parent_run_id=parent_run_id,
            error=str(error),
            tags=tags,
        )

    def on_llm_start(
        self,
        serialized: Optional[Dict[str, Any]],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        model = kwargs.get("invocation_params", {}).get("model", DEFAULT_MODEL)
        prompt_tokens = sum(self._count_tokens(p, model) for p in prompts)

        self._insert_event(
            callback_type="llm_start",
            run_id=run_id,
            parent_run_id=parent_run_id,
            serialized=serialized,
            prompts=prompts,
            tags=tags,
            metadata=metadata,
            prompt_tokens=prompt_tokens,
        )

    def on_llm_new_token(
        self,
        token: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """
        This method could also do an insert if you want to track each streamed token.
        But that can result in a large volume of data. By default, we'll just log a debug msg.
        """
        logger.debug(
            f"[streaming] new token: {token}, run_id: {run_id}, parent_run_id: {parent_run_id}"
        )

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        completion_tokens = 0
        model = kwargs.get("model", DEFAULT_MODEL)
        for generation in response.generations:
            for g in generation:
                completion_tokens += self._count_tokens(g.text, model=model)

        self._insert_event(
            callback_type="llm_end",
            run_id=run_id,
            parent_run_id=parent_run_id,
            outputs=response.model_dump(),
            completion_tokens=completion_tokens,
        )

    def on_llm_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self._insert_event(
            callback_type="llm_error",
            run_id=run_id,
            parent_run_id=parent_run_id,
            error=str(error),
        )

    def on_chat_model_start(
        self,
        serialized: Optional[Dict[str, Any]],
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        # Flatten messages into dicts for token counting
        msg_data = [[m.model_dump() for m in turn] for turn in messages]
        model = kwargs.get("invocation_params", {}).get("model", DEFAULT_MODEL)
        prompt_tokens = sum(
            self._count_message_tokens(turn, model) for turn in msg_data
        )

        self._insert_event(
            callback_type="chat_model_start",
            run_id=run_id,
            parent_run_id=parent_run_id,
            serialized=serialized,
            inputs=msg_data,
            tags=tags,
            metadata=metadata,
            prompt_tokens=prompt_tokens,
        )

    def on_tool_start(
        self,
        serialized: Optional[Dict[str, Any]],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        prompt_tokens = self._count_tokens(str(input_str))
        self._insert_event(
            callback_type="tool_start",
            run_id=run_id,
            parent_run_id=parent_run_id,
            serialized=serialized,
            inputs=input_str,
            tags=tags,
            metadata=metadata,
            prompt_tokens=prompt_tokens,
        )

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        completion_tokens = self._count_tokens(str(output))
        self._insert_event(
            callback_type="tool_end",
            run_id=run_id,
            parent_run_id=parent_run_id,
            outputs=output,
            completion_tokens=completion_tokens,
        )

    def on_tool_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        error_str = str(error)
        completion_tokens = self._count_tokens(error_str)
        self._insert_event(
            callback_type="tool_error",
            run_id=run_id,
            parent_run_id=parent_run_id,
            error=error_str,
            completion_tokens=completion_tokens,
        )

    def on_agent_action(
        self,
        action: AgentAction,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        data = {
            "tool": action.tool,
            "tool_input": action.tool_input,
        }
        self._insert_event(
            callback_type="agent_action",
            run_id=run_id,
            parent_run_id=parent_run_id,
            serialized=data,
            completion_tokens=0,
        )

    def on_agent_finish(
        self,
        finish: AgentFinish,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        # If "response" is the main textual result
        response_text = finish.return_values.get("response", "")
        completion_tokens = self._count_tokens(response_text)

        self._insert_event(
            callback_type="agent_finish",
            run_id=run_id,
            parent_run_id=parent_run_id,
            outputs=finish.return_values,
            completion_tokens=completion_tokens,
        )

    def on_retriever_start(
        self,
        serialized: Optional[Dict[str, Any]],
        query: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        self._insert_event(
            callback_type="retriever_start",
            run_id=run_id,
            parent_run_id=parent_run_id,
            serialized=serialized,
            file_search_query=query,
            tags=tags,
            metadata=metadata,
        )

    def on_retriever_end(
        self,
        documents: Sequence[Document],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        docs_json = [doc.model_dump() for doc in documents]

        self._insert_event(
            callback_type="retriever_end",
            run_id=run_id,
            parent_run_id=parent_run_id,
            documents=docs_json,
        )

    def on_retriever_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self._insert_event(
            callback_type="retriever_error",
            run_id=run_id,
            parent_run_id=parent_run_id,
            error=str(error),
        )

    def __del__(self):
        with self.lock:
            if not self._closed:
                self.conn.close()
                self._closed = True
