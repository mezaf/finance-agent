You are extracting transactions and statement metadata from a Banco Nación Argentina (BNA) statement PDF (credit card or account, in Spanish).

This BNA template has been upgraded and often includes a compact multi-line summary at the top followed by a detailed ledger section. The extraction must read the actual financial content and ignore marketing, legal text, and totals.

Return a single JSON object containing:
- "close_date": ISO date YYYY-MM-DD for the statement closing date.
- "transactions": a JSON array of transaction objects.
- "upcoming_installments": a JSON array of upcoming installments ("cuotas a vencer"), or an empty array if none present.

For each item in "transactions", include:
  - "bank": "bna"
  - "account_type": "account" or "tdc"
  - "close_date": ISO format YYYY-MM-DD (statement close date)
  - "date": ISO format YYYY-MM-DD (infer year from statement period)
  - "description": exact raw merchant/concept text as printed. Preserve installment tags like "C.05/06" or "08/18" unmodified. Do not categorize, translate, or summarize.
  - "amount": signed decimal number (charges negative, payments/credits positive).
  - "currency": "ARS" or "USD".
  - "installment": string like "05/06" or "08/18" if shown, otherwise null.

For each item in "upcoming_installments", include:
  - "month": ISO month YYYY-MM (e.g. "2026-08")
  - "amount": positive decimal number

Important BNA layout patterns to recognize:
- Many upgraded BNA credit-card statements begin with a header summary such as:
  - "RESUMEN CONSOLIDADO"
  - "Cuotas a vencer"
  - "SALDO ANTERIOR"
  - "TOTAL CONSUMOS DEL MES"
  - "PAGO MINIMO"
  - "ESTADO DE CUENTA AL"
- The actual detailed transactions are usually in a section such as:
  - "DETALLE DEL MES"
  - "COMPRAS DEL MES"
  - "CUOTAS DEL MES"
- A detailed row may look like:
  - "08-Jun-26 DLOCAL*RAPPI 00803 6490,00"
  - "16-Nov-25 HIPER RODO 08/18 01921 393160,80"
  - "10-Dic-25 WWW.RODO.COM.AR 07/18 08088 67293,83"
- A row with a "NN/NN" code in the installment field (e.g. "08/18", "07/18") is a financed installment charge and should be extracted as a transaction with `installment` set to that value.
- Summary totals such as:
  - "TOTAL TITULAR"
  - "SALDO ACTUAL"
  - "PAGO MINIMO"
  - "TOTAL CONSUMOS DEL MES"
  - "SUBTOTAL"
  are NOT transactions and must be ignored.
- A payment row like "10-Jun-26 SU PAGO" may appear in the summary section. Keep it only if it appears as a real row in the detailed ledger. Do not treat summary balance or minimum payment labels as transactions.
- Include tax and fee charges when they appear as actual transaction rows (e.g. VAT, commission, IIBB, etc.).
- Do not perform any categorization or classification.

Close date extraction rules:
- Prefer the explicit statement date: a line like "Estado de cuenta al: 02-Jul-26" or "Estado de cuenta al: 30-Jul-26".
- Convert it to ISO YYYY-MM-DD.
- If the statement has both closing and next closing dates, use the actual statement close date, not the next closing date.

Upcoming installments rules:
- Extract "Cuotas a vencer" summary values only if they are presented as a separate upcoming installment table by month.
- Convert amounts to positive decimals and set `month` as `YYYY-MM`.
- If no explicit upcoming installment table exists, return an empty array.

Parsing rules:
- Preserve the exact merchant/concept text as printed. Do not normalize names beyond converting numbers/amount formatting to JSON values.
- Keep installment references exactly as shown (examples: "08/18", "07/18", "C.03/12", "05/06").
- If a decimal amount uses comma as decimal separator, parse it as a decimal number.
- Handle the fact that BNA statements frequently compress spacing and merge fields (for example, concept, coupon number, and amount may appear without clean column separators).

Return ONLY the JSON object, nothing else.
