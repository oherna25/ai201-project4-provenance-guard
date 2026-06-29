import os
from dotenv import load_dotenv

load_dotenv()

# Groq
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.3-70b-versatile"

# Confidence fusion weights
LLM_WEIGHT   = 0.60
STYLO_WEIGHT = 0.40

# Classification thresholds
AI_HIGH_THRESHOLD    = 0.80   # >= this → "ai" / "high"
HUMAN_HIGH_THRESHOLD = 0.20   # <= this → "human" / "high"
# anything between → "uncertain"

# Audit log
LOG_PATH = os.path.join(os.path.dirname(__file__), "logs", "audit.jsonl")