# Provenance Guard — Planning Document

## Milestone Progress
- [x] Milestone 1: Architecture narrative & diagram
- [x] Milestone 2: Spec, label variants, appeals design, edge cases, AI tool plan
- [ ] Milestone 3: Submission endpoint + Signal 1 (Groq LLM)
- [ ] Milestone 4: Signal 2 (Stylometrics) + Confidence scoring
- [ ] Milestone 5: Transparency labels, appeals workflow, rate limiting, audit log
- [ ] Milestone 6: README + portfolio walkthrough

---

## Architecture Narrative

*(Milestone 1 deliverable — also used verbatim in README)*

A creator submits their work via **POST /submit** with a JSON body containing the text content and an optional `creator_id`. The request first passes through the **Rate Limiter** (Flask-Limiter), which enforces per-IP submission limits. If allowed, the raw text enters the **Detection Pipeline**.

The pipeline runs two independent signals in parallel:

**Signal 1 — LLM Classifier (Groq):** The text is sent to `llama-3.3-70b-versatile` with a structured prompt asking the model to assess whether the writing reads as human-authored or AI-generated. The model returns a verdict and a confidence value. This captures *semantic and holistic* properties — tonal consistency, idiosyncratic phrasing, whether the writing feels like it's reaching for something or just satisfying a prompt.

**Signal 2 — Stylometric Analyzer:** The same text passes through a pure-Python module that computes four statistical properties: sentence length variance, type-token ratio (vocabulary diversity), punctuation density, and average word length. AI text is measurably more uniform than human writing on these dimensions. Each metric is scored against calibrated thresholds and averaged into a single `stylo_score`.

Both scores go to the **Confidence Scorer**, which combines them via weighted average into a single `ai_probability` float (0.0 = confident human, 1.0 = confident AI). This value maps to a classification (`human`, `ai`, or `uncertain`) and a confidence level (`high` or `uncertain`).

The classification and confidence level are passed to the **Label Generator**, which selects the appropriate transparency label text. A UUID `content_id` is generated for this submission.

Everything is written as a single JSON line to the **Audit Log** (`logs/audit.jsonl`): content ID, timestamp, both signal scores, combined score, classification, label text, and a truncated text preview.

The API returns a structured response with `content_id`, `classification`, `ai_probability`, `confidence_level`, `label_text`, and both individual signal scores.

For appeals: a creator sends **POST /appeal** with their `content_id` and `creator_reasoning`. The Appeal Handler looks up the original decision, flips the content's status to `under_review`, appends an appeal record to the audit log, and returns a confirmation.

---

## Architecture

*(Required under this heading in planning.md — ASCII diagram)*

### Submission Flow

```
POST /submit
{ text, creator_id? }
        |
        v
  [Rate Limiter]                   ← enforces 10/min, 100/day per IP
  Flask-Limiter
        |
        v (allowed)
        |
   +-----------raw text-----------+
   |                              |
   v                              v
[Signal 1]                   [Signal 2]
LLM Classifier               Stylometric Analyzer
Groq llama-3.3-70b           Pure Python heuristics
   |                              |
   | llm_score (0.0–1.0)          | stylo_score (0.0–1.0)
   |                              |
   +----------+-------------------+
              |
              v
     [Confidence Scorer]
     ai_probability = (0.60 × llm_score) + (0.40 × stylo_score)
     classification  = "human" | "ai" | "uncertain"
     confidence_level = "high" | "uncertain"
              |
              v
     [Label Generator]
     selects label text by (classification, confidence_level)
              |
              v
     [Audit Log]
     append JSON line → logs/audit.jsonl
     (content_id, timestamp, scores, label, text preview, status)
              |
              v
     HTTP 200 JSON response
     { content_id, classification, ai_probability,
       confidence_level, label_text,
       signals: { llm_score, stylo_score } }
```

### Appeal Flow

```
POST /appeal
{ content_id, creator_reasoning }
        |
        v
  [Appeal Handler]
  look up content_id in audit log
        |
        v
  update status → "under_review"
        |
        v
  [Audit Log]
  append appeal record:
  { content_id, appeal_id, timestamp,
    creator_reasoning, original_classification,
    status: "under_review" }
        |
        v
  HTTP 200 JSON response
  { appeal_id, content_id, status: "under_review", message }
```

---

## Detection Signals

*(Milestone 2 spec — required in planning.md and README)*

### Signal 1: LLM Classifier (Groq — llama-3.3-70b-versatile)

**What it measures:** Semantic and holistic stylistic coherence. The model assesses whether the text reads as human-authored by looking at tonal consistency, idiosyncratic word choices, structural naturalness, and whether the voice feels personal or optimized.

