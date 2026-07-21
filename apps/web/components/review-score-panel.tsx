"use client";

import { AlertTriangle, Check, LockKeyhole, RotateCcw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ApiMutationError, approveReview } from "@/lib/client-api";
import type { Submission } from "@/lib/types";

function initialScores(submission: Submission): Record<string, number> {
  return Object.fromEntries(submission.scores.map((score) => [score.rubricId, score.humanScore ?? score.aiSuggestedScore ?? 0]));
}

export function ReviewScorePanel({ submission }: { submission: Submission }) {
  const router = useRouter();
  const [scores, setScores] = useState<Record<string, number>>(() => initialScores(submission));
  const [reviewer, setReviewer] = useState("Instructor");
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const total = useMemo(() => Object.values(scores).reduce((sum, value) => sum + value, 0), [scores]);
  const confidenceValues = submission.scores.map((score) => score.modelReportedConfidence).filter((value): value is number => value !== null);
  const minConfidence = confidenceValues.length ? Math.min(...confidenceValues) : undefined;
  const needsReview = submission.reviewRequired || submission.status === "STALE" || submission.scores.some((score) => score.manualReviewRequired) || minConfidence === undefined || minConfidence < 0.7;
  const approvalBlocked = submission.status === "STALE" || !submission.rubricReady || submission.scores.length === 0;

  async function approve() {
    if (saving || approvalBlocked) return;
    const changed = submission.scores.some((score) => score.aiSuggestedScore === null || scores[score.rubricId] !== score.aiSuggestedScore);
    if (!reviewer.trim()) {
      setError("Reviewer name is required for the audit history.");
      return;
    }
    if (changed && !reason.trim()) {
      setError("A reviewer reason is required when a human score differs from the AI suggestion.");
      return;
    }

    setSaving(true);
    setError(null);
    setNotice(null);
    if (submission.dataSource === "LOCAL_FIXTURE" || submission.provenance === "DEMO_FIXTURE") {
      setNotice("Demo Fixture review was simulated locally. No final grade or server audit record was created.");
      setSaving(false);
      return;
    }

    try {
      await approveReview(submission.id, {
        reviewer: reviewer.trim(),
        ai_analysis_id: submission.analysisId ?? null,
        status: "APPROVED",
        decision_reason: reason.trim() || null,
        scores: submission.scores.map((score) => ({
          rubric_criterion_id: score.rubricId,
          awarded_score: scores[score.rubricId],
          reason: score.aiSuggestedScore === null || scores[score.rubricId] !== score.aiSuggestedScore ? reason.trim() : null,
        })),
      });
      setNotice("Human review approved. The server created the current audit record and final total.");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ApiMutationError ? `${caught.message} (${caught.code})` : "The review could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return <aside className="stack" aria-labelledby="derived-analysis-heading">
    {error ? <div className="notice" role="alert"><AlertTriangle size={17} />{error}</div> : null}
    {notice ? <div className="notice" role="status">{notice}</div> : null}
    <div className="card card-strong card-pad">
      <div className="row-between"><div><p className="section-label">Advisory, not evidence</p><h2 className="section-title" id="derived-analysis-heading">Derived Analysis</h2></div><span className="badge badge-blue">{submission.modelName ?? "Model unavailable"}</span></div>
      <div className="row-between" style={{ marginTop: 22 }}><div><div className="subtle" style={{ fontSize: 12 }}>AI suggested total</div><strong style={{ fontSize: 30 }}>{submission.aiSuggestedTotal === null ? "Unavailable" : `${submission.aiSuggestedTotal} / ${submission.totalScore}`}</strong></div><div style={{ textAlign: "right" }}><div className="subtle" style={{ fontSize: 12 }}>Human decision</div><strong style={{ fontSize: 30, color: "var(--blue)" }}>{total} / {submission.totalScore}</strong></div></div>
      <p className="subtle" style={{ fontSize: 12, lineHeight: 1.55 }}>The model-reported confidence below is not an objective probability. It only helps prioritize review.</p>
      {minConfidence === undefined ? <p className="subtle" style={{ fontSize: 12 }}>Model-reported confidence is unavailable.</p> : <><div className="progress-track"><div className="progress-value" style={{ width: `${Math.round(minConfidence * 100)}%`, background: minConfidence < 0.7 ? "var(--amber)" : "var(--green)" }} /></div><div className="row-between" style={{ marginTop: 7, fontSize: 12 }}><span>Lowest model-reported confidence</span><strong>{Math.round(minConfidence * 100)}%</strong></div></>}
      {needsReview ? <div className="notice" style={{ marginTop: 18 }}><AlertTriangle size={17} />Review is required because evidence may be missing or conflicting, execution may be unavailable, confidence may be low, or analysis may be stale.</div> : null}
    </div>

    {submission.scores.map((score) => <article className="card card-pad" key={score.rubricId}>
      <div className="row-between" style={{ alignItems: "flex-start" }}><div><strong style={{ fontSize: 14 }}>{score.title}</strong><div className="subtle" style={{ marginTop: 4, fontSize: 12 }}>{score.rubricId} · max {score.maxScore}</div></div><span className={`badge ${score.manualReviewRequired ? "badge-amber" : "badge-green"}`}>{score.manualReviewRequired ? "Review" : "Evidence linked"}</span></div>
      <p className="subtle" style={{ fontSize: 13, lineHeight: 1.55 }}>{score.reason}</p>
      <div className="row wrap">{score.evidenceIds.length ? score.evidenceIds.map((id) => <a className="badge badge-gray" href={`#${id}`} key={id}>{id}</a>) : <span className="badge badge-amber">Missing linked evidence</span>}</div>
      <div className="grid-2" style={{ marginTop: 16 }}><div className="field"><label>AI suggestion</label><input className="input" value={score.aiSuggestedScore ?? "Unavailable"} disabled /></div><div className="field"><label htmlFor={`human-${score.rubricId}`}>Human score</label><input className="input" id={`human-${score.rubricId}`} type="number" min={0} max={score.maxScore} step="0.5" value={scores[score.rubricId]} onChange={(event) => setScores((current) => ({ ...current, [score.rubricId]: Math.max(0, Math.min(score.maxScore, Number(event.target.value))) }))} /></div></div>
    </article>)}

    <div className="card card-pad stack">
      <div className="field"><label htmlFor="reviewer-name">Reviewer</label><input className="input" id="reviewer-name" value={reviewer} onChange={(event) => setReviewer(event.target.value)} /></div>
      <div className="field"><label htmlFor="review-reason">Reviewer reason</label><textarea className="textarea" id="review-reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Required when changing an AI suggestion." /></div>
      <div className="row-between wrap"><button className="button button-secondary" type="button" onClick={() => { setScores(initialScores(submission)); setReason(""); setError(null); }}><RotateCcw size={15} />Reset edits</button><button className="button button-primary" type="button" onClick={approve} disabled={approvalBlocked || saving}><Check size={15} />{saving ? "Approving…" : "Approve human scores"}</button></div>
      {submission.status === "STALE" ? <div className="row subtle" style={{ fontSize: 12 }}><LockKeyhole size={14} />Re-run analysis before approval. Previous HumanReview records remain in audit history.</div> : null}
      {!submission.rubricReady ? <div className="row subtle" style={{ fontSize: 12 }}><LockKeyhole size={14} />Every active rubric criterion must be HUMAN_APPROVED before grading.</div> : null}
    </div>
  </aside>;
}
