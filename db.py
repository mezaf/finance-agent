"""
db.py — SQLite + sqlite-vec storage layer.

Alpha version: plain, unencrypted SQLite file. See project notes for the
decision history (SQLCipher was tested and found incompatible with
sqlite-vec on the same connection; Postgres + pgvector is the candidate
path later if encryption/role separation becomes a hard requirement).
"""

import sqlite3
import sqlite_vec

DB_PATH = "finance.db"
EMBEDDING_DIM = 384  # matches all-MiniLM-L6-v2; change if you swap embedding models


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Open a connection with sqlite-vec loaded and ready to use."""
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they don't already exist. Safe to call every run."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT NOT NULL,
            bank            TEXT NOT NULL,
            account_type    TEXT NOT NULL,      -- 'account' or 'tdc'
            card_network    TEXT,               -- 'visa' / 'master' / NULL
            description     TEXT NOT NULL,
            amount          REAL NOT NULL,
            currency        TEXT NOT NULL,
            installment     TEXT,               -- e.g. '07/18', NULL if not applicable
            bucket          TEXT NOT NULL,       -- 'savings' | 'spend' | 'leisure'
            source_file_id  TEXT NOT NULL,       -- Drive fileId, for traceability
            created_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS transaction_vectors USING vec0(
            id INTEGER PRIMARY KEY,
            embedding FLOAT[{EMBEDDING_DIM}]
        )
    """)

    # Tracks which files have already been processed, to avoid double-ingestion
    conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_files (
            file_id      TEXT PRIMARY KEY,
            file_name    TEXT NOT NULL,
            processed_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Failed runs land here instead of failing silently
    conn.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name   TEXT,
            step        TEXT,          -- e.g. 'extraction', 'categorization', 'drive_move'
            message     TEXT,
            occurred_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()


def is_file_processed(conn: sqlite3.Connection, file_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM processed_files WHERE file_id = ?", (file_id,)
    ).fetchone()
    return row is not None


def mark_file_processed(conn: sqlite3.Connection, file_id: str, file_name: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO processed_files (file_id, file_name) VALUES (?, ?)",
        (file_id, file_name),
    )
    conn.commit()


def log_error(conn: sqlite3.Connection, file_name: str, step: str, message: str) -> None:
    conn.execute(
        "INSERT INTO errors (file_name, step, message) VALUES (?, ?, ?)",
        (file_name, step, message),
    )
    conn.commit()


def insert_transaction(conn: sqlite3.Connection, txn: dict, embedding: list[float]) -> int:
    """
    txn expects keys: date, bank, account_type, card_network, description,
    amount, currency, installment, bucket, source_file_id
    """
    cur = conn.execute(
        """
        INSERT INTO transactions
            (date, bank, account_type, card_network, description,
             amount, currency, installment, bucket, source_file_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            txn["date"], txn["bank"], txn["account_type"], txn.get("card_network"),
            txn["description"], txn["amount"], txn["currency"],
            txn.get("installment"), txn["bucket"], txn["source_file_id"],
        ),
    )
    txn_id = cur.lastrowid

    conn.execute(
        "INSERT INTO transaction_vectors (id, embedding) VALUES (?, ?)",
        (txn_id, sqlite_vec.serialize_float32(embedding)),
    )
    conn.commit()
    return txn_id


# ---------- Queries: exact aggregation (SQL side) ----------

def totals_by_bucket(conn: sqlite3.Connection, start_date: str, end_date: str) -> list[sqlite3.Row]:
    """20/70/10 breakdown for a date range. Dates as 'YYYY-MM-DD'."""
    return conn.execute(
        """
        SELECT bucket, SUM(amount) AS total, COUNT(*) AS txn_count
        FROM transactions
        WHERE date BETWEEN ? AND ?
        GROUP BY bucket
        """,
        (start_date, end_date),
    ).fetchall()


def totals_by_bank(conn: sqlite3.Connection, start_date: str, end_date: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT bank, account_type, SUM(amount) AS total, COUNT(*) AS txn_count
        FROM transactions
        WHERE date BETWEEN ? AND ?
        GROUP BY bank, account_type
        """,
        (start_date, end_date),
    ).fetchall()


# ---------- Queries: semantic search (vector side) ----------

def semantic_search(conn: sqlite3.Connection, query_embedding: list[float], limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT t.id, t.date, t.bank, t.description, t.amount, t.bucket, v.distance
        FROM transaction_vectors v
        JOIN transactions t ON t.id = v.id
        WHERE v.embedding MATCH ?
        ORDER BY v.distance
        LIMIT ?
        """,
        (sqlite_vec.serialize_float32(query_embedding), limit),
    ).fetchall()