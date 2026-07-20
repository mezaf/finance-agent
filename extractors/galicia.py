from extractors import extract_transactions

SYSTEM_PROMPT = """
You are extracting transactions from a Banco Galicia Argentina credit card
statement PDF (Visa or Master, in Spanish).

For each transaction line, return a JSON object with:
  - "date": ISO format YYYY-MM-DD (infer the year from the statement period)
  - "description": the raw merchant/concept text as printed, don't translate or summarize it
  - "amount": a signed decimal number. Charges are negative, payments/credits are positive.
  - "currency": "ARS" or "USD"
  - "installment": string like "03/12" if shown, otherwise null

Watch for:
  - Galicia statements are typically verbose with promotional/marketing content interleaved
    between transaction sections — skip all promotional blocks entirely, extract only the
    actual movement/transaction table rows
  - "Resumen anterior" / previous balance carried forward is NOT a transaction — skip it
  - Watch for duplicate listing of the same purchase across "consumos del periodo" and
    installment breakdown sections — extract each distinct transaction line only once
  - Interest charges ("intereses") and administrative fees are real transactions — include them

Return ONLY a JSON array of transaction objects, nothing else.
"""


def extract(pdf_path: str) -> list[dict]:
    return extract_transactions(pdf_path, SYSTEM_PROMPT)