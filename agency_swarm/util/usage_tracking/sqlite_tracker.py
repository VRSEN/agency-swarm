import sqlite3
import threading

from openai.types.beta.threads.runs.run_step import Usage

from agency_swarm.util.usage_tracking.abstract_tracker import AbstractTracker


class SQLiteUsageTracker(AbstractTracker):
    def __init__(self, db_path: str = "token_usage.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.lock = threading.Lock()
        self._create_table()

    def _create_table(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS token_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    total_tokens INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def track_usage(self, usage: Usage) -> None:
        with self.lock:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO token_usage (prompt_tokens, completion_tokens, total_tokens)
                    VALUES (?, ?, ?)
                """,
                    (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens),
                )

    def get_total_tokens(self) -> Usage:
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens)
                FROM token_usage
            """)
            prompt, completion, total = cursor.fetchone()
            return Usage(
                prompt_tokens=prompt or 0,
                completion_tokens=completion or 0,
                total_tokens=total or 0,
            )
