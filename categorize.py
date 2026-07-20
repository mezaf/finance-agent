"""
categorize.py — assigns each transaction to a 20/70/10 bucket:
    savings  (20%) — transfers to investment/broker accounts, fixed-term deposits
    spend    (70%) — recurring living costs: utilities, groceries, transport, debt
    leisure  (10%) — entertainment, dining out, and ALWAYS food delivery

Alpha version: keyword-based rules. Ambiguous cases fall back to 'spend'
and are flagged with low_confidence=True so they can be reviewed manually
rather than silently mis-bucketed.
"""

# Merchant/description keywords are matched case-insensitively, substring match.
# Extend these lists as you see real merchant names in your statements.

FOOD_DELIVERY_KEYWORDS = [
    "rappi", "pedidosya", "pedidos ya",
]

LEISURE_KEYWORDS = [
    "netflix", "spotify", "cine", "hbo", "disney", "restaurant", "resto",
    "bar ", "cerveceria", "steam", "playstation",
] + FOOD_DELIVERY_KEYWORDS

SAVINGS_KEYWORDS = [
    "balanz", "plazo fijo", "fci", "fondo comun", "invercap",
    "transferencia a caja de ahorro propia", "broker",
]

# Everything else defaults to 'spend' (the 70% bucket — recurring/living costs)


def categorize_transaction(description: str, amount: float) -> dict:
    """
    Returns {"bucket": str, "low_confidence": bool}

    Food delivery is checked first and unconditionally forced to 'leisure',
    per the fixed rule — regardless of any other keyword that might also match.
    """
    desc_lower = description.lower()

    if any(kw in desc_lower for kw in FOOD_DELIVERY_KEYWORDS):
        return {"bucket": "leisure", "low_confidence": False}

    if any(kw in desc_lower for kw in SAVINGS_KEYWORDS):
        return {"bucket": "savings", "low_confidence": False}

    if any(kw in desc_lower for kw in LEISURE_KEYWORDS):
        return {"bucket": "leisure", "low_confidence": False}

    # No keyword match — default to spend, but mark for review
    return {"bucket": "spend", "low_confidence": True}