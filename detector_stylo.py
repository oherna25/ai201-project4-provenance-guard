"""
detector_stylo.py — Signal 2: Stylometric heuristics (pure Python, no deps).

Four metrics, each normalized to [0, 1] where 1.0 = AI-like:

  1. Sentence-length variance   — AI writing is unnaturally uniform
  2. Type-token ratio           — AI text reuses vocabulary more
  3. Punctuation density        — AI text uses less expressive punctuation
  4. Average word length        — AI text skews toward longer, Latinate words

Short-text dampening: texts < 50 words have their score pulled toward 0.5
because variance metrics are meaningless with only 2-3 sentences.
"""

import re
import math
import string


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def _words(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _punctuation_count(text: str) -> int:
    return sum(1 for ch in text if ch in string.punctuation)


# ---------------------------------------------------------------------------
# Individual metrics  (each returns a raw measurement, not a 0-1 score yet)
# ---------------------------------------------------------------------------

def _sentence_length_variance(text: str) -> float:
    sents = _sentences(text)
    if len(sents) < 2:
        return 0.0
    lengths = [len(_words(s)) for s in sents]
    mean = sum(lengths) / len(lengths)
    variance = sum((l - mean) ** 2 for l in lengths) / len(lengths)
    return math.sqrt(variance)   # std dev in words


def _type_token_ratio(text: str) -> float:
    words = _words(text)
    if not words:
        return 0.0
    return len(set(words)) / len(words)


def _punctuation_density(text: str) -> float:
    words = _words(text)
    if not words:
        return 0.0
    return (_punctuation_count(text) / len(words)) * 100   # per 100 words


def _avg_word_length(text: str) -> float:
    words = _words(text)
    if not words:
        return 0.0
    return sum(len(w) for w in words) / len(words)


# ---------------------------------------------------------------------------
# Per-metric normalization to [0, 1]  (1 = AI-like)
# ---------------------------------------------------------------------------

def _score_sentence_variance(std: float) -> float:
    """High variance → human (low score); low variance → AI (high score)."""
    # std ≥ 30 → score 0.0 (very human), std ≤ 5 → score 1.0 (very AI)
    clamped = max(5.0, min(30.0, std))
    return 1.0 - (clamped - 5.0) / 25.0


def _score_ttr(ttr: float) -> float:
    """High TTR → human (low score); low TTR → AI (high score)."""
    # ttr ≥ 0.90 → score 0.0, ttr ≤ 0.60 → score 1.0
    clamped = max(0.60, min(0.90, ttr))
    return 1.0 - (clamped - 0.60) / 0.30


def _score_punctuation_density(density: float) -> float:
    """High density → human; low density → AI."""
    # density ≥ 8 → score 0.0, density ≤ 2 → score 1.0
    clamped = max(2.0, min(8.0, density))
    return 1.0 - (clamped - 2.0) / 6.0


def _score_avg_word_length(awl: float) -> float:
    """Longer words → AI; shorter words → human."""
    # awl ≤ 4.0 → score 0.0, awl ≥ 6.5 → score 1.0
    clamped = max(4.0, min(6.5, awl))
    return (clamped - 4.0) / 2.5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify(text: str) -> tuple[float, dict, str | None]:
    """
    Returns:
      stylo_score  ∈ [0, 1]  (0 = human, 1 = AI)
      metrics      dict of raw measurements
      warning      str | None  (set when text is too short for reliable scoring)
    """
    words = _words(text)
    word_count = len(words)

    # Raw measurements
    std_dev   = _sentence_length_variance(text)
    ttr       = _type_token_ratio(text)
    punct_den = _punctuation_density(text)
    awl       = _avg_word_length(text)

    metrics = {
        "sentence_length_variance": round(std_dev, 4),
        "type_token_ratio":         round(ttr, 4),
        "punctuation_density":      round(punct_den, 4),
        "avg_word_length":          round(awl, 4),
    }

    # Per-metric scores
    scores = [
        _score_sentence_variance(std_dev),
        _score_ttr(ttr),
        _score_punctuation_density(punct_den),
        _score_avg_word_length(awl),
    ]
    raw_score = sum(scores) / len(scores)

    # Short-text dampening: pull toward 0.5 when word count < 50
    warning = None
    if word_count < 50:
        damp_factor = word_count / 50.0          # 0 → 1 as words → 50
        raw_score   = 0.5 + (raw_score - 0.5) * damp_factor
        warning = (
            f"Text is short ({word_count} words). "
            "Stylometric score dampened toward 0.5 — structural metrics are "
            "less reliable on short texts."
        )

    return round(raw_score, 4), metrics, warning