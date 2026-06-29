"""
auditor.py — append-only JSONL audit log.

Every submission and appeal is written here.  The file is human-readable
and every line is independently parseable (newline-delimited JSON).
"""

import json
import os
from datetime import datetime, timezone

from config import LOG_PATH


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_log_dir() -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def append_submission(
    content_id: str,
    creator_id: str | None,
    classification: str,
    ai_probability: float,
    confidence_level: str,
    llm_score: float,
    stylo_score: float,
    stylo_metrics: dict,
    stylo_warning: str | None,
    label_text: str,
    text_preview: str,
) -> None:
    """Write one submission record to the audit log."""
    _ensure_log_dir()
    record = {
        "entry_type":       "submission",
        "content_id":       content_id,
        "creator_id":       creator_id,
        "timestamp":        _now_iso(),
        "classification":   classification,
        "ai_probability":   round(ai_probability, 4),
        "confidence_level": confidence_level,
        "signals": {
            "llm_score":      round(llm_score, 4),
            "stylo_score":    round(stylo_score, 4),
            "stylo_metrics":  stylo_metrics,
            "stylo_warning":  stylo_warning,
        },
        "label_text":  label_text,
        "text_preview": text_preview[:120],
        "status":      "classified",
    }
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def append_appeal(
    appeal_id: str,
    content_id: str,
    creator_reasoning: str,
) -> None:
    """Write one appeal record to the audit log."""
    _ensure_log_dir()
    record = {
        "entry_type":        "appeal",
        "appeal_id":         appeal_id,
        "content_id":        content_id,
        "timestamp":         _now_iso(),
        "creator_reasoning": creator_reasoning,
        "status":            "under_review",
    }
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def get_log(limit: int = 50) -> list[dict]:
    """Return the most recent *limit* log entries (newest last)."""
    _ensure_log_dir()
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, encoding="utf-8") as fh:
        lines = [ln.strip() for ln in fh if ln.strip()]
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return entries[-limit:]


def find_submission(content_id: str) -> dict | None:
    """Return the submission record for *content_id*, or None."""
    for entry in get_log(limit=10_000):
        if entry.get("entry_type") == "submission" and entry.get("content_id") == content_id:
            return entry
    return None


def find_appeal(content_id: str) -> dict | None:
    """Return an existing appeal record for *content_id*, or None."""
    for entry in get_log(limit=10_000):
        if entry.get("entry_type") == "appeal" and entry.get("content_id") == content_id:
            return entry
    return None