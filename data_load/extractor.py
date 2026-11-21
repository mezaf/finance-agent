"""
data_load/extractor.py — Task 1: Extraction.

Converts the raw PDF into a normalized statement extraction payload containing:
  - close_date
  - transactions[]
  - upcoming_installments[]
"""

import base64
import json
import os
import re

from google import genai
from google.genai import types

MODEL_NAME = "gemini-3.5-flash"
SPEC_DIR = os.path.join(os.path.dirname(__file__), "specs")

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is missing")
        _client = genai.Client(api_key=api_key)
    return _client


def _load_bank_prompt(bank: str) -> str:
    bank_file = os.path.join(SPEC_DIR, f"{bank.lower()}.md")
    if not os.path.exists(bank_file):
        raise FileNotFoundError(f"Bank spec file not found for '{bank}': {bank_file}")
    with open(bank_file, "r", encoding="utf-8") as f:
        return f.read().strip()


def extract_statement_data(pdf_path: str, bank: str) -> dict:
    """
    Task 1: Extraction.
    
    Loads specs/<bank>.md and extracts transactions + upcoming_installments + close_date.
    Returns:
    {
        "close_date": "YYYY-MM-DD",
        "transactions": [...],
        "upcoming_installments": [...]
    }
    """
    if not bank:
        raise ValueError("Bank identifier must be provided for Task 1 Extraction")

    system_prompt = _load_bank_prompt(bank)
    client = get_client()

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    instruction = (
        f"{system_prompt}\n\n"
        "Extract statement data matching the requested schema as a single JSON object. "
        "Respond with ONLY valid JSON — no preamble, no markdown fences, no extra text."
    )

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                instruction,
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            ],
        )
        raw_text = (response.text or "").strip()
    except Exception:
        pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                instruction,
                {"inline_data": {"mime_type": "application/pdf", "data": pdf_b64}},
            ],
        )
        raw_text = (response.text or "").strip()

    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.IGNORECASE)
        raw_text = re.sub(r"\s*```$", "", raw_text)
        raw_text = raw_text.strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Task 1 Extraction model did not return valid JSON: {e}\nRaw output: {raw_text[:500]}")

    if isinstance(data, list):
        data = {"transactions": data, "upcoming_installments": []}

    if not isinstance(data, dict):
        raise ValueError(f"Expected Task 1 extraction JSON object, got: {type(data)}")

    transactions = data.get("transactions", [])
    if not isinstance(transactions, list):
        raise ValueError(f"Expected 'transactions' array in extraction output, got: {type(transactions)}")

    upcoming_installments = data.get("upcoming_installments", [])
    if not isinstance(upcoming_installments, list):
        upcoming_installments = []

    close_date = data.get("close_date")

    normalized_txns = []
    required_fields = ["date", "description", "amount"]

    for i, txn in enumerate(transactions):
        if not isinstance(txn, dict):
            raise ValueError(f"Transaction #{i} is not a dict: {txn}")
        
        missing = [f for f in required_fields if f not in txn or txn[f] is None]
        if missing:
            raise ValueError(f"Transaction #{i} missing required fields {missing}: {txn}")

        txn_close_date = txn.get("close_date") or close_date

        normalized_txns.append({
            "bank": bank.lower(),
            "account_type": (txn.get("account_type") or "account").lower(),
            "card_network": txn.get("card_network").lower() if txn.get("card_network") else None,
            "close_date": txn_close_date,
            "date": str(txn["date"]),
            "description": str(txn["description"]),
            "amount": float(txn["amount"]),
            "currency": str(txn.get("currency") or "ARS").upper(),
            "installment": str(txn["installment"]) if txn.get("installment") else None,
        })

    normalized_installments = []
    for inst in upcoming_installments:
        if isinstance(inst, dict) and "month" in inst and "amount" in inst:
            normalized_installments.append({
                "month": str(inst["month"]),
                "amount": float(inst["amount"]),
            })

    return {
        "close_date": close_date,
        "transactions": normalized_txns,
        "upcoming_installments": normalized_installments,
    }
