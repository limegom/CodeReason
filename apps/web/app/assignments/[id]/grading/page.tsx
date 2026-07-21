import { BrainCircuit, CheckCircle2, GitCompareArrows, TimerReset, Upload } from "lucide-react";
import Link from "next/link";
import { EmptyState, ErrorState } from "@/components/data-state";
import { FixtureNotice } from "@/components/fixture-notice";
import { GradingTable } from "@/components/grading-table";
import { ProvenanceBadge } from "@/components/status-badge";
import { getAssignmentOverview, getSubmissions } from "@/lib/api";

export const metadata = { title: "Grading overview" };

export default async function GradingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const assignmentResult = await getAssignmentOverview(id);
  if (!assignmentResult.ok) {
    return <div className="shell page"><ErrorState message={assignmentResult.error} code={assignmentResult.code} /></div>;
  }

  const assignment = assignmentResult.data;
  const result = await getSubmissions(assignment.id);
  if (!result.ok) {
    return <div className="shell page"><ErrorState title="Submissions could not be loaded." message={result.error} code={result.code} /></div>;
  }

  const approved = result.data.filter((item) => item.status === "APPROVED").length;
  const stale = result.data.filter((item) => item.status === "STALE").length;
  const finalTotalsReady = result.data.filter((item) => item.finalTotal !== undefined).length;

  return <div className="shell page stack" style={{ gap: 22 }}>
    <header className="row-between wrap" style={{ alignItems: "flex-end" }}>
      <div>
        <div className="row wrap"><p className="eyebrow" style={{ margin: 0 }}>Grading overview</p><ProvenanceBadge provenance={result.provenance} /></div>
        <h1 className="page-title">{assignment.title}</h1>
        <p className="subtle" style={{ margin: 0 }}>Primary Evidence is collected before a model produces separate Derived Analysis.</p>
      </div>
      <Link className="button button-secondary" href={`/assignments/${assignment.id}/consistency`}><GitCompareArrows size={15} />View consistency</Link>
    </header>
    {assignmentResult.notice ? <FixtureNotice>{assignmentResult.notice}</FixtureNotice> : null}
    {result.notice && result.notice !== assignmentResult.notice ? <FixtureNotice>{result.notice}</FixtureNotice> : null}
    <div className="grid-4">
      <div className="card metric"><div className="row"><BrainCircuit size={16} /><span className="section-label" style={{ margin: 0 }}>Submissions</span></div><div className="metric-value">{result.data.length}</div></div>
      <div className="card metric"><div className="row"><CheckCircle2 size={16} /><span className="section-label" style={{ margin: 0 }}>Human approved</span></div><div className="metric-value" style={{ color: "var(--blue)" }}>{approved}</div></div>
      <div className="card metric"><div className="row"><TimerReset size={16} /><span className="section-label" style={{ margin: 0 }}>Stale</span></div><div className="metric-value" style={{ color: "var(--amber)" }}>{stale}</div></div>
      <div className="card metric"><span className="section-label">Final totals ready</span><div className="metric-value">{finalTotalsReady} / {result.data.length}</div></div>
    </div>
    {result.data.length ? (
      <GradingTable submissions={result.data} assignmentId={assignment.id} totalScore={assignment.totalScore} />
    ) : (
      <EmptyState title="No submissions yet" message="Upload one or more Python files to create immutable submissions and enqueue deterministic execution." action={<Link className="button button-primary" href={`/assignments/${assignment.id}/upload`}><Upload size={15} />Upload submissions</Link>} />
    )}
  </div>;
}
