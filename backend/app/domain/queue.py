"""Inter-Process Queueing Layer with Redis Support and Persistent SQLite Fallback.

Allows receipt-api (Gunicorn) and receipt-worker (standalone process) to communicate
asynchronously across process and container boundaries.
"""

import os
import time
import sqlite3
import logging
from typing import Optional, List
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from backend.app.domain.db import resolve_database_path

logger = logging.getLogger("receipt-queue")

# Optional Redis import
try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class InterProcessQueue:
    """Inter-process FIFO queue supporting Redis and persistent SQLite fallback."""

    def __init__(self, queue_name: str = "receipt_ocr", redis_url: Optional[str] = None, db_path: Optional[str] = None):
        self.queue_name = queue_name
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self.db_path = db_path or resolve_database_path()
        self.redis_client = None

        if HAS_REDIS and self.redis_url and not self.redis_url.startswith("<SECRET_REF_"):
            try:
                client = redis.from_url(self.redis_url, socket_connect_timeout=2.0)
                client.ping()
                self.redis_client = client
                logger.info("Connected to Redis queue: %s", self.queue_name)
            except Exception as exc:
                logger.warning("Redis unavailable (%s), falling back to SQLite persistent queue.", exc)
                self.redis_client = None

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        try:
            yield conn
        finally:
            conn.close()

    def enqueue(self, payload: str) -> bool:
        """Pushes a payload (e.g., receipt_id) onto the queue."""
        if self.redis_client:
            try:
                self.redis_client.rpush(self.queue_name, payload)
                return True
            except Exception as exc:
                logger.warning("Redis enqueue failed (%s), falling back to SQLite.", exc)

        now = utc_now_iso()
        with self._connection() as conn:
            with conn:
                conn.execute("""
                    INSERT INTO queue_jobs (queue_name, payload, status, created_at, updated_at)
                    VALUES (?, ?, 'PENDING', ?, ?)
                """, (self.queue_name, payload, now, now))
        return True

    def dequeue(self, timeout: float = 0.0) -> Optional[str]:
        """Pops the oldest pending payload from the queue in an atomic transaction."""
        if self.redis_client:
            try:
                if timeout > 0:
                    res = self.redis_client.blpop([self.queue_name], timeout=int(timeout))
                    if res:
                        return res[1].decode("utf-8") if isinstance(res[1], bytes) else res[1]
                else:
                    item = self.redis_client.lpop(self.queue_name)
                    if item:
                        return item.decode("utf-8") if isinstance(item, bytes) else item
            except Exception as exc:
                logger.warning("Redis dequeue failed (%s), falling back to SQLite.", exc)

        # Atomic dequeue via SQLite transaction
        deadline = time.time() + timeout if timeout > 0 else 0
        while True:
            with self._connection() as conn:
                with conn:
                    cursor = conn.execute("""
                        SELECT id, payload FROM queue_jobs
                        WHERE queue_name = ? AND status = 'PENDING'
                        ORDER BY id ASC
                        LIMIT 1;
                    """, (self.queue_name,))
                    row = cursor.fetchone()
                    if row:
                        job_id = row["id"]
                        payload = row["payload"]
                        conn.execute("""
                            UPDATE queue_jobs
                            SET status = 'PROCESSING', updated_at = ?
                            WHERE id = ?;
                        """, (utc_now_iso(), job_id))
                        return payload

            if time.time() >= deadline:
                break
            time.sleep(0.05)

        return None

    def mark_completed(self, payload: str):
        """Marks a job as COMPLETED in SQLite queue."""
        with self._connection() as conn:
            with conn:
                conn.execute("""
                    UPDATE queue_jobs
                    SET status = 'COMPLETED', updated_at = ?
                    WHERE queue_name = ? AND payload = ? AND status = 'PROCESSING';
                """, (utc_now_iso(), self.queue_name, payload))

    def mark_failed(self, payload: str, error: str = "", can_retry: bool = False) -> int:
        """Marks job as failed or re-enqueues for retry. Returns current retry count."""
        now = utc_now_iso()
        with self._connection() as conn:
            with conn:
                cursor = conn.execute("""
                    SELECT id, retry_count FROM queue_jobs
                    WHERE queue_name = ? AND payload = ? AND status = 'PROCESSING'
                    ORDER BY id DESC LIMIT 1;
                """, (self.queue_name, payload))
                row = cursor.fetchone()
                if not row:
                    return 0
                job_id = row["id"]
                current_retries = (row["retry_count"] or 0) + 1
                new_status = "PENDING" if can_retry else "FAILED"
                conn.execute("""
                    UPDATE queue_jobs
                    SET status = ?, retry_count = ?, error_message = ?, updated_at = ?
                    WHERE id = ?;
                """, (new_status, current_retries, error, now, job_id))
                return current_retries

    def get_retry_count(self, payload: str) -> int:
        """Retrieves retry count for a given payload."""
        with self._connection() as conn:
            cursor = conn.execute("""
                SELECT retry_count FROM queue_jobs
                WHERE queue_name = ? AND payload = ?
                ORDER BY id DESC LIMIT 1;
            """, (self.queue_name, payload))
            row = cursor.fetchone()
            return (row["retry_count"] or 0) if row else 0

    def pending_count(self) -> int:
        """Returns the number of pending items in the queue."""
        if self.redis_client:
            try:
                return self.redis_client.llen(self.queue_name)
            except Exception:
                pass

        with self._connection() as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM queue_jobs
                WHERE queue_name = ? AND status = 'PENDING';
            """, (self.queue_name,))
            return cursor.fetchone()[0]

    def clear(self):
        """Clears all jobs in this queue (used in testing)."""
        if self.redis_client:
            try:
                self.redis_client.delete(self.queue_name)
            except Exception:
                pass

        with self._connection() as conn:
            with conn:
                conn.execute("DELETE FROM queue_jobs WHERE queue_name = ?;", (self.queue_name,))

    def check_health(self) -> bool:
        """Verifies queue broker connectivity."""
        if self.redis_client:
            try:
                return bool(self.redis_client.ping())
            except Exception:
                return False

        try:
            with self._connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM queue_jobs WHERE queue_name = ?;", (self.queue_name,))
                cursor.fetchone()
                return True
        except Exception as exc:
            logger.error("SQLite queue healthcheck failed: %s", exc)
            return False


# Global default queue instance
_GLOBAL_QUEUE: Optional[InterProcessQueue] = None


def get_receipt_queue(queue_name: str = "receipt_ocr") -> InterProcessQueue:
    global _GLOBAL_QUEUE
    if _GLOBAL_QUEUE is None or _GLOBAL_QUEUE.queue_name != queue_name:
        _GLOBAL_QUEUE = InterProcessQueue(queue_name=queue_name)
    return _GLOBAL_QUEUE
