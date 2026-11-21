"""
data_analysis/analysis.py — Data Analysis Middleware.

Sits between the database (relational + vector store) and the UI dashboard.
Never modifies data — only queries, aggregates, and shapes it into UI-ready JSON.
Exclusively focuses on Credit Card ('tdc') statement data for budget analysis.

TIER 1: Layout Queries (100% deterministic SQL, no LLM reasoning)
  - get_monthly_expenses()
  - get_macro_groups()
  - get_category_sunburst()
  - get_installments()

TIER 2: Natural-Language Insight Queries (Hybrid SQL + vector + LLM judgment)
  - query_insights()
"""

import os
import re
import unicodedata
from datetime import datetime
from google import genai

MODEL_NAME = "gemini-3.5-flash"
_client: genai.Client | None = None


def get_client() -> genai.Client | None:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            _client = genai.Client(api_key=api_key)
    return _client


# =====================================================================
# TIER 1: Layout Queries (deterministic, no LLM reasoning)
# =====================================================================

def get_monthly_expenses(conn, month: str | None = None, macro_group: str | None = None) -> dict:
    """
    Tier 1 Function: get_monthly_expenses()
    Groups TDC credit card transactions by close_date (month) and sums absolute amounts.
    """
    query = """
        SELECT strftime('%Y-%m', COALESCE(close_date, date)) AS month_key,
               ROUND(SUM(ABS(amount)), 2) AS total
        FROM transactions
        WHERE excluded_from_budget = 0 AND account_type = 'tdc' AND (category IS NULL OR category != 'Payment')
    """
    params = []
    if month:
        query += " AND strftime('%Y-%m', COALESCE(close_date, date)) = ?"
        params.append(month)
    if macro_group:
        query += " AND macro_group = ?"
        params.append(macro_group)

    query += " GROUP BY month_key ORDER BY month_key ASC"

    rows = conn.execute(query, params).fetchall()
    data = [{"month": r["month_key"] or "unknown", "total": float(r["total"] or 0.0)} for r in rows if r["month_key"]]

    return {
        "chart": "monthly_expenses",
        "data": data,
    }


def get_macro_groups(conn, month: str | None = None) -> dict:
    """
    Tier 1 Function: get_macro_groups()
    Groups TDC credit card spend by macro_group (70% Needs/Fixed Pays, 20% Savings & Invest, 10% Leisure & Others).
    """
    query = """
        SELECT macro_group, ROUND(SUM(ABS(amount)), 2) AS total
        FROM transactions
        WHERE excluded_from_budget = 0 AND account_type = 'tdc' AND (category IS NULL OR category != 'Payment')
    """
    params = []
    if month:
        query += " AND strftime('%Y-%m', COALESCE(close_date, date)) = ?"
        params.append(month)

    query += " GROUP BY macro_group ORDER BY total DESC"

    rows = conn.execute(query, params).fetchall()
    data = [{"macro_group": r["macro_group"], "total": float(r["total"] or 0.0)} for r in rows if r["macro_group"]]

    return {
        "chart": "macro_groups",
        "filter_applied": {"month": month},
        "data": data,
    }


