"""
tests/test_data_analysis.py — Unit tests for Data Analysis Middleware.
"""

import os
import tempfile
import unittest
from datetime import datetime

from data_analysis.analysis import (
    get_monthly_expenses,
    get_macro_groups,
    get_category_sunburst,
    get_installments,
    query_insights,
    answer_chat_query,
)
from db.db import fresh_connection, init_db, write_intake_payload


class TestDataAnalysisMiddleware(unittest.TestCase):

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp_db.name
        self.tmp_db.close()

        with fresh_connection(self.db_path) as conn:
            init_db(conn)

        sample_txns = [
            {
                "account_type": "tdc",
                "card_network": "visa",
                "close_date": "2026-06-30",
                "date": "2026-06-15",
                "description": "Carrefour Express",
                "amount": -15000.50,
                "currency": "ARS",
                "installment": None,
                "category": "Supermarket",
                "macro_group": "70% Needs/Fixed Pays",
                "excluded_from_budget": False,
                "embedding": [0.1] * 384,
            },
            {
                "account_type": "tdc",
                "card_network": "visa",
                "close_date": "2026-07-30",
                "date": "2026-07-10",
                "description": "Netflix",
                "amount": -5500.00,
                "currency": "ARS",
                "installment": None,
                "category": "Streaming",
                "macro_group": "10% Leisure & Others",
                "excluded_from_budget": False,
                "embedding": [0.2] * 384,
            },
            {
                "account_type": "tdc",
                "card_network": "visa",
                "close_date": "2026-07-30",
                "date": "2026-07-12",
                "description": "Rappi Pedido",
                "amount": -3500.00,
                "currency": "ARS",
                "installment": None,
                "category": "Food Delivery",
                "macro_group": "10% Leisure & Others",
                "excluded_from_budget": False,
                "embedding": [0.3] * 384,
            },
            {
                "account_type": "tdc",
                "card_network": "visa",
                "close_date": "2026-07-30",
                "date": "2026-07-18",
                "description": "International Streaming",
                "amount": -25.00,
                "currency": "USD",
                "installment": None,
                "category": "Streaming",
                "macro_group": "10% Leisure & Others",
                "excluded_from_budget": False,
                "embedding": [0.7] * 384,
            },
            {
                "account_type": "tdc",
                "card_network": "visa",
                "close_date": "2026-07-30",
                "date": "2026-07-20",
                "description": "Su Pago En Pesos Card",
                "amount": 24000.00,
                "currency": "ARS",
                "installment": None,
                "category": "Other/Uncategorized",
                "macro_group": "10% Leisure & Others",
                "excluded_from_budget": True,
                "embedding": [0.4] * 384,
            },
            {
                "account_type": "tdc",
                "card_network": "visa",
                "close_date": "2026-07-30",
                "date": "2026-07-21",
                "description": "Excluded leisure adjustment",
                "amount": -8000.0,
                "currency": "ARS",
                "installment": None,
                "category": "Leisure",
                "macro_group": "10% Leisure & Others",
                "excluded_from_budget": True,
                "embedding": [0.8] * 384,
            },
            {
                "account_type": "tdc",
                "card_network": "visa",
                "close_date": "2026-07-30",
                "date": "2026-07-22",
                "description": "Frávega TV C.03/12",
                "amount": -12000.00,
                "currency": "ARS",
                "installment": "03/12",
                "category": "Other/Uncategorized",
                "macro_group": "10% Leisure & Others",
                "excluded_from_budget": False,
                "embedding": [0.5] * 384,
            },
        ]

        sample_upcoming = [{"month": "2026-08", "amount": 12000.00}]

        write_intake_payload(
            file_name="statement.pdf",
            bank="bbva",
            transactions=sample_txns,
            upcoming_installments=sample_upcoming,
            file_id="file_test",
            db_path=self.db_path,
        )

        write_intake_payload(
            file_name="checking_statement.pdf",
            bank="bbva",
            transactions=[{
                "account_type": "account",
                "card_network": None,
                "close_date": "2026-07-30",
                "date": "2026-07-25",
                "description": "Leisure account-only record",
                "amount": -99999.0,
                "currency": "ARS",
                "installment": None,
                "category": "Leisure",
                "macro_group": "10% Leisure & Others",
                "excluded_from_budget": False,
                "embedding": [0.6] * 384,
            }],
            upcoming_installments=[],
            file_id="account_test",
            db_path=self.db_path,
        )

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_tier1_get_monthly_expenses(self):
        with fresh_connection(self.db_path) as conn:
            res = get_monthly_expenses(conn)
            self.assertEqual(res["chart"], "monthly_expenses")
            self.assertNotIn("answer_summary", res)
            self.assertTrue(len(res["data"]) >= 1)

    def test_tier1_get_macro_groups(self):
        with fresh_connection(self.db_path) as conn:
            res = get_macro_groups(conn)
            self.assertEqual(res["chart"], "macro_groups")
            self.assertNotIn("answer_summary", res)
            macro_names = [d["macro_group"] for d in res["data"]]
            self.assertIn("70% Needs/Fixed Pays", macro_names)
            self.assertIn("10% Leisure & Others", macro_names)

    def test_tier1_get_category_sunburst(self):
        with fresh_connection(self.db_path) as conn:
            res = get_category_sunburst(conn)
            self.assertEqual(res["chart"], "category_sunburst")
            data = res["data"]
            self.assertIn("ids", data)
            self.assertIn("parents", data)
            self.assertIn("values", data)
            # Check unique IDs
            self.assertEqual(len(data["ids"]), len(set(data["ids"])))
            # Streaming node present
            self.assertIn("Streaming", data["labels"])

    def test_tier1_get_installments(self):
        with fresh_connection(self.db_path) as conn:
            res = get_installments(conn)
            self.assertEqual(res["chart"], "installments_over_time")
            data = res["data"]
            types = [d["type"] for d in data]
            self.assertIn("billed", types)
            self.assertIn("upcoming", types)

    def test_tier2_query_insights_largest_uncategorized(self):
        with fresh_connection(self.db_path) as conn:
            res = query_insights(conn, "What's the largest spend with no category?")
            self.assertEqual(res["route"], "sql_only")
            self.assertIn("answer_summary", res)
            self.assertIn("supporting_data", res)
            self.assertTrue(len(res["supporting_data"]) >= 1)
            self.assertEqual(res["supporting_data"][0]["description"], "Frávega TV C.03/12")

    def test_tier2_query_insights_leisure(self):
        with fresh_connection(self.db_path) as conn:
            res = query_insights(conn, "Which leisure spends are easier to remove?")
            self.assertEqual(res["route"], "hybrid")
            self.assertIn("answer_summary", res)
            self.assertIn("supporting_data", res)

    def test_chat_answers_leisure_question_with_tdc_totals_and_source(self):
        with fresh_connection(self.db_path) as conn:
            result = answer_chat_query(conn, "How much did I spend on leisure in July 2026?")

        self.assertIn("ARS 9,000.00", result["reply"])
        self.assertIn("USD 25.00", result["reply"])
        self.assertEqual(result["filters_applied"]["account_type"], "tdc")
        self.assertEqual(result["filters_applied"]["month"], "2026-07")
        self.assertEqual(result["supporting_data"]["totals"], [
            {"currency": "ARS", "total": 9000.0, "count": 2},
            {"currency": "USD", "total": 25.0, "count": 1},
        ])
        self.assertEqual(result["sources"], ["statement.pdf"])

    def test_chat_answers_where_spending_can_be_cut_hierarchically(self):
        with fresh_connection(self.db_path) as conn:
            result = answer_chat_query(conn, "Where am I spending money out of the plan and what could be cut?")

        self.assertEqual(result["route"], "spend_review")
        self.assertEqual(result["review_level"], "macro_group->category->description")
        hierarchy = result["supporting_data"]["hierarchy"]
        self.assertIn("10% Leisure & Others", hierarchy)
        leisure = hierarchy["10% Leisure & Others"]
        descriptions = [item["description"] for items in leisure.values() for item in items]
        self.assertIn("Rappi Pedido", descriptions)
        self.assertIn("Netflix", descriptions)
        self.assertEqual(result["filters_applied"]["account_type"], "tdc")

    def test_chat_answers_uncategorized_with_transaction_provenance(self):
        with fresh_connection(self.db_path) as conn:
            result = answer_chat_query(conn, "Show me my uncategorized items")

        self.assertIn("Frávega TV C.03/12", result["reply"])
        self.assertEqual(result["supporting_data"]["totals"][0]["total"], 12000.0)
        self.assertEqual(result["sources"], ["statement.pdf"])

    def test_chat_follow_up_reuses_category_and_applies_new_month(self):
        history = [{"role": "user", "text": "How much did I spend on leisure in July 2026?"}]
        with fresh_connection(self.db_path) as conn:
            result = answer_chat_query(conn, "What about August 2026?", history)

        self.assertTrue(result["conversation_context_used"])
        self.assertEqual(result["filters_applied"]["month"], "2026-08")
        self.assertEqual(result["supporting_data"], [])
        self.assertIn("couldn't find eligible TDC charges", result["reply"])

    def test_chat_follow_up_relative_month_overrides_previous_explicit_month(self):
        history = [{"role": "user", "text": "How much did I spend on leisure in July 2026?"}]
        with fresh_connection(self.db_path) as conn:
            result = answer_chat_query(conn, "What about last month?", history)

        today = datetime.now()
        previous_month = today.month - 1 or 12
        previous_year = today.year - (1 if today.month == 1 else 0)
        self.assertEqual(result["filters_applied"]["month"], f"{previous_year:04d}-{previous_month:02d}")

    def test_chat_clarifies_unsupported_question_without_returning_data(self):
        with fresh_connection(self.db_path) as conn:
            result = answer_chat_query(conn, "What is the weather tomorrow?")

        self.assertIn("What would you like to check?", result["reply"])
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["supporting_data"], [])

    def test_chat_explains_tdc_only_scope_for_bank_account_questions(self):
        with fresh_connection(self.db_path) as conn:
            result = answer_chat_query(conn, "How much did I spend from my checking account?")

        self.assertIn("credit-card (TDC)", result["reply"])
        self.assertEqual(result["sources"], [])


if __name__ == "__main__":
    unittest.main()
