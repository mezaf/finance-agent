"""
data_load/embeddings.py — Task 3: Embedding.

Vectorizes transaction descriptions for semantic search.
What gets embedded: description only — normalized (lowercase, stripped noise).
What does NOT get embedded: amount, category, macro_group, bank, account_type, date, close_date.
"""

import re

_MODEL_NAME = "all-MiniLM-L6-v2"  # 384-dim, fast on CPU
_model = None


def get_model():
    """Lazy-load the SentenceTransformer model once per process."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(_MODEL_NAME)
        except ImportError:
            _model = False
    return _model if _model is not False else None


def normalize_description(description: str) -> str:
    """
    Normalizes transaction description string for embedding:
      - lowercase
      - collapse multiple spaces
      - keep merchant identity and installment tags intact
    """
    if not description:
        return ""
    text = description.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def encode_text(text: str) -> list[float]:
    """Generates a 384-float vector from normalized text."""
    normalized = normalize_description(text)
    if not normalized:
        normalized = "unknown"
    
    model = get_model()
    if model is not None:
        vector = model.encode(normalized).tolist()
    else:
        # Fallback dummy zero vector if sentence_transformers package is missing
        vector = [0.0] * 384
        
    return vector


def generate_embeddings_for_transactions(transactions: list[dict]) -> list[dict]:
    """
    Task 3: Embedding.
    
    Generates embedding vectors for descriptions ONLY after Task 2 categorization completes.
    Attaches vector as 'embedding' key on each transaction dictionary.
    """
    processed = []
    for txn in transactions:
        desc = txn.get("description", "")
        vector = encode_text(desc)
        updated_txn = dict(txn)
        updated_txn["embedding"] = vector
        processed.append(updated_txn)
    return processed
