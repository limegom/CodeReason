import { AlertTriangle, ArrowRight, CheckCircle2, FileCode2, GitCompareArrows, Plus } from "lucide-react";
import Link from "next/link";
import { EmptyState, ErrorState } from "@/components/data-state";
import { FixtureNotice } from "@/components/fixture-notice";
import { ProvenanceBadge } from "@/components/status-badge";
import { getAssignments } from "@/lib/api";

export const metadata = { title: "Assignments" };

export default async function AssignmentsPage() {
  const result = await getAssignments();
  if (!result.ok) {
    return <div className="shell page"><ErrorState message={result.error} code={result.code} /></div>;
  }

  const submissions = result.data.reduce((sum, assignment) => sum + assignment.submissions, 0);
  const pendingReview = result.data.reduce((sum, assignment) => sum + assignment.pendingReview, 0);
  const consistencyIssues = result.data.reduce((sum, assignment) => sum + assignment.consistencyIssues, 0);

  return (
    <div className="shell page stack" style={{ gap: 24 }}>
      <header className="row-between wrap">
        <div>
          <p className="eyebrow">Reviewer workspace</p>
          <h1 className="page-title">Assignments</h1>
          <p className="subtle" style={{ margin: 0 }}>Track evidence collection, review queues, and potential consistency issues.</p>
        </div>
        <Link className="button button-primary" href="/assignments/new"><Plus size={16} />New assignment</Link>
      </header>
      {result.notice ? <FixtureNotice>{result.notice}</FixtureNotice> : null}
      <div className="grid-4">
        <div className="card metric"><span className="section-label">Assignments</span><div className="metric-value">{result.data.length}</div></div>
        <div className="card metric"><span className="section-label">Submissions</span><div className="metric-value">{submissions}</div></div>
        <div className="card metric"><span className="section-label">Awaiting review</span><div className="metric-value" style={{ color: "var(--amber)" }}>{pendingReview}</div></div>
        <div className="card metric"><span className="section-label">Potential issues</span><div className="metric-value" style={{ color: "var(--red)" }}>{consistencyIssues}</div></div>
      </div>
      {result.data.length === 0 ? (
        <EmptyState
          title="No assignments yet"
          message="Create an assignment to define its execution contract, human-approved rubric, and deterministic tests."
          action={<Link className="button button-primary" href="/assignments/new">Create assignment</Link>}
        />
      ) : result.data.map((assignment) => (
        <article className="card card-strong card-pad" key={assignment.id}>
          <div className="row-between wrap" style={{ alignItems: "flex-start" }}>
            <div>
              <div className="row wrap">
                <ProvenanceBadge provenance={assignment.provenance} />
                <span className={`badge ${assignment.rubricReady ? "badge-green" : "badge-amber"}`}>
                  {assignment.rubricReady ? "Rubric approved" : "Rubric approval required"}
                </span>
              </div>
              <h2 style={{ margin: "17px 0 8px", fontSize: 25, letterSpacing: "-.035em" }}>{assignment.title}</h2>
              <p className="subtle" style={{ margin: 0, maxWidth: 720, lineHeight: 1.6 }}>{assignment.description}</p>
            </div>
            <Link className="button button-secondary" href={`/assignments/${assignment.id}/grading`}>Open grading <ArrowRight size={15} /></Link>
          </div>
          <div className="grid-3" style={{ marginTop: 26 }}>
            <div><div className="row"><FileCode2 size={16} /><strong>{assignment.executionMode}</strong></div><p className="subtle" style={{ margin: "7px 0 0", fontSize: 13 }}>{assignment.entryFunction ?? "standard input/output"}</p></div>
            <div><div className="row"><CheckCircle2 size={16} /><strong>{assignment.progress}% analyzed</strong></div><div className="progress-track" style={{ marginTop: 10 }}><div className="progress-value" style={{ width: `${assignment.progress}%` }} /></div></div>
            <div><div className="row"><GitCompareArrows size={16} /><strong>{assignment.comparisonMode}</strong></div><p className="subtle" style={{ margin: "7px 0 0", fontSize: 13 }}>Applied policy stored per TestResult</p></div>
          </div>
          {assignment.pendingReview ? <div className="notice" style={{ marginTop: 24 }}><AlertTriangle size={17} />{assignment.pendingReview} submissions need a human decision before final totals can be exported.</div> : null}
        </article>
      ))}
    </div>
  );
}