def get_category_sunburst(conn, month: str | None = None, macro_group: str | None = None) -> dict:
    """
    Tier 1 Function: get_category_sunburst()
    Two-level hierarchy only for TDC credit card spend: category -> aggregated description.
    """
    query = """
        SELECT category, description, ROUND(SUM(ABS(amount)), 2) AS total
        FROM transactions
        WHERE excluded_from_budget = 0 AND account_type = 'tdc' AND (category IS NULL OR category != 'Payment')
    """
    params = []
    if month:
        query += " AND strftime('%Y-%m', COALESCE(close_date, date)) = ?"
        params.append(month)
    if macro_group:
        query += " AND macro_group = ?"
        params.append(macro_group)

    query += " GROUP BY category, description ORDER BY category, total DESC"

    rows = conn.execute(query, params).fetchall()

    ids = []
    labels = []
    parents = []
    values = []

    category_totals = {}
    category_children = {}

    for r in rows:
        cat = r["category"] or "Other/Uncategorized"
        desc = r["description"] or "Unknown"
        tot = float(r["total"] or 0.0)

        if cat not in category_totals:
            category_totals[cat] = 0.0
            category_children[cat] = []
        category_totals[cat] += tot
        category_children[cat].append((desc, tot))

    # Build category root nodes first
    for cat, cat_tot in category_totals.items():
        cat_id = cat
        ids.append(cat_id)
        labels.append(cat)
        parents.append("")
        values.append(round(cat_tot, 2))

        # Build description leaf nodes with unique IDs
        for desc, desc_tot in category_children[cat]:
            clean_desc = re.sub(r"[^a-zA-Z0-9_-]", "_", desc)[:30]
            leaf_id = f"{cat_id}-{clean_desc}"
            # Ensure unique id
            counter = 1
            original_leaf_id = leaf_id
            while leaf_id in ids:
                leaf_id = f"{original_leaf_id}_{counter}"
                counter += 1

            ids.append(leaf_id)
            labels.append(desc)
            parents.append(cat_id)
            values.append(round(desc_tot, 2))

    return {
        "chart": "category_sunburst",
        "filter_applied": {"month": month, "macro_group": macro_group},
        "data": {
            "ids": ids,
            "labels": labels,
            "parents": parents,
            "values": values,
        },
    }


def get_installments(conn, month: str | None = None) -> dict:
    """
    Tier 1 Function: get_installments()
    Historical billed credit card installments + upcoming projected installments.
    """
    data = []

    # Historical billed TDC installments
    query_billed = """
        SELECT strftime('%Y-%m', COALESCE(close_date, date)) AS month_key,
               ROUND(SUM(ABS(amount)), 2) AS total
        FROM transactions
        WHERE excluded_from_budget = 0 AND account_type = 'tdc' AND (installment IS NOT NULL OR description LIKE '%C.%/%')
    """
    params_billed = []
    if month:
        query_billed += " AND strftime('%Y-%m', COALESCE(close_date, date)) = ?"
        params_billed.append(month)

    query_billed += " GROUP BY month_key ORDER BY month_key ASC"

    billed_rows = conn.execute(query_billed, params_billed).fetchall()
    for r in billed_rows:
        if r["month_key"]:
            data.append({
                "month": r["month_key"],
                "amount": float(r["total"] or 0.0),
                "type": "billed",
            })

    # Upcoming installments (from TDC credit card statements)
    query_upcoming = """
        SELECT month, ROUND(SUM(ABS(amount)), 2) AS total
        FROM upcoming_installments
    """
    params_upcoming = []
    if month:
        query_upcoming += " WHERE month = ?"
        params_upcoming.append(month)

    query_upcoming += " GROUP BY month ORDER BY month ASC"

    try:
        upcoming_rows = conn.execute(query_upcoming, params_upcoming).fetchall()
        for r in upcoming_rows:
            if r["month"]:
                data.append({
                    "month": r["month"],
                    "amount": float(r["total"] or 0.0),
                    "type": "upcoming",
                })
    except Exception:
        pass

    # Sort combined series by month
    data.sort(key=lambda x: (x["month"], x["type"]))

    return {
        "chart": "installments_over_time",
        "data": data,
    }


# =====================================================================
# TIER 2: Natural-Language Insight Queries (hybrid SQL + vector + LLM)
# =====================================================================

def query_insights(conn, query: str) -> dict:
    """
    Tier 2 Function: query_insights()
    Routes questions to SQL only, SQL + recurrence, or Hybrid LLM judgment.
    Always includes 'answer_summary' and 'supporting_data'.
    """
    q_lower = (query or "").lower().strip()

    # Route 1: Stopped charges / cadence changes ("stopped", "no longer", "used to", "dejo de")
    if any(kw in q_lower for kw in ["stopped", "no longer", "used to", "dejo de", "ya no"]):
        return _route_stopped_charges(conn, query)

    # Route 2: Single deterministic fact ("largest", "highest", "uncategorized", "max", "sin categoria")
    if any(kw in q_lower for kw in ["largest", "highest", "max", "biggest", "uncategorized", "no category", "sin categoria"]):
        return _route_largest_uncategorized(conn, query)

    # Route 3: Hierarchical cut review (macro group -> category -> stored description)
    if _chat_requests_spend_review(q_lower):
        review = _answer_spend_review(conn, query, q_lower)
        return {
            "query": query,
            "route": "spend_review",
            "answer_summary": review["answer"],
            "supporting_data": review["supporting_data"],
        }

    # Route 4: Hybrid judgment ("leisure", "remove", "easier to remove", "cut", "reduce", "discretionary")
    if any(kw in q_lower for kw in ["leisure", "remove", "cut", "easier", "eliminate", "discretionary", "gastos"]):
        return _route_leisure_removal_insights(conn, query)

    # Default fallback Tier 2 query handler
    return _route_general_insight(conn, query)


