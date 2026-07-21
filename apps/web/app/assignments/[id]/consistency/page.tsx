import { AlertTriangle, ArrowRight, Fingerprint, GitCompareArrows, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { EmptyState, ErrorState } from "@/components/data-state";
import { FixtureNotice } from "@/components/fixture-notice";
import { ProvenanceBadge } from "@/components/status-badge";
import { getAssignmentOverview, getConsistencyIssues } from "@/lib/api";

export default async function ConsistencyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const assignmentResult = await getAssignmentOverview(id);
  if (!assignmentResult.ok) return <div className="shell page"><ErrorState message={assignmentResult.error} code={assignmentResult.code} /></div>;
  const assignment = assignmentResult.data;
  const result = await getConsistencyIssues(assignment.id, assignment.provenance);
  if (!result.ok) return <div className="shell page"><ErrorState title="Consistency issues could not be loaded." message={result.error} code={result.code} /></div>;
  const highPriority = result.data.filter((issue) => issue.severity === "HIGH" && issue.status === "OPEN").length;

  return <div className="shell page stack" style={{ gap: 22 }}>
    <header className="row-between wrap">
      <div><div className="row wrap"><p className="eyebrow" style={{ margin: 0 }}>Consistency checker</p><ProvenanceBadge provenance={result.provenance} /></div><h1 className="page-title">Potential issues, not verdicts.</h1><p className="lede" style={{ fontSize: 17 }}>Deterministic fingerprints help reviewers compare like with like. CodeReason never changes a score automatically.</p></div>
      <Link className="button button-secondary" href={`/assignments/${assignment.id}/grading`}>Back to grading</Link>
    </header>
    {assignmentResult.notice ? <FixtureNotice>{assignmentResult.notice}</FixtureNotice> : null}
    {result.notice && result.notice !== assignmentResult.notice ? <FixtureNotice>{result.notice}</FixtureNotice> : null}
    <div className="grid-3"><div className="card metric"><span className="section-label">Potential issues</span><div className="metric-value">{result.data.length}</div></div><div className="card metric"><span className="section-label">High priority</span><div className="metric-value" style={{ color: "var(--red)" }}>{highPriority}</div></div><div className="card metric"><span className="section-label">Automatic changes</span><div className="metric-value">0</div></div></div>
    <div className="notice"><ShieldCheck size={18} />Fingerprints contain the test status vector, error category, AST feature summary, exception type, and entry-function signature status.</div>
    {result.data.length === 0 ? <EmptyState title="No potential issues" message="No consistency comparison currently requires reviewer attention. This does not replace human review of individual evidence." /> : <section className="stack">
      {result.data.map((issue) => <article className="card card-strong card-pad" key={issue.id}>
        <div className="row-between wrap" style={{ alignItems: "flex-start" }}><div><div className="row wrap"><span className={`badge ${issue.severity === "HIGH" ? "badge-red" : issue.severity === "MEDIUM" ? "badge-amber" : "badge-gray"}`}><AlertTriangle size={12} />{issue.severity}</span><span className="badge badge-gray">{issue.status}</span></div><h2 className="section-title" style={{ marginTop: 16, maxWidth: 850 }}>{issue.description}</h2></div><GitCompareArrows size={22} /></div>
        <div className="grid-2" style={{ marginTop: 22 }}>
          <div className="card" style={{ padding: 15 }}><div className="row"><Fingerprint size={15} /><strong style={{ fontSize: 13 }}>Comparison fingerprint</strong></div><code className="subtle" style={{ display: "block", marginTop: 10, fontSize: 11, lineHeight: 1.6, overflowWrap: "anywhere" }}>{issue.fingerprint}</code><p className="subtle" style={{ fontSize: 12 }}>Tests: {issue.testStatusVector.join(", ") || "unavailable"}</p></div>
          <div className="card" style={{ padding: 15 }}><strong style={{ fontSize: 13 }}>Fingerprint context</strong><p className="subtle" style={{ margin: "9px 0 0", fontSize: 13, lineHeight: 1.55 }}>Error: {issue.errorCategory ?? "none"} · Exception: {issue.exceptionType ?? "none"} · Signature: {issue.signatureStatus ?? "unknown"}</p><code className="subtle" style={{ display: "block", marginTop: 10, fontSize: 11 }}>{JSON.stringify(issue.astFeatureSummary)}</code></div>
        </div>
        <div className="row-between wrap" style={{ marginTop: 18 }}><div className="row wrap"><span className="badge badge-blue">{issue.submissionId}</span>{issue.comparedSubmissionId ? <span className="badge badge-blue">{issue.comparedSubmissionId}</span> : null}</div><div className="row"><Link className="button button-secondary" href={`/submissions/${issue.submissionId}`}>Review submission <ArrowRight size={14} /></Link>{issue.comparedSubmissionId ? <Link className="button button-secondary" href={`/submissions/${issue.comparedSubmissionId}`}>Review comparison <ArrowRight size={14} /></Link> : null}</div></div>
      </article>)}
    </section>}
  </div>;
}
