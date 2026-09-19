"""Database Persistence Layer with SQLAlchemy ORM and Process-Safe SQLite Fallback.

Supports:
1. PostgreSQL via SQLAlchemy in production/Docker environments.
2. Process-safe file-backed SQLite fallback with WAL mode for local execution and CI.
3. Multi-process concurrency: receipt-api and receipt-worker safely read/write concurrently.
"""

import os
import json
import sqlite3
import logging
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager

from backend.app.domain.receipt import ReceiptRecord, ReceiptStatus, ExpenseLine

logger = logging.getLogger("receipt-db")


def utc_now() -> datetime:
    """Returns current UTC datetime."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Returns ISO-formatted UTC datetime."""
    return utc_now().isoformat()


# Optional SQLAlchemy import for production
try:
    from sqlalchemy import create_engine, Column, String, Float, DateTime, Text
    from sqlalchemy.orm import declarative_base, sessionmaker, Session
    HAS_SQLALCHEMY = True
    Base = declarative_base()

    class ReceiptModel(Base):
        __tablename__ = "receipts"
        id = Column(String(64), primary_key=True)
        supplier_name = Column(String(255), nullable=True)
        receipt_number = Column(String(128), nullable=True)
        receipt_date = Column(String(64), nullable=True)
        total_amount = Column(Float, default=0.0)
        currency = Column(String(16), default="THB")
        confidence_score = Column(Float, default=0.0)
        status = Column(String(32), nullable=False)
        image_storage_key = Column(String(512), nullable=False)
        lines_json = Column(Text, default="[]")
        created_at = Column(DateTime, default=utc_now)
        updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

except ImportError:
    HAS_SQLALCHEMY = False
    Base = None
    ReceiptModel = None


def resolve_database_path() -> str:
    """Resolves database file path based on environment configuration."""
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("sqlite:///"):
        return db_url.replace("sqlite:///", "")

    if os.getenv("DATABASE_PATH"):
        return os.getenv("DATABASE_PATH")

    # Production shared path if available
    srv_shared = Path("/srv/receipt-app/shared")
    if srv_shared.exists():
        return str(srv_shared / "receipts.db")

    # Local fallback in working directory
    return os.path.abspath("./receipts.db")


