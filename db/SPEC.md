# Database Specification

This module handles persistence for all Finance Agent data using SQLite and sqlite-vec.

## Responsibilities

- Create and initialize SQLite relational and vector schemas.
- Track processed input files to prevent double-ingestion.
- Log intake errors.
- Store categorized transactions, upcoming installments, and vector embeddings atomically.
- Support aggregation and semantic search queries.

## Structure

- `db.py`: Database connection helpers, schema initialization, atomic write operations, and reporting queries.

## Key Interface

- `write_intake_payload(file_name, bank, transactions, upcoming_installments, file_id)`
- `fresh_connection(db_path)`
- `init_db(conn)`
- `is_file_processed(conn, file_id)`
- `totals_by_macro_group(conn, start_date, end_date)`
