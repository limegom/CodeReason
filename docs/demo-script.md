# Three-minute demo script

## Recording setup

- Record at 1080p and keep the browser zoom near 90% so both evidence columns remain visible.
- Use the bundled synthetic assignment only. Never show `.env`, an API key, Docker environment details, or local logs.
- Keep the `LIVE`, `STORED LIVE`, and `Demo Fixture` provenance labels visible and describe them accurately.
- The submitted video must be public on YouTube, no longer than three minutes, and include an English voiceover or English translation.

## 0:00–0:20 — The grading gap

Show the landing page and say:

> Two programs can produce the same wrong answer for very different reasons. Output-only grading misses useful implementation evidence, while an unsupported AI score is difficult to trust. CodeReason puts observable evidence before interpretation and keeps the final grading decision with the instructor.

Select **Try Demo Assignment**.

## 0:20–0:40 — How Codex and GPT-5.6 were used

> I used Codex throughout development to inspect the repository, trace grading and security decisions across the schema, API, worker, interface, and tests, and validate the Docker and CI workflows. I retained the product and grading-policy decisions. GPT-5.6 Sol is integrated at runtime for constrained rubric structuring and evidence-bound Derived Analysis.

## 0:40–1:00 — Deterministic execution first

On the grading overview, search for `student-02` and open `idea_correct_output_wrong.py`.

> This synthetic submission defines the required function and constructs a nested list, but it adds one to every calculated index. CodeReason first runs the code in the restricted local Docker executor and records test, runtime, AST, static, and source-location evidence. Those records are the only Primary Evidence.

Point to the `LIVE` execution badge, the source code, and the failed `JSON_VALUE` test.

## 1:00–1:45 — Evidence-bound GPT-5.6 analysis

Scroll to **Derived Analysis** and say:

> GPT-5.6 Sol receives redacted source, the human-approved rubric, sanitized Primary Evidence, and score bounds. It receives no tools and does not execute the submission. Here it suggests partial credit for the observable two-dimensional construction while deducting for the failed value order. Each suggestion links back to evidence IDs, and the language describes what the code shows or suggests rather than claiming to know the student's private reasoning.

Point to `gpt-5.6-sol`, the suggested total, two rubric items, and their evidence links.

## 1:45–2:10 — Privacy and hidden-test boundary

Show **Feedback preview** and **External AI transmission disclosure**.

> Student-facing feedback may cite only student-visible evidence. Reviewer-only or hidden-test evidence can support reviewer analysis, but unsafe student feedback is withheld. The interface also records what categories were sent externally, confirms hidden values were withheld, and shows that model tools were disabled.

## 2:10–2:35 — Human decision

Point to the pending final total and editable human scores.

> The AI result is advisory. It cannot approve a rubric or create a final grade. A reviewer can inspect every citation, edit a score with a reason, and explicitly approve the human scores. Until that happens, final total remains pending and CSV leaves it blank.

During a live recording, select **Approve human scores** after checking the displayed values.

## 2:35–2:50 — Consistency review

Return to the grading overview and open **View consistency**.

> Cohort consistency checks compare deterministic fingerprints and raise only potential issues for review. They never change a score automatically.

## 2:50–3:00 — Close

> CodeReason does not replace instructor judgment. It makes every proposed deduction inspectable: evidence before judgment, human approval before final grade.
