import sqlite3
import threading

from openai.types.beta.threads.runs.run_step import Usage

from agency_swarm.util.tracking.abstract_tracker import AbstractTracker


class SQLiteUsageTracker(AbstractTracker):
    def __init__(self, db_path: str = "token_usage.db"):
        """
        Initializes a SQLite-based usage tracker.

        Args:
            db_path (str): Path to the SQLite database file.
        """
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.lock = threading.Lock()
        self._create_table()
        self._closed = False

    def _create_table(self) -> None:
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS token_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    total_tokens INTEGER,
                    assistant_id TEXT,
                    thread_id TEXT,
                    model TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

    def track_usage(
        self, usage: Usage, assistant_id: str, thread_id: str, model: str
    ) -> None:
        with self.lock:
            if self._closed:
                raise RuntimeError("Attempting to track usage on a closed tracker.")
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO token_usage (prompt_tokens, completion_tokens, total_tokens, assistant_id, thread_id, model)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        usage.prompt_tokens,
                        usage.completion_tokens,
                        usage.total_tokens,
                        assistant_id,
                        thread_id,
                        model,
                    ),
                )

    def get_total_tokens(self) -> Usage:
        with self.lock:
            if self._closed:
                return Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens)
                FROM token_usage
                """
            )
            prompt, completion, total = cursor.fetchone()
            return Usage(
                prompt_tokens=prompt or 0,
                completion_tokens=completion or 0,
                total_tokens=total or 0,
            )

    def close(self) -> None:
        with self.lock:
            if not self._closed:
                self.conn.close()
                self._closed = True

    @classmethod
    def get_observe_decorator(cls):
        # Return a no-op decorator.
        return lambda f: f
