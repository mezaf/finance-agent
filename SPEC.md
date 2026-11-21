# Personal Finance Automation System — Master Specification

This document provides a comprehensive architectural specification for the Personal Finance Automation System, detailing its overall purpose, engineering goals, technical solutions, database schemas, and module contracts.

---

## 🎯 Purpose, Goals & Engineering Solutions

### 1. Problem Statement & Purpose
Personal financial statements in Argentina (BBVA, Banco Galicia, Banco Nación, Banco Santander) present unique challenges:
- **Consolidated Layouts**: Single PDFs often consolidate multiple accounts (checking/savings) and credit card networks (Visa/Master).
- **Inconsistent Formatting**: Varied date formats, installment tags (e.g. `C.03/12`), non-transaction promotional blocks, subtotal rows, and tax charges (IVA, IIBB).
- **Budget Categorization Drift**: Manual or ad-hoc categorization leads to inconsistent bucket definitions across months.
- **Search Limitations**: Traditional SQL text queries fail to find merchant variations or natural-language spending patterns ("what stopped being charged?").

The system provides an automated, deterministic intake engine, vector search store, analytics middleware, and visualization dashboard to solve these challenges.

### 2. Primary Engineering Goals
1. **Zero-Guessing Bank Identification**: Deterministically identify issuing banks from PDF text/headers without LLM hallucination.
2. **Normalized Transaction Extraction**: Convert heterogeneous PDF layouts into unified, structured transaction records.
3. **20/70/10 Budget Principle**: Automatically assign transactions into 70% Needs/Fixed Pays, 20% Savings & Invest, and 10% Leisure & Others.
4. **Description-Only Vector Search**: Embed merchant descriptions only (`all-MiniLM-L6-v2`) to enable hybrid semantic search while storing magnitudes and dates as structured metadata.
5. **Atomic Commit & Fault Tolerance**: Ensure relational records, upcoming installments, and vector embeddings commit in a single SQLite database transaction per statement file.
6. **Deterministic Charting & Flexible Insights**: Provide pure SQL aggregation for dashboard charts (Tier 1) and multi-route natural-language insights (Tier 2).
7. **TDC Credit Card Scope for Charts**: All dashboard chart queries and analysis routes exclusively aggregate transactions where `account_type = 'tdc'` (credit card). Bank account data is persisted but dismissed from budget visualizations.
8. **Live UI Data Pipeline**: Charts are never rendered from static/hardcoded data. The UI fetches live SQL aggregations from `/api/charts` on every page load and cross-filter interaction.
9. **Direct UI Statement Intake**: Uploading a PDF via the web dashboard automatically triggers the full 5-step Intake Orchestrator with real-time visual feedback (status pill, progress bar, typing indicator).

---

## 📐 System Architecture & Module Pipeline

```mermaid
flowchart TD
    subgraph 1. Intake Ingestion (data_load)
        A["PDF Statement"] --> B["Task 0: Bank Identification (bank.py)"]
        B --> C["Task 1: Layout Extraction (extractor.py + specs/<bank>.md)"]
        C --> D["Task 2: 20/70/10 Categorization (categorize.py)"]
        D --> E["Task 3: Description Vector Embedding (embeddings.py)"]
        E --> F["Task 4: Atomic DB Write (db/db.py)"]
    end
    
    subgraph 2. Database Store (db)
        F --> G[("SQLite + sqlite-vec (finance.db)")]
    end
    
    subgraph 3. Analytics Middleware (data_analysis)
        G -->|"TDC Only"| H["Tier 1: Layout Queries (Deterministic SQL)"]
        G -->|"TDC Only"| I["Tier 2: Natural-Language Insights (Multi-Route)"]
    end
    
    subgraph 4. Web Application (web_app)
        H -->|"GET /api/charts"| J["Plotly.js Dashboard UI (index.html)"]
        I --> K["AI Chat Assistant (chat.py + app.py)"]
    end
```

---

## 🗄️ Database Schemas (`finance.db`)

The persistence layer uses SQLite with `sqlite-vec` extension support.

### `transactions`
Relational store for categorized transaction records:
```sql
CREATE TABLE IF NOT EXISTS transactions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file_id        TEXT NOT NULL,
    file_name             TEXT NOT NULL,
    bank                  TEXT NOT NULL,          -- 'bbva' | 'galicia' | 'bna' | 'santander'
    account_type          TEXT NOT NULL,          -- 'account' | 'tdc'
    card_network          TEXT,                   -- 'visa' | 'master' | NULL
    close_date            TEXT,                   -- ISO YYYY-MM-DD
    date                  TEXT NOT NULL,          -- ISO YYYY-MM-DD
    description           TEXT NOT NULL,          -- exact raw text (e.g. 'CARREFOUR C.03/12')
    amount                REAL NOT NULL,          -- signed decimal (debits negative, credits positive)
    currency              TEXT NOT NULL DEFAULT 'ARS',
    installment           TEXT,                   -- e.g. '03/12'
    category              TEXT NOT NULL,          -- e.g. 'Supermarket', 'Utilities', 'Food Delivery'
    macro_group           TEXT NOT NULL,          -- '70% Needs/Fixed Pays' | '20% Savings & Invest' | '10% Leisure & Others'
    excluded_from_budget INTEGER NOT NULL DEFAULT 0, -- 1 for payments ('su pago'), 0 for regular transactions
    created_at            TEXT DEFAULT (datetime('now'))
);
```

