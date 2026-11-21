import os
from dotenv import load_dotenv

load_dotenv()

try:
    from google import genai
except ImportError:
    genai = None

MODEL_NAME = "gemini-3.5-flash"
_client = None


def get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        if genai is None:
            raise RuntimeError("google-genai is not installed.")
        _client = genai.Client(api_key=api_key)
    return _client


def get_chat_response(message: str, file_id: str | None = None) -> str:
    if not os.environ.get("GEMINI_API_KEY") or genai is None:
        if file_id:
            return (
                "I received your message. If you would like to process the uploaded statement, "
                "please say 'process it now'."
            )
        return "I received your message. You can ask me about uploaded statements, summaries, or processing commands."

    client = get_client()
    context = ""
    if file_id:
        context = (
            f"A bank statement file with ID {file_id} has been uploaded and is waiting to be processed. "
            "If the user wants to process it, respond with a friendly confirmation and ask if they want the backend to continue."
        )
    prompt = (
        "You are a finance assistant for a bank-statement ingestion application. "
        "Keep answers concise, friendly, and action-oriented. "
        f"{context}"
        f"User: {message}\nAssistant:"
    )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )
    return (response.text or "").strip()


def simple_intent_matches(message: str) -> bool:
    lower = message.lower()
    return any(
        keyword in lower
        for keyword in [
            "process",
            "load it",
            "yes",
            "go ahead",
            "run it",
            "start",
            "process now",
            "do it",
        ]
    )
