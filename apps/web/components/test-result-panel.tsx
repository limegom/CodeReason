import { EyeOff, FlaskConical } from "lucide-react";
import type { TestResultDetail } from "@/lib/types";

function displayValue(value: unknown): string {
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

export function TestResultPanel({ results }: { results: TestResultDetail[] }) {
  return <section aria-labelledby="test-results-heading">
    <div className="row-between" style={{ marginBottom: 11 }}>
      <div><p className="section-label">Deterministic execution</p><h2 className="section-title" id="test-results-heading">Test results</h2></div>
      <span className="badge badge-gray">{results.length} results</span>
    </div>
    {results.length === 0 ? <div className="card card-pad"><p className="subtle" style={{ margin: 0 }}>No deterministic test results are available for this execution.</p></div> : <div className="stack" style={{ gap: 10 }}>
      {results.map((result) => <article className="card card-pad" key={result.id}>
        <div className="row-between wrap"><div className="row wrap"><FlaskConical size={15} /><strong>{result.testName ?? result.testCaseId}</strong><span className={`badge ${result.status === "PASSED" ? "badge-green" : "badge-red"}`}>{result.status}</span>{result.isHidden ? <span className="badge badge-amber"><EyeOff size={12} />Hidden · reviewer only</span> : <span className="badge badge-blue">Visible test</span>}</div><span className="badge badge-gray">{result.comparisonMode}</span></div>
        <div className="grid-2" style={{ marginTop: 14 }}>
          <div><p className="section-label">Input</p><pre className="code-block" style={{ maxHeight: 160, overflow: "auto" }}>{result.inputPayload === undefined ? "Not included in this reviewer record" : displayValue(result.inputPayload)}</pre></div>
          <div><p className="section-label">Expected</p><pre className="code-block" style={{ maxHeight: 160, overflow: "auto" }}>{result.expectedOutput === undefined ? "Not included in this reviewer record" : displayValue(result.expectedOutput)}</pre></div>
          <div><p className="section-label">Actual output</p><pre className="code-block" style={{ maxHeight: 160, overflow: "auto" }}>{result.actualOutput ?? "No output recorded"}</pre></div>
          <div><p className="section-label">Captured stdout</p><pre className="code-block" style={{ maxHeight: 160, overflow: "auto" }}>{result.stdout || "No stdout recorded"}</pre></div>
          <div><p className="section-label">Standard error</p><pre className="code-block" style={{ maxHeight: 160, overflow: "auto" }}>{result.stderr || "No stderr recorded"}</pre></div>
        </div>
        <div className="row wrap" style={{ marginTop: 12 }}><span className="badge badge-gray">Exit {result.exitCode ?? "n/a"}</span><span className="badge badge-gray">{result.durationMs === undefined ? "Duration n/a" : `${result.durationMs.toFixed(1)} ms`}</span>{result.errorCategory ? <span className="badge badge-red">{result.errorCategory}</span> : null}<span className="badge badge-gray">{result.visibility.replaceAll("_", " ")}</span></div>
      </article>)}
    </div>}
  </section>;
}
