"""
extractors/__init__.py — shared helper for calling the Claude API with a
PDF statement + a bank-specific system prompt, and parsing the structured
JSON response.

Each bank module (bbva.py, galicia.py, bna.py, santander.py) defines its
own SYSTEM_PROMPT (tailored to that bank's layout) and calls
extract_transactions() with it.
"""

import base64
import json
import os

import anthropic

REQUIRED_FIELDS = [
    "date", "description", "amount", "currency",
]

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ["ANTHROPIC_API_KEY"]  # fail loud if missing
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _pdf_to_base64(pdf_path: str) -> str:
    with open(pdf_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def extract_transactions(pdf_path: str, system_prompt: str) -> list[dict]:
    """
    Sends the PDF + system prompt to Claude, expects a JSON array of
    transaction objects back. Raises ValueError with a clear message if
    the response isn't valid JSON — caller (main.py) is responsible for
    catching this and logging it via db.log_error rather than crashing
    the whole run.
    """
    client = get_client()
    pdf_b64 = _pdf_to_base64(pdf_path)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract every transaction from this statement as a JSON array. "
                            "Respond with ONLY the JSON array — no preamble, no markdown fences, "
                            "no explanation."
                        ),
                    },
                ],
            }
        ],
    )

    raw_text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()

    # Defensive cleanup in case the model wraps output in fences anyway
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        transactions = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Model did not return valid JSON: {e}\nRaw output: {raw_text[:500]}")

    if not isinstance(transactions, list):
        raise ValueError(f"Expected a JSON array of transactions, got: {type(transactions)}")

    for i, txn in enumerate(transactions):
        missing = [f for f in REQUIRED_FIELDS if f not in txn]
        if missing:
            raise ValueError(f"Transaction #{i} missing required fields {missing}: {txn}")

    return transactions