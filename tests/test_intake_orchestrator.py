"""
tests/test_intake_orchestrator.py — Unit and integration tests for Intake Orchestrator.
"""

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from data_load.bank import identify_bank
from data_load.extractor import extract_statement_data
from data_load.categorize import categorize_transactions, categorize_single_transaction
from data_load.embeddings import normalize_description, encode_text, generate_embeddings_for_transactions
from db.db import write_intake_payload, fresh_connection, init_db, is_file_processed
from data_load.orchestrator import IntakeOrchestrator


class TestTask0BankIdentification(unittest.TestCase):

    @patch("data_load.bank.extract_first_page_text")
    def test_identify_bbva_from_header(self, mock_extract):
        mock_extract.return_value = "Resumen de cuenta BBVA Argentina CUIT 30-50000319-3"
        result = identify_bank("fake_bbva.pdf")
        self.assertEqual(result["bank"], "bbva")
        self.assertEqual(result["file"], "fake_bbva.pdf")

    @patch("data_load.bank.extract_first_page_text")
    def test_identify_galicia_from_header(self, mock_extract):
        mock_extract.return_value = "Banco Galicia Resumen de Tarjeta de Credito"
        result = identify_bank("galicia_statement.pdf")
        self.assertEqual(result["bank"], "galicia")

    @patch("data_load.bank.extract_first_page_text")
    def test_identify_bna_from_header(self, mock_extract):
        mock_extract.return_value = "Banco de la Nación Argentina - Resumen Muestral"
        result = identify_bank("bna.pdf")
        self.assertEqual(result["bank"], "bna")

    @patch("data_load.bank.extract_first_page_text")
    def test_identify_santander_from_header(self, mock_extract):
        mock_extract.return_value = "Santander Río Estado de Cuenta Consolidado"
        result = identify_bank("santander.pdf")
        self.assertEqual(result["bank"], "santander")

    @patch("data_load.bank.extract_first_page_text")
    def test_identify_cencopay_from_header(self, mock_extract):
        mock_extract.return_value = "Cencopay - Estado de cuenta y movimientos del cliente"
        result = identify_bank("cencopay_statement.pdf")
        self.assertEqual(result["bank"], "cencopay")

    @patch("data_load.bank.extract_first_page_text")
    def test_cencopay_prefers_cencopay_over_bna_when_both_are_present(self, mock_extract):
        mock_extract.return_value = (
            "Cencopay SA - Estado de cuenta\n"
            "Cuenta asociada: 30-50001091-2 Mastercard Internacional\n"
            "Movimiento de la cuenta"
        )
        result = identify_bank("cencopay_bna_mixed.pdf")
        self.assertEqual(result["bank"], "cencopay")

    def test_issuer_cuit_disambiguates_competing_bank_names(self):
        cases = {
            "bbva": (
                "Banco BBVA Argentina CUIT Nro. 30-50000319-3; "
                "Banco Galicia, Banco Nación, Nativa Internacional"
            ),
            "galicia": (
                "Resumen CUIT Banco: 30-50000173-5; "
                "Banco Galicia, Banco BBVA, Mastercard Internacional"
            ),
            "bna": (
                "CUIT Entidad: 30-50001091-2 MASTERCARD INTERNACIONAL; "
                "Banco Galicia, BBVA"
            ),
        }
        for expected_bank, header in cases.items():
            with self.subTest(bank=expected_bank), patch(
                "data_load.bank.extract_first_page_text", return_value=header
            ):
                result = identify_bank("statement.pdf")
                self.assertEqual(result["bank"], expected_bank)

    @patch("data_load.bank.extract_first_page_text")
    def test_generic_mastercard_text_does_not_identify_bna(self, mock_extract):
        mock_extract.return_value = "Resumen de tarjeta Mastercard Internacional"
        with self.assertRaisesRegex(ValueError, "Could not confidently identify bank"):
            identify_bank("unknown_statement.pdf")

    @patch("data_load.bank.extract_first_page_text")
    def test_multiple_issuer_cuits_fail_loudly(self, mock_extract):
        mock_extract.return_value = (
            "CUIT Banco: 30-50000173-5 Banco Galicia; "
            "CUIT Entidad: 30-50001091-2"
        )
        with self.assertRaisesRegex(ValueError, "Ambiguous issuer CUITs"):
            identify_bank("mixed_statement.pdf")

    @patch("data_load.bank.extract_first_page_text")
    def test_unknown_bank_fails_loudly(self, mock_extract):
        mock_extract.return_value = "Unknown Header Text Without Identifiers"
        with self.assertRaises(ValueError) as ctx:
            identify_bank("unknown.pdf", filename="unknown.pdf")
        self.assertIn("Could not confidently identify bank", str(ctx.exception))


