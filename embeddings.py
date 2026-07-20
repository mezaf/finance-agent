"""
embeddings.py — local embedding model, no external API calls or cost.
"""

from sentence_transformers import SentenceTransformer

_MODEL_NAME = "all-MiniLM-L6-v2"  # 384-dim, small, fast on CPU
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Lazy-load the model once per process."""
    global _model
    if _model is None:
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def encode_text(text: str) -> list[float]:
    return get_model().encode(text).tolist()


def build_embedding_text(txn: dict) -> str:
    """
    Consistent text representation of a transaction for embedding.
    Keep this format stable — changing it later means re-embedding
    everything already stored, or mixing embedding styles.
    """
    network = f" {txn['card_network']}" if txn.get("card_network") else ""
    installment = f" (installment {txn['installment']})" if txn.get("installment") else ""
    return (
        f"{txn['date']} {txn['bank']}{network} {txn['description']} "
        f"{txn['amount']} {txn['currency']}{installment} — bucket: {txn['bucket']}"
    )