def answer_chat_query(conn, query: str, history: list | None = None) -> dict:
    """Answer a chat question from read-only TDC transaction data."""
    question = (query or "").strip()
    normalized = _normalize_chat_text(question)
    if normalized in {"hi", "hello", "hey", "hola", "buenos dias", "buenas"}:
        answer = "Hi. Ask me about your credit-card leisure or uncategorized spending."
        return {"reply": answer, "answer": answer, "sources": [], "supporting_data": []}

    if _chat_requests_spend_review(normalized):
        return _answer_spend_review(conn, query, normalized)

    effective_question, context_used = _resolve_chat_follow_up(question, history or [])
    normalized = _normalize_chat_text(effective_question)
    if not context_used and _asks_for_non_tdc_data(normalized):
        answer = "I can currently answer questions about credit-card (TDC) transactions only."
        return {"reply": answer, "answer": answer, "sources": [], "supporting_data": []}
    if not context_used and not _is_supported_spending_question(normalized):
        answer = "I can answer questions about TDC spending, including leisure, uncategorized items, totals, and transaction details. What would you like to check?"
        return {"reply": answer, "answer": answer, "sources": [], "supporting_data": []}

    category_names, macro_group = _chat_category_scope(normalized)
    month = _chat_month_filter(normalized)

    where = [
        "account_type = 'tdc'",
        "excluded_from_budget = 0",
        "COALESCE(category, '') != 'Payment'",
        "amount < 0",
    ]
    params: list[str] = []
    if category_names:
        placeholders = ", ".join("?" for _ in category_names)
        where.append(f"COALESCE(category, 'Other/Uncategorized') IN ({placeholders})")
        params.extend(category_names)
    elif macro_group:
        where.append("macro_group = ?")
        params.append(macro_group)
    if month:
        where.append("strftime('%Y-%m', COALESCE(close_date, date)) = ?")
        params.append(month)
    where_sql = " AND ".join(where)

    totals = conn.execute(
        f"""SELECT currency, ROUND(SUM(ABS(amount)), 2) AS total, COUNT(*) AS count
            FROM transactions WHERE {where_sql} GROUP BY currency ORDER BY currency""",
        params,
    ).fetchall()
    if not totals:
        scope_label = _chat_scope_label(category_names, macro_group)
        period_label = f" in {month}" if month else ""
        answer = f"I couldn't find eligible TDC charges for {scope_label}{period_label}."
        return {
            "reply": answer,
            "answer": answer,
            "filters_applied": {"account_type": "tdc", "categories": category_names, "macro_group": macro_group, "month": month},
            "sources": [],
            "supporting_data": [],
            "conversation_context_used": context_used,
        }

    items = conn.execute(
        f"""SELECT COALESCE(category, 'Other/Uncategorized') AS category,
                   description, currency, ROUND(SUM(ABS(amount)), 2) AS total,
                   COUNT(*) AS count, GROUP_CONCAT(DISTINCT file_name) AS source_files
            FROM transactions WHERE {where_sql}
            GROUP BY category, description, currency
            ORDER BY total DESC LIMIT 8""",
        params,
    ).fetchall()
    sources = conn.execute(
        f"SELECT DISTINCT file_name FROM transactions WHERE {where_sql} ORDER BY file_name",
        params,
    ).fetchall()
    source_names = [row["file_name"] for row in sources if row["file_name"]]
    total_labels = [f"{row['currency']} {float(row['total'] or 0):,.2f}" for row in totals]
    total_count = sum(int(row["count"] or 0) for row in totals)
    scope_label = _chat_scope_label(category_names, macro_group)
    period_label = f" for {month}" if month else ""
    answer = f"Your TDC {scope_label} charges{period_label} total {', '.join(total_labels)} across {total_count} transactions."

    if _chat_requests_details(normalized):
        item_labels = [
            f"{row['description']} ({row['currency']} {float(row['total'] or 0):,.2f})"
            for row in items[:5]
        ]
        if item_labels:
            answer += " Top items: " + "; ".join(item_labels) + "."
    if source_names:
        shown_sources = source_names[:3]
        answer += " Source statement" + ("s" if len(shown_sources) != 1 else "") + ": " + ", ".join(shown_sources)
        if len(source_names) > len(shown_sources):
            answer += f" and {len(source_names) - len(shown_sources)} more"
        answer += "."

    return {
        "reply": answer,
        "answer": answer,
        "filters_applied": {"account_type": "tdc", "categories": category_names, "macro_group": macro_group, "month": month},
        "sources": source_names,
        "supporting_data": {
            "totals": [
                {"currency": row["currency"], "total": float(row["total"] or 0), "count": int(row["count"] or 0)}
                for row in totals
            ],
            "items": [
                {
                    "category": row["category"],
                    "description": row["description"],
                    "currency": row["currency"],
                    "total": float(row["total"] or 0),
                    "count": int(row["count"] or 0),
                    "source_files": (row["source_files"] or "").split(",") if row["source_files"] else [],
                }
                for row in items
            ],
        },
        "conversation_context_used": context_used,
    }


