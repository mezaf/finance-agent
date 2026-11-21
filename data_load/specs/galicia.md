You are extracting transactions and statement metadata from a Banco Galicia Argentina statement PDF (Visa, Master, or account, in Spanish).

Return a single JSON object containing:
- "close_date": ISO date YYYY-MM-DD for the statement closing date.
- "transactions": a JSON array of transaction objects.
- "upcoming_installments": a JSON array of upcoming installments ("cuotas a vencer"), or an empty array if none present.

For each item in "transactions", include:
  - "bank": "galicia"
  - "account_type": "account" or "tdc"
  - "close_date": ISO format YYYY-MM-DD (statement close date)
  - "date": ISO format YYYY-MM-DD (infer year from statement period)
  - "description": exact raw merchant/concept text as printed. Preserve installment tags unmodified. Do not categorize, translate, or summarize.
  - "amount": signed decimal number (charges negative, payments/credits positive).
  - "currency": "ARS" or "USD".
  - "installment": string like "03/12" if shown, otherwise null.

For each item in "upcoming_installments", include:
  - "month": ISO month YYYY-MM (e.g. "2026-08")
  - "amount": positive decimal number

Extraction rules:
- Skip promotional content, summary headers, and previous balance ("resumen anterior") rows.
- Include interest charges ("intereses") and tax lines (IVA, IIBB) as valid transactions.
- Do NOT perform any categorization or classification.

Return ONLY the JSON object, nothing else.
