"""
data_load/orchestrator.py — Intake Orchestrator.

Processes bank statement PDFs through five strictly sequential steps:
  TASK 0: Bank Identification
  TASK 1: Extraction
  TASK 2: Categorization
  TASK 3: Embedding
  TASK 4: Database Write

Rules:
  - Do not skip, merge, or parallelize steps.
  - Each step's output is the next step's only input.
  - Fail loud, not silent.
"""

import os
from data_load.bank import identify_bank
from data_load.extractor import extract_statement_data
from data_load.categorize import categorize_transactions
from data_load.embeddings import generate_embeddings_for_transactions
from db.db import write_intake_payload


class IntakeOrchestrator:
    """Intake Orchestrator enforcing 5 strictly sequential processing tasks."""

    def process_file(self, pdf_path: str, file_id: str | None = None, filename: str | None = None) -> dict:
        target_filename = filename or os.path.basename(pdf_path)

        # TASK 0: Bank Identification
        task0_output = identify_bank(pdf_path, filename=target_filename)
        bank = task0_output["bank"]

        # TASK 1: Extraction
        task1_output = extract_statement_data(pdf_path, bank=bank)
        transactions = task1_output.get("transactions", [])
        upcoming_installments = task1_output.get("upcoming_installments", [])

        # TASK 2: Categorization
        task2_output = categorize_transactions(transactions)

        # TASK 3: Embedding
        task3_output = generate_embeddings_for_transactions(task2_output)

        # TASK 4: Database Write
        task4_output = write_intake_payload(
            file_name=target_filename,
            bank=bank,
            transactions=task3_output,
            upcoming_installments=upcoming_installments,
            file_id=file_id or target_filename,
        )

        return task4_output


def run_intake(pdf_path: str, file_id: str | None = None, filename: str | None = None) -> dict:
    """Helper function to run the Intake Orchestrator on a single PDF statement."""
    orchestrator = IntakeOrchestrator()
    return orchestrator.process_file(pdf_path, file_id=file_id, filename=filename)