def _normalize_chat_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower().strip()


def _chat_category_scope(query: str) -> tuple[list[str], str | None]:
    has_leisure = any(word in query for word in ("leisure", "ocio", "streaming", "food delivery", "delivery", "discretionary"))
    has_other = any(word in query for word in ("uncategorized", "uncategorised", "sin categoria", "sin categorizar", "other/uncategorized", "other expenses", "other category", "otros"))
    if any(word in query for word in ("10%", "leisure & others", "leisure and others", "macro group")):
        return [], "10% Leisure & Others"
    categories = []
    if has_leisure:
        categories.extend(("Leisure", "Streaming", "Food Delivery"))
    if has_other:
        categories.append("Other/Uncategorized")
    return categories, None


def _chat_scope_label(categories: list[str], macro_group: str | None) -> str:
    if macro_group:
        return "10% Leisure & Others"
    if categories:
        if "Other/Uncategorized" in categories and len(categories) > 1:
            return "leisure and uncategorized"
        if "Other/Uncategorized" in categories:
            return "uncategorized"
        return "leisure"
    return "credit-card"


def _chat_month_filter(query: str) -> str | None:
    today = datetime.now()
    if any(phrase in query for phrase in ("last month", "previous month", "past month", "mes pasado", "mes anterior")):
        month_number = today.month - 1 or 12
        year = today.year - (1 if today.month == 1 else 0)
        return f"{year:04d}-{month_number:02d}"
    if any(phrase in query for phrase in ("this month", "current month", "este mes")):
        return today.strftime("%Y-%m")

    explicit_months = re.findall(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", query)
    if explicit_months:
        year, month = explicit_months[-1]
        return f"{year}-{month}"

    month_numbers = {
        "january": 1, "jan": 1, "enero": 1,
        "february": 2, "feb": 2, "febrero": 2,
        "march": 3, "mar": 3, "marzo": 3,
        "april": 4, "apr": 4, "abril": 4,
        "may": 5, "mayo": 5,
        "june": 6, "jun": 6, "junio": 6,
        "july": 7, "jul": 7, "julio": 7,
        "august": 8, "aug": 8, "agosto": 8, "ago": 8,
        "september": 9, "sep": 9, "septiembre": 9, "setiembre": 9,
        "october": 10, "oct": 10, "octubre": 10,
        "november": 11, "nov": 11, "noviembre": 11,
        "december": 12, "dec": 12, "diciembre": 12,
    }
    mentioned_months = [(match.start(), month_numbers[match.group()]) for match in re.finditer(r"\b(?:" + "|".join(sorted(month_numbers, key=len, reverse=True)) + r")\b", query) if match.group() in month_numbers]
    if mentioned_months:
        month_number = mentioned_months[-1][1]
        years = re.findall(r"\b(20\d{2})\b", query)
        year = int(years[-1]) if years else datetime.now().year
        return f"{year:04d}-{month_number:02d}"

    return None


def _resolve_chat_follow_up(query: str, history: list) -> tuple[str, bool]:
    normalized = _normalize_chat_text(query)
    follow_up = any(
        phrase in normalized
        for phrase in ("what about", "how about", "and ", "those", "these", "them", "show me", "list them", "what were")
    )
    if not follow_up or _chat_category_scope(normalized)[0] or _chat_category_scope(normalized)[1]:
        return query, False
    for message in reversed(history[-12:]):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        previous = str(message.get("text") or message.get("content") or "").strip()
        if _chat_category_scope(_normalize_chat_text(previous))[0] or _chat_category_scope(_normalize_chat_text(previous))[1]:
            return f"{previous} {query}", True
    return query, False


def _chat_requests_details(query: str) -> bool:
    return any(word in query for word in ("show", "list", "which", "breakdown", "details", "transactions", "items", "largest", "biggest", "top"))


def _asks_for_non_tdc_data(query: str) -> bool:
    return any(phrase in query for phrase in ("checking account", "bank account", "savings account", "account statement", "debit card"))


def _is_supported_spending_question(query: str) -> bool:
    if _chat_category_scope(query)[0] or _chat_category_scope(query)[1] or _chat_month_filter(query):
        return True
    return any(
        word in query
        for word in (
            "spend", "spent", "spending", "expense", "expenses", "transaction", "transactions",
            "charge", "charges", "merchant", "category", "categories", "budget", "total", "amount",
            "paid", "purchase", "purchases", "consumo", "consumos", "gasto", "gastos", "pague",
        )
    )


def _route_stopped_charges(conn, query: str) -> dict:
    """Route: SQL + recurrence check for stopped charges on TDC."""
    latest_row = conn.execute("SELECT MAX(date) as max_d FROM transactions WHERE account_type = 'tdc'").fetchone()
    latest_date_str = latest_row["max_d"] if latest_row and latest_row["max_d"] else datetime.now().strftime("%Y-%m-%d")

    rows = conn.execute("""
        SELECT description, category, COUNT(*) as frequency,
               MAX(date) as last_date, ROUND(SUM(ABS(amount)), 2) as total_amount
        FROM transactions
        WHERE excluded_from_budget = 0 AND account_type = 'tdc'
        GROUP BY description
        HAVING frequency >= 2
        ORDER BY last_date ASC
    """).fetchall()

    stopped = []
    latest_dt = datetime.strptime(latest_date_str, "%Y-%m-%d") if len(latest_date_str) == 10 else datetime.now()

    for r in rows:
        last_dt_str = r["last_date"]
        if len(last_dt_str) == 10:
            last_dt = datetime.strptime(last_dt_str, "%Y-%m-%d")
            days_ago = (latest_dt - last_dt).days
            if days_ago >= 45:
                stopped.append({
                    "description": r["description"],
                    "category": r["category"],
                    "frequency": int(r["frequency"]),
                    "last_charged": r["last_date"],
                    "total_amount": float(r["total_amount"]),
                })

    if stopped:
        summary = f"Identified {len(stopped)} recurring credit card charges that have stopped appearing in recent cycles."
    else:
        summary = "No recurring credit card charges appear to have stopped recently."

    return {
        "query": query,
        "route": "sql_recurrence",
        "answer_summary": summary,
        "supporting_data": stopped,
    }


def _route_largest_uncategorized(conn, query: str) -> dict:
    """Route: SQL only for largest uncategorized spend on TDC."""
    row = conn.execute("""
        SELECT description, category, ROUND(ABS(amount), 2) as amount, date, bank
        FROM transactions
        WHERE excluded_from_budget = 0 AND account_type = 'tdc' AND (category = 'Other/Uncategorized' OR category IS NULL)
        ORDER BY ABS(amount) DESC
        LIMIT 1
    """).fetchone()

    if row:
        summary = f"The largest uncategorized credit card expense is '{row['description']}' for ${float(row['amount']):.2f} on {row['date']}."
        data = [{
            "description": row["description"],
            "category": row["category"] or "Other/Uncategorized",
            "amount": float(row["amount"]),
            "date": row["date"],
            "bank": row["bank"],
        }]
    else:
        summary = "No uncategorized credit card spend records were found."
        data = []

    return {
        "query": query,
        "route": "sql_only",
        "answer_summary": summary,
        "supporting_data": data,
    }


def _route_leisure_removal_insights(conn, query: str) -> dict:
    """Route: Hybrid SQL + Vector grouping + LLM judgment on TDC discretionary spend."""
    rows = conn.execute("""
        SELECT description, category, COUNT(*) as frequency, ROUND(SUM(ABS(amount)), 2) as total_amount
        FROM transactions
        WHERE excluded_from_budget = 0 AND account_type = 'tdc' AND macro_group = '10% Leisure & Others'
        GROUP BY description
        ORDER BY total_amount DESC
    """).fetchall()

    supporting_data = []
    for r in rows:
        freq = int(r["frequency"])
        cat = r["category"]
        if cat in ["Food Delivery", "Leisure"]:
            ease = "easy"
        elif cat == "Streaming":
            ease = "medium"
        else:
            ease = "easy" if freq < 3 else "medium"

        supporting_data.append({
            "description": r["description"],
            "category": cat,
            "frequency": freq,
            "total_amount": float(r["total_amount"]),
            "removal_ease": ease,
        })

    client = get_client()
    summary = "Discretionary food delivery and dining out expenses on credit cards are easiest to remove immediately."
    if client and supporting_data:
        try:
            items_desc = ", ".join([f"{item['description']} (${item['total_amount']:.2f})" for item in supporting_data[:5]])
            prompt = (
                f"User asked: '{query}'.\n"
                f"Top leisure items: {items_desc}.\n"
                "Give a concise 1-2 sentence recommendation on which items are easiest to eliminate to save money."
            )
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )
            summary = (response.text or "").strip()
        except Exception:
            pass

    return {
        "query": query,
        "route": "hybrid",
        "answer_summary": summary,
        "supporting_data": supporting_data,
    }


