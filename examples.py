"""
examples.py — Provenance Guard test corpus.

Run with:
    python examples.py

Requires GROQ_API_KEY in .env (real LLM calls are made for every example).
Each example prints both signal scores, the fused ai_probability, the
classification, and a one-line note on what the case is testing.
"""

import uuid

import auditor
import detector          # real Groq calls
import detector_stylo as ds
import scorer

# ---------------------------------------------------------------------------
# The corpus
# ---------------------------------------------------------------------------

EXAMPLES = [

    # -----------------------------------------------------------------------
    # A. AI policy document — repetitive vocabulary drives TTR very low
    # -----------------------------------------------------------------------
    {
        "id":    "ai_policy_document",
        "label": "AI-generated policy document",
        "category": "clear_ai",
        "text": (
            "This policy establishes organizational requirements for information security management "
            "and data protection compliance. All organizational personnel are required to maintain "
            "compliance with established information security requirements and organizational "
            "data protection standards. Unauthorized access to organizational information systems "
            "constitutes a violation of established security policy requirements. Personnel must "
            "complete mandatory information security training requirements on an annual basis. "
            "Organizational management maintains responsibility for enforcing information security "
            "policy compliance within respective organizational units. Violations of information "
            "security policy requirements will result in appropriate disciplinary action in "
            "accordance with established organizational procedures."
        ),
        "notes": (
            "Deliberate repetition of 'organizational', 'requirements', 'information security' "
            "drives TTR to ~0.58 (below the 0.60 AI floor). Uniform 15-word sentences, "
            "high AWL. Stylo=0.80, fused@llm0.93≈0.88 → ai/high."
        ),
        "expected_outcome": "ai (high confidence)",
    },

    # -----------------------------------------------------------------------
    # B. AI performance review — repetitive boilerplate HR language
    # -----------------------------------------------------------------------
    {
        "id":    "ai_performance_review",
        "label": "AI-generated HR performance review",
        "category": "clear_ai",
        "text": (
            "This performance evaluation provides a comprehensive assessment of professional "
            "contributions during the evaluation period. The employee demonstrated consistent "
            "performance across all designated responsibility areas. Technical competencies "
            "reflect adequate proficiency in relevant professional domains. Communication "
            "effectiveness maintained satisfactory standards throughout the evaluation period. "
            "Collaborative performance within the organizational team structure remained consistent. "
            "Professional development activities demonstrated satisfactory engagement with "
            "organizational learning objectives. Overall performance assessment reflects "
            "satisfactory contribution to organizational goals and professional responsibilities. "
            "Continued professional development is recommended to enhance performance contributions."
        ),
        "notes": (
            "Boilerplate HR language repeats 'performance', 'organizational', 'professional', "
            "'satisfactory' throughout. TTR≈0.71, AWL=8.8, near-zero variance. "
            "Stylo=0.66, fused@llm0.93≈0.82 → should clear ai/high threshold."
        ),
        "expected_outcome": "ai (high confidence)",
    },

    # -----------------------------------------------------------------------
    # C. AI product description — marketing copy with repeated value words
    # -----------------------------------------------------------------------
    {
        "id":    "ai_product_description",
        "label": "AI-generated SaaS product description",
        "category": "clear_ai",
        "text": (
            "This innovative solution delivers comprehensive functionality designed to maximize "
            "operational efficiency and organizational productivity. The integrated platform "
            "provides seamless connectivity across multiple organizational systems and workflows. "
            "Advanced analytics capabilities enable data-driven decision making and performance "
            "optimization. The solution incorporates enterprise-grade security features to ensure "
            "comprehensive data protection and regulatory compliance. Scalable architecture "
            "supports organizational growth and evolving operational requirements. Implementation "
            "of this solution facilitates significant operational improvements and productivity "
            "enhancement across organizational functions. The platform delivers measurable value "
            "through optimized workflows and enhanced operational performance."
        ),
        "notes": (
            "Repeats 'organizational', 'operational', 'solution', 'performance', 'comprehensive'. "
            "TTR≈0.70, AWL=8.3, variance near-zero. Stylo=0.67, fused@llm0.93≈0.82 → ai/high."
        ),
        "expected_outcome": "ai (high confidence)",
    },

    # -----------------------------------------------------------------------
    # 1. Canonical AI — both signals should agree strongly
    # -----------------------------------------------------------------------
    {
        "id":    "classic_ai_corporate",
        "label": "Classic AI corporate prose",
        "category": "clear_ai",
        "text": (
            "Artificial intelligence represents a transformative paradigm shift in modern "
            "society. It is important to note that while the benefits of AI are numerous, "
            "it is equally essential to consider the ethical implications. Furthermore, "
            "stakeholders across various sectors must collaborate to ensure responsible "
            "deployment. Organizations should implement comprehensive governance frameworks "
            "to address these challenges. The integration of advanced technologies requires "
            "careful consideration of societal impact."
        ),
        "notes": (
            "Uniform sentence lengths, Latinate vocabulary, generic hedging language. "
            "Both signals should lean AI; conservative threshold may still land uncertain."
        ),
        "expected_outcome": "ai or uncertain",
    },

    # -----------------------------------------------------------------------
    # 2. Canonical human — casual register, slang, irregular structure
    # -----------------------------------------------------------------------
    {
        "id":    "casual_human_chat",
        "label": "Casual human chat / social writing",
        "category": "clear_human",
        "text": (
            "ok so i finally tried that new ramen place downtown and honestly? underwhelming. "
            "the broth was fine but they put WAY too much sodium in it and i was thirsty for "
            "like three hours after. my friend got the spicy version and said it was better. "
            "probably wont go back unless someone drags me there lol. also the line was insane, "
            "like 45 minutes on a tuesday? who has time for that"
        ),
        "notes": (
            "Short words, caps, slang, rhetorical questions, no sentence discipline. "
            "LLM should recognise the register immediately."
        ),
        "expected_outcome": "human",
    },

    # -----------------------------------------------------------------------
    # 3. Short human text — short-text dampening fires
    # -----------------------------------------------------------------------
    {
        "id":    "short_haiku_human",
        "label": "Short human text / haiku (9 words)",
        "category": "edge_short_text",
        "text": "Old pond— a frog jumps in, sound of water.",
        "notes": (
            "9 words: dampening pulls stylo_score toward 0.5 (factor=0.18). "
            "LLM is the only meaningful signal. Should land uncertain."
        ),
        "expected_outcome": "uncertain (dampening floor)",
    },

    # -----------------------------------------------------------------------
    # 4. Short AI text — LLM should rescue where stylometrics can't
    # -----------------------------------------------------------------------
    {
        "id":    "short_ai_marketing",
        "label": "Short AI marketing copy (10 words)",
        "category": "edge_short_text",
        "text": "Revolutionize your workflow with our cutting-edge platform. Leverage AI-powered insights.",
        "notes": (
            "10 words: dampening neutralises stylo. LLM should catch buzzword tone. "
            "Fused score depends entirely on LLM — likely uncertain."
        ),
        "expected_outcome": "uncertain (dampening prevents confident ai verdict)",
    },

    # -----------------------------------------------------------------------
    # 5. Genre confound — formal human prose that looks AI to stylometrics
    # -----------------------------------------------------------------------
    {
        "id":    "legal_academic_formal",
        "label": "Legal / academic writing (human, formal register)",
        "category": "confound_formal_human",
        "text": (
            "The doctrine of promissory estoppel, as articulated in Restatement (Second) "
            "of Contracts section 90, requires a showing of four elements: a promise, "
            "reasonable and foreseeable reliance upon that promise, actual reliance, and "
            "resulting detriment. Courts have historically applied this doctrine with "
            "considerable variation in jurisdictions where the underlying consideration "
            "doctrine already provides substantial protection. The Eighth Circuit has "
            "restricted application to cases involving unconscionable injury, whereas the "
            "Second Circuit has adopted a more permissive reading of the reliance requirement."
        ),
        "notes": (
            "High AWL, formal register, specific citations. Stylo will flag as AI-like. "
            "LLM should recognise legal specificity as human. Correct outcome: uncertain."
        ),
        "expected_outcome": "uncertain (genre confound — correct conservative behavior)",
    },

    # -----------------------------------------------------------------------
    # 6. Lightly edited AI — signals should partially disagree
    # -----------------------------------------------------------------------
    {
        "id":    "lightly_edited_ai",
        "label": "Lightly edited AI output with human touches",
        "category": "borderline",
        "text": (
            "I have been thinking a lot about remote work lately. There are genuine "
            "tradeoffs — flexibility and no commute on one side, isolation and blurred "
            "work-life boundaries on the other. Studies show productivity varies widely "
            "by individual and role type. Communication overhead increases for distributed "
            "teams. The evidence suggests hybrid models may offer the optimal balance for "
            "most knowledge workers in professional settings."
        ),
        "notes": (
            "Stylo sees human structure; LLM may catch 'studies show' / 'evidence suggests' "
            "hedging. Signals likely disagree. Should land uncertain."
        ),
        "expected_outcome": "uncertain (signal disagreement)",
    },

    # -----------------------------------------------------------------------
    # 7. Stream of consciousness — high structural variance, very human
    # -----------------------------------------------------------------------
    {
        "id":    "stream_of_consciousness",
        "label": "Stream-of-consciousness human writing",
        "category": "clear_human",
        "text": (
            "woke up and it was already noon which was bad because i had that thing at 2 "
            "and i still hadnt — god where did i put my keys — anyway the coffee was cold "
            "by the time i remembered it existed and then sarah texted asking if i was "
            "still coming and i said yes obviously but also maybe? like i genuinely do not "
            "know what i want to do today. the laundry is staring at me. "
            "its been staring at me for four days."
        ),
        "notes": (
            "Extreme sentence variance, em-dashes, interruptions, named person. "
            "Both signals should strongly agree: human."
        ),
        "expected_outcome": "human (high confidence)",
    },

    # -----------------------------------------------------------------------
    # 8. Polished personal essay — human despite polish
    # -----------------------------------------------------------------------
    {
        "id":    "personal_essay_with_opinion",
        "label": "Polished personal essay with a strong point of view",
        "category": "borderline",
        "text": (
            "Climate change is the defining challenge of our era, yet our political "
            "response remains hopelessly fragmented. I grew up near a river that flooded "
            "twice in my childhood; it flooded six times in the last decade. That is not "
            "an abstraction. What frustrates me most is not denialism — that is a fringe "
            "position now — but the comfortable delay of people who accept the science "
            "and still find reasons to wait. The transition costs are real. So is the "
            "cost of doing nothing, and unlike transition costs, that one compounds."
        ),
        "notes": (
            "Personal anecdote, semicolons, em-dashes, punchy short sentences. "
            "LLM should lean human; may land just above the 0.20 threshold → uncertain."
        ),
        "expected_outcome": "uncertain or human",
    },

    # -----------------------------------------------------------------------
    # 9. Repetitive poem — stylometric false alarm rescued by dampening
    # -----------------------------------------------------------------------
    {
        "id":    "repetitive_poem_confound",
        "label": "Repetitive poem — stylometric false alarm",
        "category": "edge_genre_confound",
        "text": (
            "I wait. I wait for you. I wait for you every day. "
            "Every day I wait and wonder. I wonder and I wait. "
            "The waiting is the wondering. The wondering is the wait."
        ),
        "notes": (
            "33 words: dampening active (factor=0.66). Raw TTR=0.36 looks very AI, "
            "but dampening neutralises it. LLM should recognise anaphora as a device."
        ),
        "expected_outcome": "uncertain (dampening rescues repetitive poem)",
    },

    # -----------------------------------------------------------------------
    # 10. AI listicle — rigid structure, uniform sentence length
    # -----------------------------------------------------------------------
    {
        "id":    "ai_listicle_no_punctuation",
        "label": "AI listicle — uniform structure, minimal punctuation",
        "category": "edge_short_text",
        "text": (
            "There are several key benefits to regular exercise. "
            "First it improves cardiovascular health significantly. "
            "Second it enhances mental wellbeing and reduces stress. "
            "Third it promotes better sleep quality and duration. "
            "Fourth it increases overall energy levels throughout the day. "
            "Fifth it strengthens the immune system and reduces illness."
        ),
        "notes": (
            "48 words: just under dampening threshold. Near-zero sentence variance. "
            "LLM should catch the numbered-list template. Likely uncertain due to dampening."
        ),
        "expected_outcome": "uncertain (dampening prevents confident ai verdict)",
    },

    # -----------------------------------------------------------------------
    # Appeal scenario 1 — creator contests an AI verdict (formal register)
    # -----------------------------------------------------------------------
    {
        "id":    "appeal_formal_human_flagged",
        "label": "Appeal: formal human writing flagged as AI",
        "category": "appeal",
        "text": (
            "The mitigation of systemic financial risk necessitates comprehensive regulatory "
            "oversight and coordinated institutional response mechanisms. Central banking "
            "authorities must implement countercyclical capital requirements to ensure "
            "adequate liquidity buffers during periods of elevated market volatility. "
            "Prudential supervision frameworks require continuous refinement to address "
            "emerging vulnerabilities within interconnected financial systems. Macroprudential "
            "policy instruments complement microprudential regulation to achieve systemic "
            "stability objectives. Regulatory harmonisation across jurisdictions facilitates "
            "effective cross-border risk management and supervisory cooperation."
        ),
        "notes": (
            "A financial policy analyst's genuine writing. High AWL and formal register "
            "will push stylo AI-like. LLM may also lean AI. The creator appeals because "
            "they write like this professionally — a legitimate false-positive scenario."
        ),
        "expected_outcome": "ai or uncertain — appeal demonstrates the false-positive case",
        "appeal_reasoning": (
            "I am a regulatory economist and this excerpt is from a working paper I authored. "
            "My writing is naturally formal and technical. I am a non-native English speaker "
            "which may contribute to the structured sentence style. I can provide the full "
            "paper with revision history as evidence of authorship."
        ),
    },

    # -----------------------------------------------------------------------
    # Appeal scenario 2 — creator contests an uncertain verdict
    # -----------------------------------------------------------------------
    {
        "id":    "appeal_uncertain_human",
        "label": "Appeal: human writer frustrated by uncertain verdict",
        "category": "appeal",
        "text": (
            "I started keeping bees three years ago, mostly by accident. A swarm landed "
            "in my apple tree in May and I called a local beekeeper who said she couldn't "
            "collect it and did I want it. I said yes before I understood what that meant. "
            "Now I have two hives and more honey than I can give away, and I spend a "
            "disproportionate amount of time thinking about insects. My partner thinks "
            "this is funny. I think it has made me more patient, though I couldn't say "
            "exactly why — something about working with creatures that have no interest "
            "in your feelings."
        ),
        "notes": (
            "Genuine personal essay voice with specific detail and first-person anecdote. "
            "Should score clearly human, but polished structure may push it into uncertain. "
            "Creator appeals — wants the record corrected."
        ),
        "expected_outcome": "human or uncertain — appeal shows creator contesting uncertainty",
        "appeal_reasoning": (
            "This is a personal essay I wrote for my newsletter. I have been writing it "
            "for four years and have 800 subscribers who can verify my authorship. "
            "The uncertain verdict is frustrating — this is entirely from my own experience "
            "and I have drafts showing the writing process."
        ),
    },

    # -----------------------------------------------------------------------
    # Appeal scenario 3 — creator correctly flagged but appeals anyway
    # -----------------------------------------------------------------------
    {
        "id":    "appeal_ai_flagged_correctly",
        "label": "Appeal: AI-generated content correctly flagged",
        "category": "appeal",
        "text": (
            "Effective leadership requires the cultivation of comprehensive strategic vision "
            "and the systematic development of organisational capabilities. Successful leaders "
            "demonstrate consistent commitment to stakeholder engagement and evidence-based "
            "decision-making processes. The integration of diverse perspectives within "
            "leadership frameworks facilitates innovative problem-solving and organisational "
            "resilience. Continuous professional development remains essential for maintaining "
            "leadership effectiveness in dynamic and complex organisational environments. "
            "Transformational leadership approaches consistently demonstrate superior outcomes "
            "in terms of employee engagement and organisational performance metrics."
        ),
        "notes": (
            "Classic AI leadership content: uniform sentences, Latinate vocabulary, "
            "repetitive 'organisational', zero personal voice. Correctly flagged. "
            "Creator appeals anyway — tests the 409 guard if run twice, and shows "
            "the audit trail capturing a contested-but-correct classification."
        ),
        "expected_outcome": "ai/high — appeal logged but classification stands",
        "appeal_reasoning": (
            "I used AI to help draft this but I reviewed and edited the content myself. "
            "I believe my editorial contributions make this substantially my own work. "
            "I am contesting the classification on those grounds."
        ),
    },
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_examples():
    print("=" * 72)
    print("Provenance Guard — Example Corpus  (live Groq calls)")
    print("=" * 72)
    print()

    totals = {}

    for i, ex in enumerate(EXAMPLES, 1):
        text = ex["text"]
        print(f"[{i}/{len(EXAMPLES)}] {ex['label']}  ", end="", flush=True)

        # Real calls
        llm_score                        = detector.classify(text)
        stylo_score, metrics, warning    = ds.classify(text)
        ai_prob                          = scorer.fuse(llm_score, stylo_score)
        classification, confidence       = scorer.classify(ai_prob)
        label_text                       = scorer.label(classification, confidence)
        word_count                       = len(text.split())

        bucket = classification if confidence == "high" else "uncertain"
        totals[bucket] = totals.get(bucket, 0) + 1

        content_id = str(uuid.uuid4())
        auditor.append_submission(
            content_id       = content_id,
            creator_id       = f"examples/{ex['id']}",
            classification   = classification,
            ai_probability   = ai_prob,
            confidence_level = confidence,
            llm_score        = llm_score,
            stylo_score      = stylo_score,
            stylo_metrics    = metrics,
            stylo_warning    = warning,
            label_text       = label_text,
            text_preview     = text,
        )

        print(f"→ {classification.upper()} ({ai_prob:.4f})")
        print(f"  Words          : {word_count}")
        print(f"  LLM score      : {llm_score:.4f}")
        print(f"  Stylo score    : {stylo_score:.4f}{'  ⚠ dampened' if warning else ''}")
        print(f"    var={metrics['sentence_length_variance']:.2f}  "
              f"ttr={metrics['type_token_ratio']:.3f}  "
              f"punct={metrics['punctuation_density']:.2f}  "
              f"awl={metrics['avg_word_length']:.2f}")
        print(f"  ai_probability : {ai_prob:.4f}")
        print(f"  Classification : {classification.upper()} / {confidence}")
        print(f"  Label          : {label_text.splitlines()[0]}")
        print(f"  Expected       : {ex['expected_outcome']}")
        print(f"  Notes          : {ex['notes'][:110]}...")
        print(f"  Logged         : {content_id}")

        # File appeal if this example has one
        if ex.get("appeal_reasoning"):
            appeal_id = str(uuid.uuid4())
            auditor.append_appeal(
                appeal_id         = appeal_id,
                content_id        = content_id,
                creator_reasoning = ex["appeal_reasoning"],
            )
            print(f"  Appeal filed   : {appeal_id}")
            print(f"  Reasoning      : {ex['appeal_reasoning'][:80]}...")

        print()

    print("=" * 72)
    ai_n   = totals.get("ai", 0)
    hu_n   = totals.get("human", 0)
    un_n   = totals.get("uncertain", 0)
    ap_n   = sum(1 for ex in EXAMPLES if ex.get("appeal_reasoning"))
    print(f"Distribution — ai/high: {ai_n}  human/high: {hu_n}  uncertain: {un_n}")
    print(f"Appeals filed  : {ap_n}")
    print("=" * 72)


if __name__ == "__main__":
    run_examples()