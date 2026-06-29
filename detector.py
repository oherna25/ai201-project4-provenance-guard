"""
detector.py — Signal 1: LLM classifier via Groq.

Sends text to llama-3.3-70b-versatile and asks for:
  - verdict: "human" | "ai"
  - raw_confidence: 0.0–1.0

Score direction: llm_score = raw_confidence when verdict is "ai",
                             1.0 - raw_confidence when verdict is "human".
So 0.0 always = confident human, 1.0 always = confident AI.
"""

import json
import re

from groq import Groq

from config import GROQ_API_KEY, GROQ_MODEL

_client = Groq(api_key=GROQ_API_KEY)

_SYSTEM = """You are an expert at distinguishing human-written text from AI-generated text.
Analyze the text provided by the user and respond with ONLY a JSON object — no markdown fences,
no explanation — in exactly this format:
{"verdict": "human" | "ai", "raw_confidence": <float 0.0-1.0>}

raw_confidence is how confident you are in the verdict (0.5 = unsure, 1.0 = certain).
"""


def _parse_response(raw: str) -> tuple[str, float]:
    """Extract (verdict, raw_confidence) from the model's reply."""
    # Strip markdown fences if present
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    data = json.loads(cleaned)
    verdict = str(data.get("verdict", "")).lower()
    if verdict not in ("human", "ai"):
        verdict = "ai"
    raw_confidence = float(data.get("raw_confidence", 0.5))
    raw_confidence = max(0.0, min(1.0, raw_confidence))
    return verdict, raw_confidence


def classify(text: str) -> float:
    """
    Return llm_score ∈ [0, 1] where:
      0.0 = confident human
      1.0 = confident AI
    Raises RuntimeError if Groq is unreachable.
    """
    try:
        response = _client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0.1,
            max_tokens=64,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": text},
            ],
        )
        raw = response.choices[0].message.content or ""
        verdict, raw_confidence = _parse_response(raw)
        if verdict == "ai":
            return raw_confidence
        else:
            return 1.0 - raw_confidence
    except Exception as exc:
        raise RuntimeError(f"Groq classifier unavailable: {exc}") from exc