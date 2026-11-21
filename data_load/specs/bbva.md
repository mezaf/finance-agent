You are extracting transactions and statement metadata from a BBVA Argentina bank statement PDF (account or credit card, in Spanish).

Return a single JSON object containing:
- "close_date": ISO date YYYY-MM-DD for the statement closing date (cierre).
- "transactions": a JSON array of transaction objects.
- "upcoming_installments": a JSON array of upcoming installments ("cuotas a vencer"), or an empty array if none present.

For each item in "transactions", include:
  - "bank": "bbva"
  - "account_type": "account" or "tdc" (credit card)
  - "close_date": ISO format YYYY-MM-DD (same as statement close date)
  - "date": ISO format YYYY-MM-DD (infer year from statement period)
  - "description": exact raw merchant/concept text as printed. Preserve installment tags like "C.03/12" unmodified. Do not categorize, translate, or summarize.
  - "amount": signed decimal number (debits/charges negative, credits/payments positive).
  - "currency": "ARS" or "USD".
  - "installment": string like "03/12" if shown, otherwise null.

For each item in "upcoming_installments", include:
  - "month": ISO month YYYY-MM (e.g. "2026-08")
  - "amount": positive decimal number

Extraction rules:
- Ignore balance/"saldo" rows, promotional blocks, section headers, and subtotal rows.
- Include real tax charges (IVA, IIBB) as valid transactions.
- Do NOT perform any categorization or classification.

Return ONLY the JSON object, nothing else.
