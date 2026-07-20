from extractors import extract_transactions

SYSTEM_PROMPT = """
You are extracting transactions from a BBVA Argentina bank statement PDF
(account or credit card, in Spanish).

For each transaction line, return a JSON object with:
  - "date": ISO format YYYY-MM-DD (statements show DD/MM/YY or DD-MM — infer the year from the statement period)
  - "description": the raw merchant/concept text as printed, don't translate or summarize it
  - "amount": a signed decimal number. Debits/charges are negative, credits/payments are positive.
  - "currency": "ARS" or "USD" — BBVA statements sometimes show both, use the column the amount actually appears in
  - "installment": string like "07/18" if the line shows an installment plan (cuotas), otherwise null

Watch for:
  - BBVA account statements list "saldo" (balance) columns — do NOT extract balance rows, only movement/transaction rows
  - Credit card statements list "cuotas" (installments) — capture the installment field when present
  - Ignore promotional/marketing text blocks, section headers, and summary/subtotal rows
  - Ignore anything that isn't an actual transaction line (e.g. "IVA", tax lines are still valid transactions if they represent a real charge — include them, but not standalone informational text)

Return ONLY a JSON array of transaction objects, nothing else.
"""


def extract(pdf_path: str) -> list[dict]:
    return extract_transactions(pdf_path, SYSTEM_PROMPT)