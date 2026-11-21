# Chat Accuracy Checklist

Run the automated checks with `python -m unittest tests.test_data_analysis tests.test_intake_orchestrator`.

## Automated Coverage

- Leisure totals include eligible TDC charges only and exclude checking-account records.
- Payments and transactions marked `excluded_from_budget` do not inflate expense totals.
- Month-specific questions filter by statement close month, falling back to transaction date.
- Uncategorized answers return the matching category and source statement filename.
- Follow-up questions reuse the previous category and apply a newly specified month.
- Empty result sets return a clear response without inventing values or sources.
- Each currency is totaled separately.

## Manual Acceptance Checks

- Ask "How much did I spend on leisure in July 2026?" and compare the total with the July TDC rows in SQLite.
- Ask "Show me my uncategorized items" and verify each description, amount, and source filename against its statement.
- Ask a follow-up such as "What about August 2026?" and confirm the category carries over but the month changes.
- Ask about checking-account spending and confirm the answer remains limited to TDC data.
- Refresh the page and confirm the conversation transcript returns, while a new question is answered from a fresh database query.
- Upload a PDF and confirm the existing upload/processing flow remains separate from ordinary chat messages.
- Temporarily remove or rename a source PDF after ingestion; confirm answers still cite the stored source filename and do not claim to reopen the PDF.
- Ask an unsupported or ambiguous question and confirm the assistant requests a more specific category or period instead of fabricating a number.