import { ArrowRight, FileCode2, FlaskConical, GitCompareArrows, Upload } from "lucide-react";
import Link from "next/link";
import { ErrorState } from "@/components/data-state";
import { FixtureNotice } from "@/components/fixture-notice";
import { ProvenanceBadge } from "@/components/status-badge";
import { getAssignmentOverview } from "@/lib/api";

export default async function AssignmentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const result = await getAssignmentOverview(id);
  if (!result.ok) return <div className="shell page"><ErrorState message={result.error} code={result.code} /></div>;
  const assignment = result.data;

  return <div className="shell page stack" style={{ gap: 24 }}>
    <header>
      <div className="row wrap"><p className="eyebrow" style={{ margin: 0 }}>Assignment detail</p><ProvenanceBadge provenance={assignment.provenance} /></div>
      <h1 className="page-title">{assignment.title}</h1>
      <p className="lede" style={{ fontSize: 17 }}>{assignment.description}</p>
    </header>
    {result.notice ? <FixtureNotice>{result.notice}</FixtureNotice> : null}
    <div className="grid-3">
      <article className="card card-pad"><FileCode2 size={19} /><h2 className="section-title" style={{ marginTop: 17 }}>Execution contract</h2><p className="subtle">{assignment.executionMode} · {assignment.entryFunction ?? "standard input/output"} · {assignment.comparisonMode}</p></article>
      <article className="card card-pad"><FlaskConical size={19} /><h2 className="section-title" style={{ marginTop: 17 }}>Submissions</h2><p className="subtle">Upload `.py` files and run deterministic checks before AI analysis.</p><Link className="button button-secondary" href={`/assignments/${assignment.id}/upload`}><Upload size={15} />Upload</Link></article>
      <article className="card card-pad"><GitCompareArrows size={19} /><h2 className="section-title" style={{ marginTop: 17 }}>Review workspace</h2><p className="subtle">Inspect evidence, make human decisions, then check potential inconsistencies.</p><Link className="button button-primary" href={`/assignments/${assignment.id}/grading`}>Open grading <ArrowRight size={15} /></Link></article>
    </div>
  </div>;
}