def _route_general_insight(conn, query: str) -> dict:
    """Fallback Tier 2 route for general questions on TDC spend."""
    rows = conn.execute("""
        SELECT category, ROUND(SUM(ABS(amount)), 2) as total_amount, COUNT(*) as count
        FROM transactions
        WHERE excluded_from_budget = 0 AND account_type = 'tdc'
        GROUP BY category
        ORDER BY total_amount DESC
    """).fetchall()

    data = [{"category": r["category"], "total_amount": float(r["total_amount"]), "count": int(r["count"])} for r in rows]
    summary = f"Summary of credit card spending across {len(data)} active categories."

    return {
        "query": query,
        "route": "sql_only",
        "answer_summary": summary,
        "supporting_data": data,
    }


def analyze_prompt(conn, prompt: str, start_date: str | None = None, end_date: str | None = None) -> dict:
    """
    Backwards-compatible prompt analyzer routing to Tier 1 or Tier 2.
    """
    p = (prompt or "").lower()

    if "monthly" in p:
        return get_monthly_expenses(conn)
    if "macro" in p:
        return get_macro_groups(conn)
    if "sunburst" in p or "category" in p:
        return get_category_sunburst(conn)
    if "installment" in p or "cuota" in p:
        return get_installments(conn)

    return query_insights(conn, prompt)


