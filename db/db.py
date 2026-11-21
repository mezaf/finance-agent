"""
db.py — Task 4: Database Write layer (SQLite + sqlite-vec).

Provides schema initialization and atomic database persistence for categorized
transactions, upcoming installments, and vector embeddings.
"""

import hashlib
import sqlite3
from contextlib import contextmanager

DB_PATH = "finance.db"
EMBEDDING_DIM = 384


def transaction_duplicate_key(txn: dict) -> str:
    """Natural key: close_date, date, exact description, and amount."""
    raw = "\x1f".join([
        str(txn.get("close_date") or ""),
        str(txn["date"]),
        str(txn["description"]),
        str(txn["amount"]),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Open a connection with sqlite-vec loaded."""
    conn = sqlite3.connect(db_path)
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except Exception:
        pass
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def fresh_connection(db_path: str = DB_PATH):
    """Guarantees a fresh connection per operation that is closed afterwards."""
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    """Create relational and vector tables if they don't already exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file_id        TEXT NOT NULL,
            file_name             TEXT NOT NULL,
            bank                  TEXT NOT NULL,
            account_type          TEXT NOT NULL,
            card_network          TEXT,
            close_date            TEXT,
            date                  TEXT NOT NULL,
            description           TEXT NOT NULL,
            amount                REAL NOT NULL,
            currency              TEXT NOT NULL DEFAULT 'ARS',
            installment           TEXT,
            category              TEXT NOT NULL,
            macro_group           TEXT NOT NULL,
            excluded_from_budget INTEGER NOT NULL DEFAULT 0,
            duplicate_key         TEXT,
            created_at            TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS upcoming_installments (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file_id TEXT NOT NULL,
            file_name      TEXT NOT NULL,
            bank           TEXT NOT NULL,
            month          TEXT NOT NULL,
            amount         REAL NOT NULL,
            created_at     TEXT DEFAULT (datetime('now'))
        )
    """)

    try:
        conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS transaction_vectors USING vec0(
                id INTEGER PRIMARY KEY,
                embedding FLOAT[{EMBEDDING_DIM}]
            )
        """)
    except Exception:
        # Fallback if vec0 is unsupported on local sqlite driver
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transaction_vectors (
                id INTEGER PRIMARY KEY,
                embedding TEXT
            )
        """)

    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()}
    if "duplicate_key" not in existing_columns:
        conn.execute("ALTER TABLE transactions ADD COLUMN duplicate_key TEXT")

    backfill_rows = conn.execute("""
            SELECT id, close_date, date, description, amount
            FROM transactions
            WHERE duplicate_key IS NULL
        """).fetchall()
    for row in backfill_rows:
        txn = {
            "close_date": row["close_date"],
            "date": row["date"],
            "description": row["description"],
            "amount": row["amount"],
        }
        conn.execute(
            "UPDATE transactions SET duplicate_key = ? WHERE id = ?",
            (transaction_duplicate_key(txn), row["id"]),
        )

    existing_keys = conn.execute("SELECT id, duplicate_key FROM transactions WHERE duplicate_key IS NOT NULL ORDER BY id").fetchall()
    seen_duplicate_keys = set()
    duplicate_ids = []
    for row in existing_keys:
        key = row["duplicate_key"]
        if key in seen_duplicate_keys:
            duplicate_ids.append(row["id"])
        else:
            seen_duplicate_keys.add(key)
    for duplicate_id in duplicate_ids:
        try:
            conn.execute("DELETE FROM transaction_vectors WHERE id = ?", (duplicate_id,))
        except Exception:
            pass
        conn.execute("DELETE FROM transactions WHERE id = ?", (duplicate_id,))

    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_transactions_duplicate_key
        ON transactions(duplicate_key)
        WHERE duplicate_key IS NOT NULL
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_files (
            file_id      TEXT PRIMARY KEY,
            file_name    TEXT NOT NULL,
            bank         TEXT,
            processed_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name   TEXT,
            step        TEXT,
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


def mark_file_processed(conn: sqlite3.Connection, file_id: str, file_name: str, bank: str | None = None) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO processed_files (file_id, file_name, bank) VALUES (?, ?, ?)",
        (file_id, file_name, bank),
    )
    conn.commit()


def log_error(conn: sqlite3.Connection, file_name: str, step: str, message: str) -> None:
    conn.execute(
        "INSERT INTO errors (file_name, step, message) VALUES (?, ?, ?)",
        (file_name, step, message),
    )
    conn.commit()


def write_intake_payload(
    file_name: str,
    bank: str,
    transactions: list[dict],
    upcoming_installments: list[dict] | None = None,
    file_id: str | None = None,
    db_path: str = DB_PATH,
) -> dict:
    """
    Task 4: Database Write.
    
    Atomically persists categorized transactions, upcoming installments, and vector embeddings.
    Both relational and vector writes occur in the same logical operation (transaction).
    Marks source file as processed only after successful commit.
    Uses a fresh connection.
    
    Returns:
      { "file": file_name, "bank": bank, "transactions_written": count, "status": "committed" }
    """
    target_file_id = file_id or file_name
    upcoming = upcoming_installments or []

    with fresh_connection(db_path) as conn:
        init_db(conn)

        if is_file_processed(conn, target_file_id):
            return {
                "file": file_name,
                "bank": bank,
                "transactions_written": 0,
                "status": "already_processed",
            }

        try:
            conn.execute("BEGIN TRANSACTION")

            written_count = 0
            for txn in transactions:
                duplicate_key = transaction_duplicate_key(txn)
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO transactions (
                        source_file_id, file_name, bank, account_type, card_network,
                        close_date, date, description, amount, currency, installment,
                        category, macro_group, excluded_from_budget, duplicate_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        target_file_id,
                        file_name,
                        bank,
                        txn["account_type"],
                        txn.get("card_network"),
                        txn.get("close_date"),
                        txn["date"],
                        txn["description"],
                        txn["amount"],
                        txn.get("currency", "ARS"),
                        txn.get("installment"),
                        txn["category"],
                        txn["macro_group"],
                        1 if txn.get("excluded_from_budget") else 0,
                        duplicate_key,
                    ),
                )
                if cur.rowcount == 0:
                    continue

                txn_id = cur.lastrowid

                # Write embedding to vector store in the same transaction
                embedding = txn.get("embedding")
                if embedding:
                    try:
                        import sqlite_vec
                        conn.execute(
                            "INSERT INTO transaction_vectors (id, embedding) VALUES (?, ?)",
                            (txn_id, sqlite_vec.serialize_float32(embedding)),
                        )
                    except Exception:
                        conn.execute(
                            "INSERT INTO transaction_vectors (id, embedding) VALUES (?, ?)",
                            (txn_id, str(embedding)),
                        )
                written_count += 1

            for inst in upcoming:
                conn.execute(
                    """
                    INSERT INTO upcoming_installments (
                        source_file_id, file_name, bank, month, amount
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (target_file_id, file_name, bank, inst["month"], inst["amount"]),
                )

            # Mark source file as processed inside the same transaction
            conn.execute(
                "INSERT INTO processed_files (file_id, file_name, bank) VALUES (?, ?, ?)",
                (target_file_id, file_name, bank),
            )

            conn.commit()

            return {
                "file": file_name,
                "bank": bank,
                "transactions_written": written_count,
                "status": "committed",
            }
        except Exception as e:
            conn.rollback()
            log_error(conn, file_name, "Task 4 Database Write", str(e))
            raise RuntimeError(f"Database write failed for file '{file_name}': {e}") from e


def get_all_transactions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM transactions").fetchall()


def totals_by_macro_group(conn: sqlite3.Connection, start_date: str | None = None, end_date: str | None = None) -> list[sqlite3.Row]:
    query = """
        SELECT macro_group, category, SUM(amount) AS total, COUNT(*) AS txn_count
        FROM transactions
        WHERE excluded_from_budget = 0
    """
    params = []
    if start_date and end_date:
        query += " AND date BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    query += " GROUP BY macro_group, category"
    return conn.execute(query, params).fetchall()