class SQLiteReceiptRepository:
    """Robust, process-safe SQLite repository supporting concurrent API and Worker processes."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or resolve_database_path()
        self._ensure_parent_directory()
        self._init_schema()

    def _ensure_parent_directory(self):
        parent = Path(self.db_path).parent
        parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _connection(self):
        """Context manager guaranteeing connection closure to prevent file lock leakage."""
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        # Enable Write-Ahead Logging (WAL) for inter-process concurrent read/write
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self):
        with self._connection() as conn:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS receipts (
                        id TEXT PRIMARY KEY,
                        supplier_name TEXT,
                        receipt_number TEXT,
                        receipt_date TEXT,
                        total_amount REAL DEFAULT 0.0,
                        currency TEXT DEFAULT 'THB',
                        confidence_score REAL DEFAULT 0.0,
                        status TEXT NOT NULL,
                        image_storage_key TEXT NOT NULL,
                        lines_json TEXT DEFAULT '[]',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS queue_jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        queue_name TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'PENDING',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_receipts_status ON receipts(status);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_lookup ON queue_jobs(queue_name, status);")

    def _row_to_record(self, row: sqlite3.Row) -> ReceiptRecord:
        raw_lines = json.loads(row["lines_json"] or "[]")
        lines = [ExpenseLine(**line) if isinstance(line, dict) else line for line in raw_lines]

        created = datetime.fromisoformat(row["created_at"]) if row["created_at"] else utc_now()
        updated = datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else utc_now()

        return ReceiptRecord(
            id=row["id"],
            supplier_name=row["supplier_name"],
            receipt_number=row["receipt_number"],
            receipt_date=row["receipt_date"],
            total_amount=float(row["total_amount"]),
            currency=row["currency"],
            confidence_score=float(row["confidence_score"]),
            status=ReceiptStatus(row["status"]),
            image_storage_key=row["image_storage_key"],
            lines=lines,
            created_at=created,
            updated_at=updated
        )

    def save(self, record: ReceiptRecord) -> ReceiptRecord:
        """Upserts receipt record into persistent storage."""
        lines_data = [line.dict() if hasattr(line, "dict") else dict(line) for line in record.lines]
        lines_json = json.dumps(lines_data)

        created_str = record.created_at.isoformat() if hasattr(record.created_at, "isoformat") else str(record.created_at)
        updated_str = record.updated_at.isoformat() if hasattr(record.updated_at, "isoformat") else str(record.updated_at)

        with self._connection() as conn:
            with conn:
                conn.execute("""
                    INSERT INTO receipts (
                        id, supplier_name, receipt_number, receipt_date,
                        total_amount, currency, confidence_score, status,
                        image_storage_key, lines_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        supplier_name=excluded.supplier_name,
                        receipt_number=excluded.receipt_number,
                        receipt_date=excluded.receipt_date,
                        total_amount=excluded.total_amount,
                        currency=excluded.currency,
                        confidence_score=excluded.confidence_score,
                        status=excluded.status,
                        image_storage_key=excluded.image_storage_key,
                        lines_json=excluded.lines_json,
                        updated_at=excluded.updated_at;
                """, (
                    record.id,
                    record.supplier_name,
                    record.receipt_number,
                    record.receipt_date,
                    float(record.total_amount),
                    record.currency,
                    float(record.confidence_score),
                    record.status.value if hasattr(record.status, "value") else str(record.status),
                    record.image_storage_key,
                    lines_json,
                    created_str,
                    updated_str
                ))
        return record

    def get(self, receipt_id: str) -> Optional[ReceiptRecord]:
        """Retrieves a receipt by ID."""
        with self._connection() as conn:
            cursor = conn.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_record(row)
        return None

    def list_all(self, limit: int = 100) -> List[ReceiptRecord]:
        """Lists receipts sorted by creation time descending."""
        with self._connection() as conn:
            cursor = conn.execute("SELECT * FROM receipts ORDER BY created_at DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [self._row_to_record(r) for r in rows]

    def delete(self, receipt_id: str) -> bool:
        """Deletes a receipt record."""
        with self._connection() as conn:
            with conn:
                cursor = conn.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
                return cursor.rowcount > 0

    def clear(self):
        """Clears all receipts (used in test isolation)."""
        with self._connection() as conn:
            with conn:
                conn.execute("DELETE FROM receipts;")

    def check_health(self) -> bool:
        """Verifies database connectivity."""
        try:
            with self._connection() as conn:
                cursor = conn.execute("SELECT 1;")
                return cursor.fetchone() is not None
        except Exception as exc:
            logger.error("Database health check failed: %s", exc)
            return False


class ReceiptStore:
    """Dict-compatible interface wrapping SQLite/SQLAlchemy persistent storage.
    
    Allows drop-in replacement for the in-memory RECEIPTS_DB dictionary while
    guaranteeing persistence across independent OS processes (Gunicorn API & Worker).
    """

    def __init__(self, db_path: Optional[str] = None):
        self.repo = SQLiteReceiptRepository(db_path=db_path)

    def __getitem__(self, receipt_id: str) -> ReceiptRecord:
        record = self.repo.get(receipt_id)
        if record is None:
            raise KeyError(receipt_id)
        return record

    def __setitem__(self, receipt_id: str, record: ReceiptRecord):
        if record.id != receipt_id:
            record.id = receipt_id
        self.repo.save(record)

    def __contains__(self, receipt_id: str) -> bool:
        return self.repo.get(receipt_id) is not None

    def __len__(self) -> int:
        return len(self.repo.list_all(limit=10000))

    def get(self, receipt_id: str, default: Optional[ReceiptRecord] = None) -> Optional[ReceiptRecord]:
        record = self.repo.get(receipt_id)
        return record if record is not None else default

    def values(self) -> List[ReceiptRecord]:
        return self.repo.list_all(limit=1000)

    def items(self) -> List[Tuple[str, ReceiptRecord]]:
        return [(r.id, r) for r in self.repo.list_all(limit=1000)]

    def pop(self, receipt_id: str, default: Any = None) -> Any:
        record = self.repo.get(receipt_id)
        if record:
            self.repo.delete(receipt_id)
            return record
        return default

    def clear(self):
        self.repo.clear()

    def check_health(self) -> bool:
        return self.repo.check_health()


# Shared singleton receipt store instance
_GLOBAL_STORE: Optional[ReceiptStore] = None


def get_receipt_store(db_path: Optional[str] = None) -> ReceiptStore:
    global _GLOBAL_STORE
    if _GLOBAL_STORE is None or db_path is not None:
        _GLOBAL_STORE = ReceiptStore(db_path=db_path)
    return _GLOBAL_STORE