def _chat_requests_spend_review(query: str) -> bool:
    return any(phrase in query for phrase in (
        "where am i spending", "where i'm spending", "out of the plan", "outside the plan",
        "could be cut", "can be cut", "reduce spending", "cut spending", "where to cut",
        "what should i cut", "donde puedo recortar", "gastos para recortar", "fuera del plan",
    ))


def _answer_spend_review(conn, original_query: str, normalized_query: str) -> dict:
    """Build a macro-group -> category -> description spending review."""
    month = _chat_month_filter(normalized_query)
    where = [
        "account_type = 'tdc'",
        "excluded_from_budget = 0",
        "COALESCE(category, '') != 'Payment'",
        "amount < 0",
    ]
    params: list[str] = []
    if month:
        where.append("strftime('%Y-%m', COALESCE(close_date, date)) = ?")
        params.append(month)

    where_sql = " AND ".join(where)
    rows = conn.execute(
        f"""SELECT COALESCE(macro_group, 'Unknown') AS macro_group,
                   COALESCE(category, 'Other/Uncategorized') AS category,
                   description, currency,
                   ROUND(SUM(ABS(amount)), 2) AS total,
                   COUNT(*) AS count,
                   GROUP_CONCAT(DISTINCT file_name) AS source_files
            FROM transactions
            WHERE {where_sql}
            GROUP BY macro_group, category, description, currency
            ORDER BY CASE macro_group
                         WHEN '10% Leisure & Others' THEN 0
                         WHEN '70% Needs/Fixed Pays' THEN 1
                         WHEN '20% Savings & Invest' THEN 2
                         ELSE 3 END,
                     total DESC""",
        params,
    ).fetchall()

    if not rows:
        period_label = f" in {month}" if month else ""
        answer = f"I couldn't find eligible TDC charges to review{period_label}."
        return {
            "reply": answer,
            "answer": answer,
            "query": original_query,
            "route": "spend_review",
            "filters_applied": {"account_type": "tdc", "month": month},
            "sources": [],
            "supporting_data": {"hierarchy": [], "totals_by_macro_group": []},
        }

    hierarchy: dict[str, dict[str, list[dict]]] = {}
    source_names: set[str] = set()
    totals: dict[tuple[str, str], float] = {}
    counts: dict[tuple[str, str], int] = {}

    for row in rows:
        macro = row["macro_group"]
        category = row["category"]
        description = row["description"] or "Unknown"
        currency = row["currency"]
        total = float(row["total"] or 0)
        count = int(row["count"] or 0)
        hierarchy.setdefault(macro, {}).setdefault(category, []).append({
            "description": description,
            "currency": currency,
            "total": total,
            "count": count,
            "source_files": (row["source_files"] or "").split(",") if row["source_files"] else [],
        })
        key = (macro, currency)
        totals[key] = totals.get(key, 0.0) + total
        counts[key] = counts.get(key, 0) + count
        if row["source_files"]:
            source_names.update(row["source_files"].split(","))

    macro_totals = [
        {"macro_group": macro, "currency": currency, "total": round(total, 2), "count": counts[(macro, currency)]}
        for (macro, currency), total in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]

    first_items = []
    for macro, categories in hierarchy.items():
        for category, items in categories.items():
            for item in items:
                if macro == "10% Leisure & Others":
                    first_items.append((item["total"], macro, category, item))
    first_items.sort(reverse=True, key=lambda entry: entry[0])

    period_label = f" for {month}" if month else " across the stored TDC statements"
    macro_labels = [
        f"{row['macro_group']} — {row['currency']} {row['total']:,.2f}"
        for row in macro_totals[:4]
    ]
    answer = f"I found spending worth reviewing{period_label}. Start with the big groups: " + "; ".join(macro_labels) + "."

    unidentified_count = sum(
        len(items)
        for categories in hierarchy.values()
        for category, items in categories.items()
        if category in {"Other/Uncategorized", "Unknown"}
    )
    answer += f" I highlighted {unidentified_count} unidentified item groups that could affect the monthly budget."

    sources = sorted(source_names)
    review_candidates = []
    seen_candidates = set()
    for macro, categories in hierarchy.items():
        for category, items in categories.items():
            for item in items:
                unidentified = category in {"Other/Uncategorized", "Unknown"}
                discretionary = macro == "10% Leisure & Others"
                if not unidentified and not discretionary:
                    continue
                key = (item["currency"], item["description"])
                if key in seen_candidates:
                    continue
                seen_candidates.add(key)
                review_candidates.append({
                    "description": item["description"],
                    "macro_group": macro,
                    "category": category,
                    "currency": item["currency"],
                    "total": item["total"],
                    "count": item["count"],
                    "unidentified": unidentified,
                    "discretionary": discretionary,
                    "source_files": item["source_files"],
                })

    review_candidates.sort(key=lambda item: (not item["unidentified"], -item["total"]))

    return {
        "reply": answer,
        "answer": answer,
        "query": original_query,
        "route": "spend_review",
        "filters_applied": {"account_type": "tdc", "month": month},
        "sources": sources,
        "supporting_data": {
            "hierarchy": hierarchy,
            "totals_by_macro_group": macro_totals,
            "review_candidates": review_candidates,
        },
        "review_level": "macro_group->category->description",
    }
