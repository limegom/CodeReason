import { AlertTriangle, ArrowLeft, BrainCircuit, MessageSquareText } from "lucide-react";
import Link from "next/link";
import { CodeViewer } from "@/components/code-viewer";
import { ErrorState } from "@/components/data-state";
import { EvidencePanel } from "@/components/evidence-panel";
import { FixtureNotice } from "@/components/fixture-notice";
import { PrivacyDisclosure } from "@/components/privacy-disclosure";
import { ReviewScorePanel } from "@/components/review-score-panel";
import { ProvenanceBadge, StatusBadge } from "@/components/status-badge";
import { TestResultPanel } from "@/components/test-result-panel";
import { getSubmission } from "@/lib/api";

export default async function SubmissionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const result = await getSubmission(id);
  if (!result.ok) return <div className="shell page"><ErrorState title="Submission could not be loaded." message={result.error} code={result.code} /></div>;
  const submission = result.data;
  return <div className="shell page stack" style={{ gap: 22 }}>
    <Link className="row subtle" href={`/assignments/${submission.assignmentId}/grading`} style={{ fontSize: 13, fontWeight: 700 }}><ArrowLeft size={14} />Back to grading overview</Link>
    <header className="row-between wrap"><div><div className="row wrap"><p className="eyebrow" style={{ margin: 0 }}>Submission review</p><StatusBadge status={submission.status} /></div><h1 className="page-title" style={{ marginBottom: 7 }}>{submission.studentId}</h1><p className="subtle" style={{ margin: 0 }}>{submission.filename} · {submission.errorCategory}</p><div className="row wrap" style={{ marginTop: 10 }}><span className="subtle" style={{ fontSize: 12 }}>Input</span><ProvenanceBadge provenance={submission.provenance} /><span className="subtle" style={{ fontSize: 12 }}>Execution</span><ProvenanceBadge provenance={submission.executionProvenance ?? "UNAVAILABLE"} /><span className="subtle" style={{ fontSize: 12 }}>Derived Analysis</span><ProvenanceBadge provenance={submission.analysisProvenance ?? "UNAVAILABLE"} /></div></div><div style={{ textAlign: "right" }}><div className="subtle" style={{ fontSize: 12 }}>Final total</div><strong style={{ fontSize: 32 }}>{submission.finalTotal === undefined ? "Pending approval" : `${submission.finalTotal} / ${submission.totalScore}`}</strong></div></header>
    {result.notice ? <FixtureNotice>{result.notice}</FixtureNotice> : null}
    {submission.status === "STALE" ? <div className="notice"><AlertTriangle size={18} />Source, rubric, or test content changed after this analysis. Results are STALE, approval is blocked, and any prior HumanReview remains audit history only.</div> : null}

    <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.18fr) minmax(390px, .82fr)", gap: 20, alignItems: "start" }}>
      <div className="stack">
        <section><div className="row-between" style={{ marginBottom: 11 }}><div><p className="section-label">Immutable input</p><h2 className="section-title">Student source</h2></div><span className="badge badge-gray">Read only</span></div><CodeViewer source={submission.source} evidence={submission.evidence} /></section>
        <EvidencePanel evidence={submission.evidence} />
        <TestResultPanel results={submission.testResults} />
      </div>
      <ReviewScorePanel submission={submission} />
    </div>

    <section className="grid-2">
      <div className="card card-pad"><div className="row"><BrainCircuit size={17} /><div><p className="section-label" style={{ margin: 0 }}>Derived Analysis</p><h2 className="section-title" style={{ marginTop: 4 }}>Uncertainties</h2></div></div>{submission.uncertainties.length ? <ul className="subtle" style={{ paddingLeft: 20, lineHeight: 1.7 }}>{submission.uncertainties.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="subtle">No additional uncertainties were reported. Human verification is still required.</p>}</div>
      <div className="card card-pad"><div className="row"><MessageSquareText size={17} /><div><p className="section-label" style={{ margin: 0 }}>Student-safe language</p><h2 className="section-title" style={{ marginTop: 4 }}>Feedback preview</h2></div></div>{submission.feedback.length ? submission.feedback.map((item) => <div key={`${item.concept}-${item.nextStep}`} style={{ marginTop: 17 }}><strong>{item.concept}</strong><p className="subtle" style={{ fontSize: 13, lineHeight: 1.6 }}>{item.showsEvidenceOf} {item.likelyMisconception} {item.nextStep}</p></div>) : <p className="subtle">No student-visible feedback has been approved.</p>}</div>
    </section>
    <section className="card card-pad" aria-labelledby="review-history-heading">
      <div className="row-between wrap"><div><p className="section-label">Audit trail</p><h2 className="section-title" id="review-history-heading">Human review history</h2></div><span className="badge badge-gray">{submission.reviewHistory.length} decisions</span></div>
      {submission.reviewHistory.length ? <div className="stack" style={{ marginTop: 16, gap: 10 }}>{submission.reviewHistory.map((review) => <div className="card row-between wrap" style={{ padding: 13 }} key={review.id}><div><div className="row wrap"><strong>{review.reviewer}</strong><span className={`badge ${review.isCurrent ? "badge-green" : "badge-gray"}`}>{review.isCurrent ? "Current" : "Historical"}</span><span className="badge badge-blue">{review.status}</span></div><p className="subtle" style={{ margin: "7px 0 0", fontSize: 12 }}>{review.decisionReason ?? "No decision reason recorded."}</p></div><div style={{ textAlign: "right" }}><strong>{review.total} / {submission.totalScore}</strong><div className="subtle" style={{ fontSize: 11, marginTop: 4 }}>{review.createdAt.replace("T", " ").replace("Z", " UTC")}</div></div></div>)}</div> : <p className="subtle">No HumanReview decision has been recorded. AI suggestions do not create final grades.</p>}
    </section>
    <PrivacyDisclosure manifest={submission.externalDataManifest} provider={submission.provider} provenance={submission.analysisProvenance} />
  </div>;
}
