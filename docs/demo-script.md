# Three-minute demo script

## Before presenting

Keep the stack on localhost; this MVP has no user authentication. Reset through the documented `POST /api/demo/reset` helper while `DEMO_MODE=true`. For live execution and analysis, use `live`, ensure Docker and `codereason-sandbox:py312` are available, and configure `OPENAI_API_KEY`. Otherwise use `fixture` and keep the **Demo Fixture** badge visible. Do not describe fixture, stored-live, or unavailable data as a live Docker or provider result.

## 0:00–0:20 — The grading gap

“Two programs can both be wrong for completely different reasons. Output-only grading misses correct structure, and an AI score without evidence is not trustworthy. CodeReason puts observable evidence before judgment and keeps the final decision with the instructor.”

Open the landing page and select **Try Demo Assignment**.

## 0:20–0:45 — Assignment and rubric

Show **Matrix Transformation Assignment** and its explicit execution contract:

- `FUNCTION`
- `make_matrix(data, rows, cols)`
- JSON argument schema
- `JSON_VALUE` comparison

Open the rubric builder. Briefly show the natural-language parser, then point out that generated criteria remain `DRAFT`. A person must select **Mark approved** on every criterion and then **Save assignment** before the rubric can be used for grading.

## 0:45–1:15 — Five submissions

Open the grading overview. Show the five bundled Python submissions and their distinct states:

- all tests pass
- correct nested-list approach with wrong indexing
- `IndexError`
- example-specific hardcoding
- missing entry function

Point to the provenance badges. Say whether results are live Docker/OpenAI output, stored live results, or demo fixtures.

## 1:15–1:50 — Evidence-backed partial credit

Open `idea_correct_output_wrong.py`. On the left, select the loop and nested-list AST findings. On the right, show failed output tests separately from Derived Analysis.

“The system does not claim to know what the student thought. The code shows evidence of a row-building approach, while execution shows an indexing defect. The analysis can suggest partial credit only by citing these Primary Evidence IDs.”

## 1:50–2:15 — Runtime versus logic

Compare `runtime_error.py` with the indexing submission. Show `IndexError` evidence and the different test-status vectors. Briefly open the hardcoded submission and show that a heuristic alone does not decide the score; hidden-test behavior corroborates it.

## 2:15–2:35 — Human decision

In a live-data demo, change one rubric score, enter a reason, and select **Approve human scores**. Show the AI suggestion and human-approved score as separate values. In fixture mode, show the already approved correct submission; editing another fixture only produces the local-simulation notice and does not create `final_total` or a server audit record. Mention that changing source, tests, or rubric later marks dependent analysis stale and returns the submission to review.

## 2:35–2:50 — Consistency review

Open the consistency page and inspect a **Potential issue** created by the server-side consistency operation or stored fixture. Emphasize that it is a review lead, not a finding, and never changes a grade. The current page lists existing issues; it does not trigger a new check.

## 2:50–3:00 — Export and close

Export CSV. Point out that unapproved submissions have a blank `final_total` and hidden-test details are excluded.

Close with: “CodeReason does not replace instructor judgment. It makes every proposed deduction inspectable: evidence before judgment, human approval before final grade.”
