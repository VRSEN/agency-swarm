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
    # Define table columns as a class variable for a single source of truth
    TABLE_COLUMNS = {
        "id": "TEXT PRIMARY KEY",
        "parent_run_id": "TEXT",
        "start_time": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "end_time": "TIMESTAMP",
        "type": "TEXT",
        "inputs": "TEXT",
        "outputs": "TEXT",
        "error": "TEXT",
        "serialized": "TEXT",
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

    def _execute(self, sql: str, params: tuple) -> None:
        """Execute a single SQL statement with given parameters."""
        try:
            with self.conn:
                self.conn.execute(sql, params)
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            raise

    def _upsert_event(self, run_id: UUID, **kwargs) -> None:
        """
        Insert or update an event by run_id.
        This handles any columns passed in via kwargs.
        """
        columns = ", ".join(kwargs.keys())
        placeholders = ", ".join("?" for _ in kwargs)
        update_stmt = ", ".join(f"{k} = excluded.{k}" for k in kwargs.keys())

        sql = f"""
            INSERT INTO events (id, {columns})
            VALUES (?, {placeholders})
            ON CONFLICT(id) DO UPDATE SET
            {update_stmt}
            WHERE id = excluded.id
        """
        params = (str(run_id), *kwargs.values())
        self._execute(sql, params)

    def _update_event(
        self,
        run_id: UUID,
        set_end_time: bool = False,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ) -> None:
        """
        Update an existing event row.
        Optionally set end_time = CURRENT_TIMESTAMP and/or parent_run_id.
        """
        set_clauses = []
        values = []

        if set_end_time:
            set_clauses.append("end_time = CURRENT_TIMESTAMP")

        if parent_run_id is not None:
            set_clauses.append("parent_run_id = ?")
            values.append(str(parent_run_id))

        for k, v in kwargs.items():
            set_clauses.append(f"{k} = ?")
            values.append(v)

        set_expr = ", ".join(set_clauses)
        sql = f"UPDATE events SET {set_expr} WHERE id = ?"
        values.append(str(run_id))

        self._execute(sql, tuple(values))

    def _count_tokens(self, text: str, model: str = DEFAULT_MODEL) -> int:
        """Count tokens in a given text for a particular model."""
        try:
            encoding = tiktoken.encoding_for_model(model)
            return len(encoding.encode(text))
        except Exception as e:
            logger.error(f"Error counting tokens: {e}")
            return 0

    def _count_message_tokens(
        self, messages: List[Dict], model: str = DEFAULT_MODEL
    ) -> int:
        """Count tokens in a list of message dictionaries."""
        try:
            encoding = tiktoken.encoding_for_model(model)
            total_tokens = 0
            for msg in messages:
                content = msg.get("content", "")
                if content:
                    total_tokens += len(encoding.encode(str(content)))
            return total_tokens
        except Exception as e:
            logger.error(f"Error counting message tokens: {e}")
            return 0

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
        self._upsert_event(
            run_id,
            type="chain_start",
            serialized=json.dumps(serialized) if serialized else None,
            inputs=json.dumps(inputs),
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            tags=json.dumps(tags) if tags else None,
            metadata=json.dumps(metadata) if metadata else None,
        )

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        response_text = outputs.get("response", "")
        completion_tokens = self._count_tokens(response_text)

        self._update_event(
            run_id,
            set_end_time=True,
            parent_run_id=parent_run_id,
            outputs=json.dumps(outputs),
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
        self._update_event(
            run_id,
            set_end_time=True,
            parent_run_id=parent_run_id,
            error=str(error),
            tags=json.dumps(tags) if tags else None,
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

        self._upsert_event(
            run_id,
            type="llm_start",
            serialized=json.dumps(serialized) if serialized else None,
            prompts=json.dumps(prompts),
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            tags=json.dumps(tags) if tags else None,
            metadata=json.dumps(metadata) if metadata else None,
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
        """Note: Tracking streaming for chat completions is not yet supported."""
        logger.debug(
            f"New token received: {token}, run_id: {run_id}, parent_run_id: {parent_run_id}"
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

        self._update_event(
            run_id,
            set_end_time=True,
            parent_run_id=parent_run_id,
            outputs=json.dumps(response.model_dump()),
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
        self._update_event(
            run_id,
            set_end_time=True,
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
        msg_data = [[m.dict() for m in turn] for turn in messages]
        model = kwargs.get("invocation_params", {}).get("model", DEFAULT_MODEL)
        prompt_tokens = sum(
            self._count_message_tokens(turn, model) for turn in msg_data
        )
        completion_tokens = 0

        self._upsert_event(
            run_id,
            type="chat_model_start",
            inputs=json.dumps(msg_data),
            serialized=json.dumps(serialized) if serialized else None,
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            tags=json.dumps(tags) if tags else None,
            metadata=json.dumps(metadata) if metadata else None,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
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
        self._upsert_event(
            run_id,
            type="tool_start",
            serialized=json.dumps(serialized) if serialized else None,
            inputs=input_str,
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            tags=json.dumps(tags) if tags else None,
            metadata=json.dumps(metadata) if metadata else None,
        )

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self._update_event(
            run_id, set_end_time=True, parent_run_id=parent_run_id, outputs=output
        )

    def on_tool_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self._update_event(
            run_id, set_end_time=True, parent_run_id=parent_run_id, error=str(error)
        )

    def on_agent_action(
        self,
        action: AgentAction,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self._upsert_event(
            run_id,
            type="agent_action",
            serialized=json.dumps(
                {"tool": action.tool, "tool_input": action.tool_input}
            ),
            parent_run_id=str(parent_run_id) if parent_run_id else None,
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
        response_text = finish.return_values.get("response", "")
        completion_tokens = self._count_tokens(response_text)

        self._update_event(
            run_id,
            set_end_time=True,
            parent_run_id=parent_run_id,
            outputs=json.dumps(finish.return_values),
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
        self._upsert_event(
            run_id,
            type="retriever_start",
            serialized=json.dumps(serialized) if serialized else None,
            file_search_query=query,
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            tags=json.dumps(tags) if tags else None,
            metadata=json.dumps(metadata) if metadata else None,
        )

    def on_retriever_end(
        self,
        documents: Sequence[Document],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        docs_json = json.dumps([doc.model_dump() for doc in documents])
        self._update_event(
            run_id, set_end_time=True, parent_run_id=parent_run_id, documents=docs_json
        )

    def on_retriever_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self._update_event(
            run_id, set_end_time=True, parent_run_id=parent_run_id, error=str(error)
        )

    def __del__(self):
        with self.lock:
            if not self._closed:
                self.conn.close()
                self._closed = True
