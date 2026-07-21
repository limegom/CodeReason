import { ErrorState } from "@/components/data-state";
import { FixtureNotice } from "@/components/fixture-notice";
import { UploadPanel } from "@/components/upload-panel";
import { getAssignmentOverview } from "@/lib/api";

export const metadata = { title: "Upload submissions" };

export default async function UploadPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const result = await getAssignmentOverview(id);
  if (!result.ok) return <div className="shell page"><ErrorState message={result.error} code={result.code} /></div>;
  return <div className="shell page"><header style={{ marginBottom: 24 }}><p className="eyebrow">Submission intake</p><h1 className="page-title">Upload untrusted code safely.</h1><p className="lede" style={{ fontSize: 17 }}>Source is immutable after upload. Any replacement creates a new revision and makes prior analysis stale.</p></header>{result.notice ? <FixtureNotice>{result.notice}</FixtureNotice> : null}<UploadPanel assignmentId={result.data.id} dataSource={result.source} provenance={result.data.provenance} /></div>;
}
