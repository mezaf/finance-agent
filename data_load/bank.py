"""
data_load/bank.py — Task 0: Bank Identification.

Determines which bank issued an uploaded PDF statement using deterministic
pattern matching on the first page's text / header and account metadata.
No LLM inference or guessing.
"""

import os
import re
from pypdf import PdfReader


def normalize_pattern(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


# Known bank identifier patterns for Argentine bank statements
BANK_PATTERNS = {
    "bbva": [
        "bbva",
        "banco bilbao vizcaya",
        "bbva argentina",
        "cuit 30-50000319-3",
        "30500003193",
    ],
    "galicia": [
        "banco galicia",
        "banco de galicia",
        "galicia",
        "cuit 30-50000173-5",
        "30500001735",
    ],
    "bna": [
        "banco nacion",
        "banco nación",
        "bna",
        "banco de la nacion argentina",
        "banco de la nación argentina",
        "cuit 30-50001091-2",
        "30500010912",
        "nativa internacional",
        "30-50001091-2",
    ],
    "santander": [
        "santander",
        "santander rio",
        "santander río",
        "banco santander",
        "cuit 30-50000845-4",
        "30500008454",
    ],
    "cencopay": [
        "cencopay",
        "cenco pay",
        "cen co pay",
        "cencopay sa",
        "cencopay s.a.",
        "cencopay s.a",
        "cencopay payment",
        "cencopay settlement",
        "cencopay movimientos",
        "cencopay estados de cuenta",
        "cencodev",
    ],
}

BANK_CUITS = {
    "bbva": "30-50000319-3",
    "galicia": "30-50000173-5",
    "bna": "30-50001091-2",
    "santander": "30-50000845-4",
}


def extract_first_page_text(pdf_path: str) -> str:
    """Extract only page one, where the statement issuer is identified."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    try:
        reader = PdfReader(pdf_path)
        if len(reader.pages) == 0:
            return ""

        return reader.pages[0].extract_text() or ""
    except Exception as e:
        raise ValueError(f"Failed to read PDF file '{pdf_path}': {e}")


def identify_bank(pdf_path: str, filename: str | None = None) -> dict:
    """
    Task 0: Bank Identification.
    
    Determines which bank issued each uploaded PDF via deterministic pattern match.
    Returns: { "file": filename, "bank": bank_name }
    
    Rule: If no bank can be confidently identified, stop and raise ValueError.
    Do NOT guess or fall back to a default extractor.
    """
    target_filename = filename or os.path.basename(pdf_path)
    text = extract_first_page_text(pdf_path)
    normalized_text = normalize_pattern(text)

    bank_hits = {bank_key: [] for bank_key in BANK_PATTERNS}
    for bank_key, patterns in BANK_PATTERNS.items():
        for pattern in patterns:
            if normalize_pattern(pattern) in normalized_text:
                bank_hits[bank_key].append(pattern)

    matched_banks = {bank_key for bank_key, hits in bank_hits.items() if hits}

    # Strong identifiers outweigh generic account/card markers. This prevents a
    # Cencopay statement from being rejected when a BNA-issued card number appears in
    # the account metadata, while still allowing real BNA statements to match.
    if "cencopay" in matched_banks:
        explicit_cencopay = any(
            normalize_pattern(pattern) in normalized_text
            for pattern in [
                "cencopay",
                "cenco pay",
                "cen co pay",
                "cencopay sa",
                "cencopay s.a.",
                "cencopay payment",
                "cencopay settlement",
                "cencopay movimientos",
                "cencopay estados de cuenta",
            ]
        )
        if explicit_cencopay:
            return {"file": target_filename, "bank": "cencopay"}

    # Issuer CUITs are stronger evidence than bank or card names mentioned in text.
    cuit_matches = {
        bank_key
        for bank_key, cuit in BANK_CUITS.items()
        if normalize_pattern(cuit) in normalized_text
    }
    if len(cuit_matches) == 1:
        return {"file": target_filename, "bank": cuit_matches.pop()}
    if len(cuit_matches) > 1:
        raise ValueError(
            f"Ambiguous issuer CUITs for '{target_filename}': matched multiple banks {sorted(cuit_matches)}"
        )

    # If header text pattern fails or is empty, try exact prefix/keyword match on filename
    if not matched_banks and target_filename:
        lower_name = normalize_pattern(target_filename)
        for bank_key in BANK_PATTERNS:
            if normalize_pattern(bank_key) in lower_name:
                matched_banks.add(bank_key)

    if len(matched_banks) == 1:
        detected_bank = matched_banks.pop()
        return {
            "file": target_filename,
            "bank": detected_bank,
        }

    if len(matched_banks) > 1:
        if "cencopay" in matched_banks and any(
            phrase in normalized_text
            for phrase in [
                "cencopay",
                "cenco pay",
                "cencopay sa",
                "cencopay settlement",
                "cencopay movimientos",
                "estado de cuenta cencopay",
            ]
        ):
            return {"file": target_filename, "bank": "cencopay"}
        raise ValueError(
            f"Ambiguous bank identification for '{target_filename}': matched multiple banks {list(matched_banks)}"
        )

    raise ValueError(
        f"Could not confidently identify bank for file '{target_filename}'. No deterministic bank signature matched."
    )
