"""
app.py — Provenance Guard Flask application.

Routes:
  POST /submit   — classify text, return label + signals, log decision
  GET  /log      — return recent audit log entries
  POST /appeal   — contest a classification (M5)

Rate limiting (M5):
  POST /submit is capped at 10 requests/minute and 100 requests/day per IP.

  Reasoning for those limits:
    • A legitimate creator submitting their own work rarely needs more than
      a few submissions per session.  10/min is generous for interactive use
      while being far too low for automated flooding.
    • 100/day prevents a single actor from exhausting the Groq free-tier quota
      or poisoning the audit log with junk data.
"""

import os
import uuid

from flask import Flask, jsonify, request, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import auditor
import detector
import detector_stylo
import scorer

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Rate limiter (M5) — in-memory storage is fine for local / single-process
# ---------------------------------------------------------------------------
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],          # no global default; apply per route
    storage_uri="memory://",
)


# ---------------------------------------------------------------------------
# POST /submit
# ---------------------------------------------------------------------------

@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    data = request.get_json(silent=True)
    if not data or not data.get("text", "").strip():
        return jsonify({"error": "Request body must include a non-empty 'text' field."}), 400

    text       = data["text"].strip()
    creator_id = data.get("creator_id") or None
    content_id = str(uuid.uuid4())

    # --- Signal 1: LLM ---
    try:
        llm_score = detector.classify(text)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

    # --- Signal 2: Stylometrics ---
    stylo_score, stylo_metrics, stylo_warning = detector_stylo.classify(text)

    # --- Confidence fusion ---
    ai_probability  = scorer.fuse(llm_score, stylo_score)
    classification, confidence_level = scorer.classify(ai_probability)
    label_text      = scorer.label(classification, confidence_level)

    # --- Audit log ---
    auditor.append_submission(
        content_id      = content_id,
        creator_id      = creator_id,
        classification  = classification,
        ai_probability  = ai_probability,
        confidence_level= confidence_level,
        llm_score       = llm_score,
        stylo_score     = stylo_score,
        stylo_metrics   = stylo_metrics,
        stylo_warning   = stylo_warning,
        label_text      = label_text,
        text_preview    = text,
    )

    return jsonify({
        "content_id":       content_id,
        "classification":   classification,
        "ai_probability":   ai_probability,
        "confidence_level": confidence_level,
        "label_text":       label_text,
        "signals": {
            "llm_score":     round(llm_score, 4),
            "stylo_score":   round(stylo_score, 4),
            "stylo_metrics": stylo_metrics,
            "stylo_warning": stylo_warning,
        },
        "status": "classified",
    }), 200


# ---------------------------------------------------------------------------
# GET /log
# ---------------------------------------------------------------------------

@app.route("/log", methods=["GET"])
def get_log():
    try:
        limit   = int(request.args.get("limit", 50))
        limit   = max(1, min(limit, 500))
    except ValueError:
        limit   = 50

    entries = auditor.get_log(limit=limit)
    return jsonify({"count": len(entries), "entries": entries}), 200


# ---------------------------------------------------------------------------
# POST /appeal  (M5)
# ---------------------------------------------------------------------------

@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required."}), 400

    content_id = (data.get("content_id") or "").strip()
    reasoning  = (data.get("creator_reasoning") or "").strip()

    if not content_id:
        return jsonify({"error": "'content_id' is required."}), 400
    if not reasoning:
        return jsonify({"error": "'creator_reasoning' is required."}), 400

    # 404 if submission doesn't exist
    submission = auditor.find_submission(content_id)
    if not submission:
        return jsonify({
            "error": f"No submission found with content_id '{content_id}'."
        }), 404

    # 409 if appeal already submitted
    existing = auditor.find_appeal(content_id)
    if existing:
        return jsonify({
            "error":    "An appeal has already been submitted for this content.",
            "appeal_id": existing["appeal_id"],
            "status":   existing["status"],
        }), 409

    appeal_id = str(uuid.uuid4())
    auditor.append_appeal(
        appeal_id        = appeal_id,
        content_id       = content_id,
        creator_reasoning= reasoning,
    )

    return jsonify({
        "appeal_id":  appeal_id,
        "content_id": content_id,
        "status":     "under_review",
        "message": (
            "Your appeal has been received and the submission has been flagged for "
            "human review. You will be notified when a decision is made. "
            "Thank you for helping us improve attribution accuracy."
        ),
    }), 200


# ---------------------------------------------------------------------------
# 429 handler — rate limit exceeded
# ---------------------------------------------------------------------------

@app.errorhandler(429)
def rate_limit_exceeded(e):
    return jsonify({
        "error": "Rate limit exceeded.",
        "detail": (
            "Submission endpoint is limited to 10 requests per minute and "
            "100 requests per day per IP address. Please try again later."
        ),
    }), 429


# ---------------------------------------------------------------------------
# GET /dashboard — serve the analytics dashboard HTML
# ---------------------------------------------------------------------------

@app.route("/dashboard", methods=["GET"])
def dashboard():
    here = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(here, "dashboard.html")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"[Provenance Guard] Starting — audit log: {__import__('config').LOG_PATH}")
    app.run(debug=True, port=5000)