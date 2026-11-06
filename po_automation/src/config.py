from pathlib import Path

# Root of the challenge data (adjust if you move files)
_BASE = Path(__file__).parent.parent.parent
DATA_DIR = _BASE / "challenge_data" / "FDE Challenge-4th stage"

EMAILS_DIR    = DATA_DIR / "emails"
QUOTES_DIR    = DATA_DIR / "quotes"
MASTER_DATA   = DATA_DIR / "master_data.json"

DB_PATH       = Path(__file__).parent.parent / "procurement.db"
PO_API_URL    = "http://127.0.0.1:8080/purchase-orders"

# Ollama model — change to "llama3.1" or "mistral" if you pulled a different one
OLLAMA_MODEL = "llama3.2"

# FX rates are in master_data.json; these are fallback defaults
FX_TO_CHF = {"CHF": 1.0, "EUR": 0.96, "USD": 0.88, "GBP": 1.13}
