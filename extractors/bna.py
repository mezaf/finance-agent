from extractors import extract_transactions

SYSTEM_PROMPT = """
You are extracting transactions from a Banco Nación Argentina (BNA) credit
card statement PDF (Master, in Spanish).

For each transaction line, return a JSON object with:
  - "date": ISO format YYYY-MM-DD (infer the year from the statement period)
  - "description": the raw merchant/concept text as printed, don't translate or summarize it
  - "amount": a signed decimal number. Charges are negative, payments/credits are positive.
  - "currency": "ARS" or "USD"
  - "installment": string like "05/06" if shown, otherwise null

Watch for:
  - BNA statements include a detailed installment schedule table ("plan de cuotas") —
    extract each installment as its own transaction line with its installment field set,
    do not collapse a multi-installment purchase into a single row
  - Distinguish between the current period's new charges and the running installment
    balances from prior purchases — both are valid transactions, but avoid double-counting
    a purchase that appears both in "resumen de cuotas" and "detalle de consumos"
  - Skip minimum payment / total balance summary rows — these are not transactions

Return ONLY a JSON array of transaction objects, nothing else.
"""


def extract(pdf_path: str) -> list[dict]:
    return extract_transactions(pdf_path, SYSTEM_PROMPT)