class TestTask2Categorization(unittest.TestCase):

    def test_food_delivery_forced_to_leisure(self):
        res = categorize_single_transaction("Rappi * Supermercado Promocion")
        self.assertEqual(res["category"], "Food Delivery")
        self.assertEqual(res["macro_group"], "10% Leisure & Others")
        self.assertFalse(res["excluded_from_budget"])

    def test_supermarket_category(self):
        res = categorize_single_transaction("Carrefour Express")
        self.assertEqual(res["category"], "Supermarket")
        self.assertEqual(res["macro_group"], "70% Needs/Fixed Pays")
        self.assertFalse(res["excluded_from_budget"])

    def test_savings_category(self):
        res = categorize_single_transaction("Plazo Fijo Banco Galicia")
        self.assertEqual(res["category"], "Savings")
        self.assertEqual(res["macro_group"], "20% Savings & Invest")

    def test_payment_exclusion(self):
        res = categorize_single_transaction("Su Pago En Pesos Card")
        self.assertTrue(res["excluded_from_budget"])


class TestTask3Embedding(unittest.TestCase):

    def test_description_normalization(self):
        normalized = normalize_description("  CARREFOUR   EXPRESS  C.03/12  ")
        self.assertEqual(normalized, "carrefour express c.03/12")

    def test_encode_text_length(self):
        vector = encode_text("Supermercado Coto")
        self.assertEqual(len(vector), 384)


class TestTask4DatabaseWrite(unittest.TestCase):

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp_db.name
        self.tmp_db.close()
        with fresh_connection(self.db_path) as conn:
            init_db(conn)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_atomic_write_success(self):
        sample_txns = [
            {
                "account_type": "account",
                "card_network": None,
                "close_date": "2026-07-31",
                "date": "2026-07-15",
                "description": "Carrefour Express",
                "amount": -1500.0,
                "currency": "ARS",
                "installment": None,
                "category": "Supermarket",
                "macro_group": "70% Needs/Fixed Pays",
                "excluded_from_budget": False,
                "embedding": [0.1] * 384,
            }
        ]
        sample_installments = [{"month": "2026-08", "amount": 5000.0}]

        res = write_intake_payload(
            file_name="test_statement.pdf",
            bank="bbva",
            transactions=sample_txns,
            upcoming_installments=sample_installments,
            file_id="file_123",
            db_path=self.db_path,
        )

        self.assertEqual(res["status"], "committed")
        self.assertEqual(res["transactions_written"], 1)

        with fresh_connection(self.db_path) as conn:
            self.assertTrue(is_file_processed(conn, "file_123"))
            row = conn.execute("SELECT * FROM transactions WHERE source_file_id = 'file_123'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["description"], "Carrefour Express")
            self.assertEqual(row["category"], "Supermarket")

            inst_row = conn.execute("SELECT * FROM upcoming_installments WHERE source_file_id = 'file_123'").fetchone()
            self.assertIsNotNone(inst_row)
            self.assertEqual(inst_row["amount"], 5000.0)

    def test_duplicate_natural_key_is_inserted_once(self):
        sample_txns = [{
            "account_type": "tdc",
            "card_network": "visa",
            "close_date": "2026-10-31",
            "date": "2026-10-12",
            "description": "NETFLIX.COM",
            "amount": -12500.0,
            "currency": "ARS",
            "installment": None,
            "category": "Streaming",
            "macro_group": "10% Leisure & Others",
            "excluded_from_budget": False,
            "embedding": [0.1] * 384,
        }]

        first = write_intake_payload("first.pdf", "galicia", sample_txns, [], "file_first", self.db_path)
        second = write_intake_payload("second.pdf", "galicia", sample_txns, [], "file_second", self.db_path)

        self.assertEqual(first["transactions_written"], 1)
        self.assertEqual(second["transactions_written"], 0)
        with fresh_connection(self.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) AS count FROM transactions").fetchone()["count"]
            self.assertEqual(count, 1)


class TestIntakeOrchestratorEndToEnd(unittest.TestCase):

    @patch("data_load.orchestrator.identify_bank")
    @patch("data_load.orchestrator.extract_statement_data")
    @patch("data_load.orchestrator.write_intake_payload")
    def test_orchestrator_sequential_steps(self, mock_write, mock_extract, mock_identify):
        mock_identify.return_value = {"file": "statement.pdf", "bank": "bbva"}
        mock_extract.return_value = {
            "close_date": "2026-07-30",
            "transactions": [
                {
                    "date": "2026-07-10",
                    "description": "Rappi Pedido",
                    "amount": -2500.0,
                    "currency": "ARS",
                    "account_type": "account",
                }
            ],
            "upcoming_installments": [],
        }
        mock_write.return_value = {
            "file": "statement.pdf",
            "bank": "bbva",
            "transactions_written": 1,
            "status": "committed",
        }

        orchestrator = IntakeOrchestrator()
        res = orchestrator.process_file("dummy_path/statement.pdf", file_id="id_1")

        self.assertEqual(res["status"], "committed")
        mock_identify.assert_called_once()
        mock_extract.assert_called_once_with("dummy_path/statement.pdf", bank="bbva")
        mock_write.assert_called_once()


if __name__ == "__main__":
    unittest.main()
