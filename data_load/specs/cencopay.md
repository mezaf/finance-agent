You are extracting transactions and statement metadata from a Cencopay statement PDF (a fintech/payment platform statement, often in Spanish or English).

Return a single JSON object containing:
- "close_date": ISO date YYYY-MM-DD for the statement closing date.
- "transactions": a JSON array of transaction objects.
- "upcoming_installments": a JSON array of upcoming installments, or an empty array if none present.

For each item in "transactions", include:
  - "bank": "cencopay"
  - "account_type": "account" or "tdc"
  - "close_date": ISO format YYYY-MM-DD (statement close date)
  - "date": ISO format YYYY-MM-DD (infer year from statement period)
  - "description": exact raw merchant/concept text as printed. Preserve reference codes, installment references, and labels exactly as shown. Do not categorize, translate, or summarize.
  - "amount": signed decimal number (charges negative, payments/credits positive).
  - "currency": "ARS" or "USD".
  - "installment": string like "03/12" if shown, otherwise null.

For each item in "upcoming_installments", include:
  - "month": ISO month YYYY-MM (e.g. "2026-08")
  - "amount": positive decimal number

Important Cencopay layout patterns to recognize:
- Cencopay statements are often ledger or settlement exports, not classic bank statement layouts.
- The header may include a business name, account identifier, statement period, and closing date.
- Transactions usually appear in a table with date, description, reference, and amount.
- Common patterns include entries like:
  - "2026-07-01 PAYPAL *XYZ  -4500"
  - "2026-07-02 TRANSFERENCIA CLIENTE 15000"
  - "2026-07-05 COMISIÓN  -350"
- A statement may contain one or more sections such as: "MOVIMIENTOS", "OPERACIONES", "DETAIL", "HISTORIAL", or "ACTIVITY".
- Some rows are summary totals, balances, fees, and settlement figures; ignore those.
- Ignore lines such as: totals, opening balance, closing balance, available balance, account summary, net settlement, page numbers, and legal footers.
- Keep real transaction rows even if they involve fees, commissions, taxes, reimbursements, chargebacks, settlements, or transfers.
- If the statement includes installment-like references (e.g. a plan, payment cycle, or installment code), preserve them in the exact text and set "installment" to that value.
- If the statement is a payment/settlement report, include real movement rows but ignore aggregate totals and reconciliation summaries.

Close date extraction rules:
- Prefer the explicit statement closing date if present, such as “Statement period”, “Periodo”, “Cierre”, “Fecha de cierre”, or similar.
- Convert it to ISO YYYY-MM-DD.
- If only a statement period range is present, use the closing date from that range.

Parsing rules:
- Preserve the raw merchant or concept label exactly as printed. Do not invent or normalize names beyond converting numeric formatting into JSON values.
- If a decimal amount uses comma as decimal separator, parse it to a number.
- If the description and amount are in separate columns, reconstruct the description exactly as printed.
- If a row is clearly a summary or reconciliation line, skip it.
- Do not perform any categorization or classification.

Return ONLY the JSON object, nothing else.
