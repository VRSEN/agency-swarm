import json
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Sequence, Union
from uuid import UUID

from langchain.schema import AgentAction, AgentFinish, BaseMessage, Document, LLMResult

from agency_swarm.util.tracking.callbacks import CallbackHandler


class LocalCallbackHandler(CallbackHandler):
    def __init__(self, db_path: str = "usage.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.lock = threading.Lock()
        self._create_tables()
        self._closed = False

    def _create_tables(self):
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    type TEXT,
                    serialized TEXT,
                    inputs TEXT,
                    outputs TEXT,
                    error TEXT,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    parent_run_id TEXT,
                    tags TEXT,
                    metadata TEXT,
                    prompts TEXT,
                    input_str TEXT,
                    file_search_query TEXT,
                    documents TEXT
                )
                """
            )

    def _save_run(self, run_id: UUID, **kwargs):
        with self.conn:
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
            self.conn.execute(sql, (str(run_id), *kwargs.values()))

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
        self._save_run(
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
        with self.conn:
            self.conn.execute(
                """
                UPDATE events
                SET outputs = ?, end_time = CURRENT_TIMESTAMP, parent_run_id = ?
                WHERE id = ?
                """,
                (
                    json.dumps(outputs),
                    str(parent_run_id) if parent_run_id else None,
                    str(run_id),
                ),
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
        with self.conn:
            self.conn.execute(
                """
                UPDATE events
                SET error = ?, end_time = CURRENT_TIMESTAMP, parent_run_id = ?, tags=?
                WHERE id = ?
                """,
                (
                    str(error),
                    str(parent_run_id) if parent_run_id else None,
                    json.dumps(tags) if tags else None,
                    str(run_id),
                ),
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
        self._save_run(
            run_id,
            type="llm_start",
            serialized=json.dumps(serialized) if serialized else None,
            prompts=json.dumps(prompts),
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            tags=json.dumps(tags) if tags else None,
            metadata=json.dumps(metadata) if metadata else None,
        )

    def on_llm_new_token(
        self,
        token: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any: ...

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        with self.conn:
            self.conn.execute(
                """
                UPDATE events
                SET outputs = ?, end_time = CURRENT_TIMESTAMP, parent_run_id = ?
                WHERE id = ?
                """,
                (
                    json.dumps(response.dict()),
                    str(parent_run_id) if parent_run_id else None,
                    str(run_id),
                ),
            )

    def on_llm_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        with self.conn:
            self.conn.execute(
                """
                UPDATE events
                SET error = ?, end_time = CURRENT_TIMESTAMP, parent_run_id = ?
                WHERE id = ?
                """,
                (
                    str(error),
                    str(parent_run_id) if parent_run_id else None,
                    str(run_id),
                ),
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
        # Convert messages to string for storage
        msg_data = [[m.dict() for m in turn] for turn in messages]
        self._save_run(
            run_id,
            type="chat_model_start",
            serialized=json.dumps(serialized) if serialized else None,
            inputs=json.dumps(msg_data),
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            tags=json.dumps(tags) if tags else None,
            metadata=json.dumps(metadata) if metadata else None,
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
        self._save_run(
            run_id,
            type="tool_start",
            serialized=json.dumps(serialized) if serialized else None,
            input_str=input_str,
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
        with self.conn:
            self.conn.execute(
                """
                UPDATE events
                SET outputs = ?, end_time = CURRENT_TIMESTAMP, parent_run_id = ?
                WHERE id = ?
                """,
                (output, str(parent_run_id) if parent_run_id else None, str(run_id)),
            )

    def on_tool_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        with self.conn:
            self.conn.execute(
                """
                UPDATE events
                SET error = ?, end_time = CURRENT_TIMESTAMP, parent_run_id = ?
                WHERE id = ?
                """,
                (
                    str(error),
                    str(parent_run_id) if parent_run_id else None,
                    str(run_id),
                ),
            )

    def on_agent_action(
        self,
        action: AgentAction,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Run on agent action."""
        self._save_run(
            run_id,
            type="agent_action",
            serialized=json.dumps(
                {"tool": action.tool, "tool_input": action.tool_input}
            ),
            parent_run_id=str(parent_run_id) if parent_run_id else None,
        )

    def on_agent_finish(
        self,
        finish: AgentFinish,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        with self.conn:
            self.conn.execute(
                """
                UPDATE events
                SET outputs = ?, end_time = CURRENT_TIMESTAMP, parent_run_id = ?
                WHERE id = ?
                """,
                (
                    json.dumps(finish.return_values),
                    str(parent_run_id) if parent_run_id else None,
                    str(run_id),
                ),
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
        self._save_run(
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
        with self.conn:
            self.conn.execute(
                """
                UPDATE events
                SET documents = ?, end_time = CURRENT_TIMESTAMP, parent_run_id = ?
                WHERE id = ?
                """,
                (
                    json.dumps([doc.dict() for doc in documents]),
                    str(parent_run_id) if parent_run_id else None,
                    str(run_id),
                ),
            )

    def on_retriever_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Run when Retriever errors."""
        with self.conn:
            self.conn.execute(
                """
                UPDATE events
                SET error = ?, end_time = CURRENT_TIMESTAMP, parent_run_id = ?
                WHERE id = ?
                """,
                (
                    str(error),
                    str(parent_run_id) if parent_run_id else None,
                    str(run_id),
                ),
            )

    def __del__(self):
        with self.lock:
            if not self._closed:
                self.conn.close()
                self._closed = True