**Why it differs between human and AI writing:** LLMs produce text that is well-formed, coherent, and avoids awkward leaps — which is itself a signal. Human writing has a different texture: it digresses, uses unexpected comparisons, has rhythm that isn't always optimized for clarity. A classifier model that has seen enough of both can recognize these patterns holistically in a way rules can't.

**Output format:** A prompt-engineered response parsed for two values:
- `verdict`: `"human"` or `"ai"`
- `raw_confidence`: float 0.0–1.0 (the model's self-reported certainty in that verdict)

These are combined into `llm_score`: if verdict is `"ai"`, `llm_score = raw_confidence`; if verdict is `"human"`, `llm_score = 1.0 - raw_confidence`. So 0.0 always means confident human, 1.0 always means confident AI.

**Blind spots:**
- Short texts (< 100 words) don't provide enough signal to assess holistically.
- Human writers who deliberately write in a clean, structured style will be penalized.
- AI text that has been lightly edited or humanized by a revision step.
- Non-English text and genre-specific writing (legal briefs, technical docs) where "AI-like uniformity" is simply the convention.
- The model has no memory across submissions — it cannot compare an author's historical voice.

---

### Signal 2: Stylometric Analyzer (Pure Python)

**What it measures:** Four structural, statistical properties of the text:

1. **Sentence length variance** — standard deviation of sentence lengths in words. High variance is more human-like; low variance is more AI-like.
2. **Type-token ratio (TTR)** — unique words ÷ total words. AI text reuses vocabulary more predictably; human writing is more lexically diverse.
3. **Punctuation density** — punctuation characters per 100 words. Human writing uses punctuation more expressively and irregularly (dashes, ellipses, etc.).
4. **Average word length** — AI writing tends toward slightly longer, more formal words on average.

**Why it differs between human and AI writing:** These are structural fingerprints, independent of meaning. LLMs produce text that is varied enough to seem natural but measurably less noisy when you compute the variance across sentences. A human writing a poem will vary rhythm in ways that feel right but look irregular on paper; an LLM's variation is more statistically uniform.

**Output format:** A `stylo_score` float (0.0–1.0) computed by scoring each metric against calibrated thresholds, then averaging the four per-metric scores. 0.0 = strongly human-like structure; 1.0 = strongly AI-like structure.

**Blind spots:**
- Unreliable on very short texts (< 50 words — not enough data points for variance to be meaningful).
- Genre confound: a legal brief or academic abstract written by a human will have low sentence variance and high word length, falsely resembling AI output.
- Won't catch AI text that has been deliberately stylized to be irregular.
- Measures form, not intent — a clean writer will always be penalized regardless of authorship.

---

## Uncertainty Representation

*(Milestone 2 spec)*

**Fusion formula:**
```
ai_probability = (0.60 × llm_score) + (0.40 × stylo_score)
```

**Weighting rationale:** The LLM captures semantic patterns the stylometric signal completely misses, making it the stronger signal in most cases. Stylometrics provide a structural cross-check — especially when the LLM is uncertain — but structural features alone are too easily confounded by genre to be weighted equally.

**What each score value means:**

| ai_probability | Interpretation |
|---|---|
| 0.0 – 0.20 | System is highly confident this is human writing |
| 0.21 – 0.79 | Signals disagree or neither is confident; genuinely uncertain |
| 0.80 – 1.0 | System is highly confident this is AI-generated writing |

**Classification thresholds:**

| ai_probability | classification | confidence_level |
|---|---|---|
| ≥ 0.80 | `ai` | `high` |
| ≤ 0.20 | `human` | `high` |
| 0.21 – 0.79 | `uncertain` | `uncertain` |

**False positive asymmetry:** Mislabeling a human writer's work as AI is a reputational harm to a real person. A false negative (missing AI content) is a transparency gap, but a less severe one. This asymmetry is baked into the thresholds: the system only calls something AI with "high confidence" at ≥ 0.80, not at 0.51. Anything below that ceiling gets an "uncertain" label that explicitly tells the reader the system isn't sure, and the creator can appeal. When in doubt, the system defers toward uncertainty rather than accusation.

---

## Transparency Label Variants

*(Milestone 2 spec — these exact strings will be returned by the API and documented in the README)*

All three variants must be reachable. Graders will test by submitting inputs that produce each confidence band.

**Variant 1 — High-confidence AI** (`ai_probability ≥ 0.80`)
```
⚠️ AI-Generated Content
Our analysis strongly suggests this work was generated by an AI writing tool, not
written by the credited creator. Confidence: High. If you are the creator and believe
this is incorrect, you may contest this classification using the appeals process.
```

**Variant 2 — High-confidence Human** (`ai_probability ≤ 0.20`)
```
✅ Human-Authored
Our analysis strongly suggests this work was written by the credited creator.
Confidence: High.
```

**Variant 3 — Uncertain** (`0.21 ≤ ai_probability ≤ 0.79`)
```
🔍 Authorship Uncertain
Our system could not confidently determine whether this work was written by a human
or generated by AI. This may reflect an unusual writing style, a short submission,
or signals that disagree. The creator may contest this classification. This label
may be updated following a review.
```

---

## Appeals Workflow

*(Milestone 2 spec)*

**Who can submit an appeal:** Any creator, identified by submitting the `content_id` returned when their work was originally classified. No authentication is required beyond possessing the content ID (acceptable for this project scope).

**What they provide:**
- `content_id` (required) — the UUID from the original `/submit` response
- `creator_reasoning` (required) — free-text explanation; e.g., "I wrote this myself. I am a non-native English speaker and my writing may appear more formal than typical."

**What the system does on receipt:**
1. Looks up the original decision in the audit log by `content_id`. Returns 404 if not found; 409 if an appeal already exists for this ID.
2. Updates the content's `status` field from `"classified"` to `"under_review"` in the in-memory store and in the audit log.
3. Appends a new appeal record to `logs/audit.jsonl` containing: `appeal_id` (new UUID), `content_id`, `timestamp`, `creator_reasoning`, `original_classification`, `original_ai_probability`, and `status: "under_review"`.
4. Returns a confirmation response.

**What a human reviewer would see (GET /log):**
- The original submission entry (with all signal scores and the original label)
- Directly below it (or queryable by content_id): the appeal entry with the creator's reasoning and the `under_review` status

Automated re-classification is not implemented — a human moderator reviews the appeal queue. This is intentional: the system acknowledges its own uncertainty and defers the final call to a human.

---

## Anticipated Edge Cases

*(Milestone 2 spec — at least two specific scenarios)*

**1. Formally-written human poetry** — A poet with a clean, structured style submits a 12-line poem with consistent meter and elevated vocabulary. The stylometric signal sees low sentence variance and high word length, scoring it 0.65 (leans AI). The LLM may read the same precision as intentional craft and score it 0.35 (leans human). Combined: ~0.47 — uncertain band. The poet gets the "Authorship Uncertain" label even though they clearly wrote it. This is the primary false positive scenario; the label and appeals workflow are specifically designed to handle it gracefully.

**2. Short text submissions (< 80 words)** — A user submits a brief haiku or a two-sentence blurb. The stylometric signal can't compute meaningful sentence variance from 3 sentences, producing an unreliable `stylo_score`. The LLM may not have enough text to read tone holistically. Both signals will likely produce mid-range scores, pushing the result into the uncertain band almost by default. The system will correctly show "Authorship Uncertain" but for the wrong reason — not because signals genuinely disagree, but because neither had enough data. A future improvement would be a minimum-length check that returns a dedicated "too short to classify" response.

**3. Lightly edited AI output** — A user generates a piece with an LLM and then manually rewrites a few sentences to add irregularities. The stylometric signal may pick up the structural inconsistency and score it lower (more human-like), while the LLM may still recognize the underlying AI cadence in the unedited passages and score it higher. The signals diverge in opposite ways from what each usually produces, making the combined score unreliable. This is the hardest case — neither signal was designed to detect *partial* AI generation.

---

## API Surface

*(Milestone 1 deliverable — the contract all implementation code satisfies)*

### `POST /submit`
```
Request body:
{
  "text":       string (required) — the creative work to analyze
  "creator_id": string (optional) — platform user ID
}

Response 200:
{
  "content_id":       string (UUID),
  "classification":   "human" | "ai" | "uncertain",
  "ai_probability":   float (0.0–1.0),
  "confidence_level": "high" | "uncertain",
  "label_text":       string (exact text shown to readers),
  "signals": {
    "llm_score":   float,
    "stylo_score": float
  },
  "status": "classified"
}

Errors:
  400 — missing or empty "text" field
  429 — rate limit exceeded
  503 — Groq API unavailable (returns uncertain label with error flag)
```

### `POST /appeal`
```
Request body:
{
  "content_id":        string (required) — UUID from /submit response
  "creator_reasoning": string (required) — creator's explanation
}

Response 200:
{
  "appeal_id":  string (UUID),
  "content_id": string,
  "status":     "under_review",
  "message":    "Your appeal has been received and logged. A moderator will
                 review your submission. This typically takes 2–3 business days."
}

Errors:
  400 — missing required fields
  404 — content_id not found
  409 — appeal already submitted for this content_id
```

### `GET /log`
```
Response 200:
{
  "entries": [
    {
      "content_id":       string,
      "creator_id":       string | null,
      "timestamp":        string (ISO 8601),
      "classification":   string,
      "ai_probability":   float,
      "signals": {
        "llm_score":   float,
        "stylo_score": float
      },
      "label_text":    string,
      "text_preview":  string (first 100 chars),
      "status":        "classified" | "under_review",
      "appeal_reasoning": string | null
    }
  ]
}
```

---

## File Structure

```
provenance-guard/
├── app.py              ← Flask app: routes, rate limiting, orchestration
├── detector_llm.py     ← Signal 1: Groq LLM classifier
├── detector_stylo.py   ← Signal 2: Stylometric heuristics
├── scorer.py           ← Confidence score fusion + label selection
├── auditor.py          ← Audit log read/write (logs/audit.jsonl)
├── config.py           ← API keys, model, thresholds, log path, rate limits
├── logs/
│   └── audit.jsonl     ← Append-only structured log
├── .env                ← GROQ_API_KEY (gitignored)
├── .env.example
├── requirements.txt
├── planning.md
└── README.md
```

**`requirements.txt`:**
```
flask>=3.0.0
flask-limiter>=3.5.0
groq>=1.1.2,<2
python-dotenv>=1.0.0
```

---

## AI Tool Plan

*(Milestone 2 spec — how AI assistance will be used in each implementation milestone)*

### M3 — Submission Endpoint + Signal 1 (Groq LLM)

**Spec sections to provide:** Detection Signals (Signal 1 entry only) + Architecture diagram (submission flow only) + API Surface (`POST /submit` contract).

**What to ask for:**
1. Flask app skeleton with `POST /submit` route stub that accepts `{text, creator_id}` and returns a hardcoded response.
2. `detector_llm.py` — a function `classify_with_llm(text: str) -> dict` that calls Groq with a prompt returning `{"verdict": "human"|"ai", "raw_confidence": float}`.

**How to verify before wiring in:**
- Call `classify_with_llm()` directly with the 4 test inputs from Milestone 4's sample set.
- Confirm the return dict has the right keys and types.
- Check that `raw_confidence` actually varies — if it's always 0.9, the prompt needs tuning.
- Only wire into the endpoint after the function passes these checks.

---

### M4 — Signal 2 + Confidence Scoring

**Spec sections to provide:** Detection Signals (Signal 2 entry) + Uncertainty Representation section + Architecture diagram.

**What to ask for:**
1. `detector_stylo.py` — a function `classify_with_stylometrics(text: str) -> float` that computes the four metrics (sentence length variance, TTR, punctuation density, avg word length) and returns a `stylo_score` float.
2. `scorer.py` — a function `compute_confidence(llm_score: float, stylo_score: float) -> dict` that applies the weighted formula and returns `{ai_probability, classification, confidence_level}`.

**What to check:**
- Run both signals independently on all 4 test inputs before combining.
- Confirm the clearly AI sample scores noticeably higher than the clearly human sample.
- Confirm the weighted formula in the generated code matches the 60/40 split in this spec — AI tools sometimes substitute their own weighting silently.
- Verify all three classification buckets (`human`, `ai`, `uncertain`) are reachable by the thresholds as implemented.

---

### M5 — Production Layer (Labels, Appeals, Rate Limiting, Audit Log)

**Spec sections to provide:** Transparency Label Variants + Appeals Workflow + Architecture diagram (both flows) + API Surface (`POST /appeal`).

**What to ask for:**
1. `scorer.py` addition — a function `generate_label(classification: str, confidence_level: str) -> str` that returns the exact label text strings from this spec.
2. `POST /appeal` endpoint in `app.py` — including status update logic and audit log append.
3. Flask-Limiter configuration for `POST /submit` with `storage_uri="memory://"`.

**How to verify:**
- Test all three label variants are reachable by submitting inputs that produce `ai_probability` in each band (< 0.20, > 0.80, middle).
- Submit an appeal with a valid `content_id` from a prior submission; then call `GET /log` and confirm the entry shows `status: "under_review"` and `appeal_reasoning` populated.
- Run the 12-request rate limit test from the Milestone 5 instructions; confirm responses 11–12 return `429`.
- Check the audit log has ≥ 3 entries with all required fields before writing the README.


# stretch feature

i decided to do an analytics dashboard.
i updated app.py to compute analytics and a gui using html that renders the charts and data. each metric gets it own chart. 
it grabs data from the log to show number of occurences per each possible outcome ( AI , uncertain , human) also shows data from past runs
