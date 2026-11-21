"""
data_load/categorize.py — Task 2: Categorization.

Assigns category + budget macro group to every transaction.
Deterministic, keyword-based — not inferred by the LLM.

Categories → Macro Group mapping (20/70/10 principle):
  70% Needs/Fixed Pays : Supermarket, Utilities, Insurance
  20% Savings & Invest : Savings, Investment
  10% Leisure & Others : Leisure, Streaming, Food Delivery, Other/Uncategorized

Fixed Rule:
  Food delivery (Rappi, PedidosYa, etc.) is ALWAYS Leisure (Food Delivery category),
  never Needs — regardless of framing.

Exclusion:
  Transactions matching "Payment" keywords (e.g. "su pago", "pago tarjeta") are tagged
  excluded_from_budget: true.
"""

MACRO_GROUP_NEEDS = "70% Needs/Fixed Pays"
MACRO_GROUP_SAVINGS = "20% Savings & Invest"
MACRO_GROUP_LEISURE = "10% Leisure & Others"

CATEGORY_TO_MACRO_GROUP = {
    "Supermarket": MACRO_GROUP_NEEDS,
    "Utilities": MACRO_GROUP_NEEDS,
    "Insurance": MACRO_GROUP_NEEDS,
    "Savings": MACRO_GROUP_SAVINGS,
    "Investment": MACRO_GROUP_SAVINGS,
    "Food Delivery": MACRO_GROUP_LEISURE,
    "Streaming": MACRO_GROUP_LEISURE,
    "Leisure": MACRO_GROUP_LEISURE,
    "Other/Uncategorized": MACRO_GROUP_LEISURE,
}

PAYMENT_KEYWORDS = [
    "su pago",
    "pago tarjeta",
    "cr.rg",
    "tu pago",
    "pago de tarjeta",
]

FOOD_DELIVERY_KEYWORDS = [
    "rappi",
    "pedidosya",
    "pedidos ya",
    "ubereats",
    "uber eats",
]

STREAMING_KEYWORDS = [
    "netflix",
    "spotify",
    "hbo",
    "disney",
    "youtube",
    "paramount",
    "directv",
    "flow",
    "star+",
    "star plus",
    "starplus",
    "prime video",
    "primevideo",
    "apple.com/bill",
]

SUPERMARKET_KEYWORDS = [
    "carrefour",
    "coto",
    "supermayorista",
    "jumbo",
    "disco",
    "vea",
    "dia argentina",
    "supermercado",
    "chango mas",
    "changomas",
]

UTILITIES_KEYWORDS = [
    "edenor",
    "edesur",
    "metrogas",
    "aysa",
    "abl",
    "personal",
    "telecom",
    "movistar",
    "claro",
    "leet",
    "farmacity",
    "tuenti",
    "axion"
]

INSURANCE_KEYWORDS = [
    "seguro",
    "seguros",
    "la caja",
    "sancor",
    "allianz",
    "mapfre",
    "swiss medical",
    "galeno",
    "omint",
]

SAVINGS_KEYWORDS = [
    "plazo fijo",
    "fci",
    "fondo comun",
    "transferencia a caja de ahorro propia",
]

INVESTMENT_KEYWORDS = [
    "balanz",
    "invercap",
    "broker",
    "bull market",
    "iol",
    "invertironline",
    "interna",
    "toyota",
]

LEISURE_KEYWORDS = [
    "cine",
    "restaurant",
    "resto",
    "bar ",
    "cerveceria",
    "steam",
    "playstation",
    "kahwa",
    "google",
    "mi gusto",
    "migusto",
    "patisserie",
    "tienda de cafe",
    "mc donalds",
    "mcdonalds",
    "burger king",
    "starbucks",
    "cafeteria",
    "violetas",
]


def categorize_single_transaction(description: str) -> dict:
    """
    Categorizes a single description string using fixed keyword lookup.
    Returns:
      {
        "category": str,
        "macro_group": str,
        "excluded_from_budget": bool
      }
    """
    desc_lower = (description or "").lower()

    is_payment = any(kw in desc_lower for kw in PAYMENT_KEYWORDS)

    # 1. Food Delivery rule (always Leisure / Food Delivery)
    if any(kw in desc_lower for kw in FOOD_DELIVERY_KEYWORDS):
        category = "Food Delivery"
    # 2. Payments exclusion match
    elif is_payment:
        category = "Other/Uncategorized"
    # 3. Utilities
    elif any(kw in desc_lower for kw in UTILITIES_KEYWORDS):
        category = "Utilities"
    # 4. Insurance
    elif any(kw in desc_lower for kw in INSURANCE_KEYWORDS):
        category = "Insurance"
    # 5. Supermarket
    elif any(kw in desc_lower for kw in SUPERMARKET_KEYWORDS):
        category = "Supermarket"
    # 6. Streaming
    elif any(kw in desc_lower for kw in STREAMING_KEYWORDS):
        category = "Streaming"
    # 7. Savings
    elif any(kw in desc_lower for kw in SAVINGS_KEYWORDS):
        category = "Savings"
    # 8. Investment
    elif any(kw in desc_lower for kw in INVESTMENT_KEYWORDS):
        category = "Investment"
    # 9. Leisure
    elif any(kw in desc_lower for kw in LEISURE_KEYWORDS):
        category = "Leisure"
    else:
        category = "Other/Uncategorized"

    macro_group = CATEGORY_TO_MACRO_GROUP[category]

    return {
        "category": category,
        "macro_group": macro_group,
        "excluded_from_budget": is_payment,
    }


def categorize_transactions(transactions: list[dict]) -> list[dict]:
    """
    Task 2: Categorization.
    
    Applies deterministic keyword rules to each transaction in the list.
    Returns updated transaction dicts with 'category', 'macro_group', and 'excluded_from_budget'.
    """
    categorized = []
    for txn in transactions:
        result = categorize_single_transaction(txn.get("description", ""))
        updated_txn = dict(txn)
        updated_txn["category"] = result["category"]
        updated_txn["macro_group"] = result["macro_group"]
        updated_txn["excluded_from_budget"] = result["excluded_from_budget"]
        categorized.append(updated_txn)
    return categorized
