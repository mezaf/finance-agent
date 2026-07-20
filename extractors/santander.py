from extractors import extract_transactions

# Santander is the one exception to the filename-driven account_type/card_network
# pattern: a single santander_statement.pdf contains ALL products (checking account,
# Visa, Master, etc.) in one file. So unlike the other banks, THIS extractor must
# also identify account_type/card_network per transaction, since main.py can't
# infer it from the filename alone.

SYSTEM_PROMPT = """
You are extracting transactions from a Banco Santander Argentina consolidated
statement PDF. This single PDF contains MULTIPLE products (e.g. a checking/savings
account section AND one or more credit card sections — Visa and/or Master),
each presented as its own section with its own transaction table, in Spanish.

First, identify each distinct product section in the document. Then, for every
transaction line across ALL sections, return a JSON object with:
  - "date": ISO format YYYY-MM-DD (infer the year from the statement period)
  - "description": the raw merchant/concept text as printed, don't translate or summarize it
  - "amount": a signed decimal number. Debits/charges are negative, credits/payments are positive.
  - "currency": "ARS" or "USD"
  - "installment": string like "02/06" if shown, otherwise null
  - "account_type": "account" if this line came from the checking/savings account
        section, or "tdc" if it came from a credit card section
  - "card_network": "visa" or "master" if this line came from a credit card section,
        otherwise null (for account-section transactions)

Watch for:
  - Do not merge transactions from different sections together — every transaction
    must correctly reflect which product section it came from via account_type/card_network
  - Skip balance/summary/subtotal rows within each section
  - If the statement has more than one credit card (e.g. both Visa and Master), keep
    their transactions separate using the card_network field — never guess, only use
    "visa"/"master" if explicitly labeled in that section's header

Return ONLY a JSON array of transaction objects, nothing else.
"""


def extract(pdf_path: str) -> list[dict]:
    return extract_transactions(pdf_path, SYSTEM_PROMPT)