### `upcoming_installments`
Relational store for future installment commitments extracted from statements ("Cuotas a vencer"):
```sql
CREATE TABLE IF NOT EXISTS upcoming_installments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file_id TEXT NOT NULL,
    file_name      TEXT NOT NULL,
    bank           TEXT NOT NULL,
    month          TEXT NOT NULL,                 -- ISO YYYY-MM
    amount         REAL NOT NULL,
    created_at     TEXT DEFAULT (datetime('now'))
);
```

### `transaction_vectors`
Virtual vector store (`vec0`) for 384-dimensional embeddings:
```sql
CREATE VIRTUAL TABLE IF NOT EXISTS transaction_vectors USING vec0(
    id INTEGER PRIMARY KEY,
    embedding FLOAT[384]
);
```

### `processed_files`
Idempotency tracker to prevent duplicate file processing:
```sql
CREATE TABLE IF NOT EXISTS processed_files (
    file_id      TEXT PRIMARY KEY,
    file_name    TEXT NOT NULL,
    bank         TEXT,
    processed_at TEXT DEFAULT (datetime('now'))
);
```

### `errors`
Error log table recording file-level failure tracebacks:
```sql
CREATE TABLE IF NOT EXISTS errors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name   TEXT,
    step        TEXT,
    message     TEXT,
    occurred_at TEXT DEFAULT (datetime('now'))
);
```

---

## 🎨 Color System & Category Map

To maintain a calm, trustworthy financial aesthetic, the UI uses fixed category colors mapped to macro group hue families:

| Macro Group | Category | Hex Code | Visual Tone |
|---|---|---|---|
| **70% Needs/Fixed Pays** | Supermarket | `#1B3A5C` | Deep Navy |
| | Utilities | `#3D6A94` | Medium Blue |
| | Insurance | `#7FA6C9` | Soft Sky Blue |
| **20% Savings & Invest** | Savings | `#2F6B4F` | Forest Green |
| | Investment | `#6FA985` | Sage Green |
| **10% Leisure & Others** | Leisure | `#C58B2E` | Muted Amber |
| | Streaming | `#D9A857` | Warm Gold |
| | Food Delivery | `#B8895F` | Tan / Bronze |
| | Other / Uncategorized | `#8C8378` | Warm Slate Gray |

---

## 🔌 Web Application REST API Summary

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/charts` | Unified live chart data (all 4 Tier 1 queries, TDC only). Supports `?month=` and `?macro_group=` filters. |
| `POST` | `/api/upload` | Upload PDF statement, returns `fileId`. |
| `POST` | `/api/process_upload/<file_id>` | Trigger 5-step Intake Orchestrator on uploaded PDF. Returns transaction count + refreshed chart data. |
| `POST` | `/api/chat` | Chat message with optional `fileId` for intake trigger. |
| `GET` | `/api/transactions` | Recent TDC transactions (`?limit=20`). |
| `POST` | `/api/analysis_query` | Tier 2 natural language insight query. |

---

## 🖥️ Dashboard Visual Feedback System

The dashboard header bar contains a persistent status pill that communicates the current application state:

| State | Visual | Description |
|---|---|---|
| **Ready** | 🟢 Green | App is idle and responsive |
| **Loading** | 🔵 Blue | Fetching chart data or waiting for AI |
| **Processing** | 🟡 Amber (pulsing) | Running 5-step Intake Orchestrator on uploaded PDF |
| **Success** | 🟢 Green (solid) | Operation completed (auto-reverts to Ready after 4s) |
| **Error** | 🔴 Red (solid) | Operation failed (auto-reverts after 4s) |

Additional feedback elements:
- **Upload Zone**: Indeterminate progress bar animation during intake processing
- **Chat Thread**: Bouncing dots typing indicator while waiting for API responses
- **Chat Input**: Disabled with "Waiting for response..." placeholder during API calls

---

## 📜 Module Contracts Summary

- **`data_load/SPEC.md`**: Documents the 5-step Intake Orchestrator (`identify_bank` → `extract_statement_data` → `categorize_transactions` → `generate_embeddings_for_transactions` → `write_intake_payload`).
- **`data_analysis/SPEC.md`**: Documents Tier 1 Layout Queries (TDC-scoped: `get_monthly_expenses`, `get_macro_groups`, `get_category_sunburst`, `get_installments`) and Tier 2 Insight Queries (`query_insights`).
- **`db/SPEC.md`**: Documents SQLite connection helpers, schema definitions, and atomic transaction persistence.
- **`web_app/SPEC.md`**: Documents Flask REST endpoints (incl. `/api/charts` and `/api/process_upload`), live data pipeline, side panel layout, Plotly charts, cross-filtering, global status indicator, and direct UI intake processing.
