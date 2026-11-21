"""Data loading package for statement ingestion and orchestration."""

from data_load.orchestrator import IntakeOrchestrator, run_intake
from data_load.bank import identify_bank
from data_load.extractor import extract_statement_data
from data_load.categorize import categorize_transactions, categorize_single_transaction
from data_load.embeddings import generate_embeddings_for_transactions, encode_text

__all__ = [
    "IntakeOrchestrator",
    "run_intake",
    "identify_bank",
    "extract_statement_data",
    "categorize_transactions",
    "categorize_single_transaction",
    "generate_embeddings_for_transactions",
    "encode_text",
]
