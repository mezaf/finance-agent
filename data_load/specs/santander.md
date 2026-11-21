You are extracting transactions and statement metadata from a Banco Santander Argentina consolidated statement PDF (which may contain checking/savings account sections AND credit card sections).

Return a single JSON object containing:
- "close_date": ISO date YYYY-MM-DD for the statement closing date.
- "transactions": a JSON array of transaction objects.
- "upcoming_installments": a JSON array of upcoming installments ("cuotas a vencer"), or an empty array if none present.

For each item in "transactions", include:
  - "bank": "santander"
  - "account_type": "account" (for checking/savings) or "tdc" (for credit card sections)
  - "card_network": "visa" or "master" if credit card section, otherwise null
  - "close_date": ISO format YYYY-MM-DD (statement close date)
  - "date": ISO format YYYY-MM-DD (infer year from statement period)
  - "description": exact raw merchant/concept text as printed. Preserve installment tags unmodified. Do not categorize, translate, or summarize.
  - "amount": signed decimal number (debits/charges negative, credits/payments positive).
  - "currency": "ARS" or "USD".
  - "installment": string like "02/06" if shown, otherwise null.

For each item in "upcoming_installments", include:
  - "month": ISO month YYYY-MM (e.g. "2026-08")
  - "amount": positive decimal number

Extraction rules:
- Santander statements often consolidate multiple product sections (checking/savings account and credit cards). Disambiguate per transaction via "account_type" and "card_network".
- Skip balance/summary/subtotal rows within each section.
- Include tax charges (IVA, IIBB) as valid transactions.
- Do NOT perform any categorization or classification.

Return ONLY the JSON object, nothing else.
