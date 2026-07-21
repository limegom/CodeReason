import { Braces, Eye, EyeOff, FileCode2, FlaskConical, LockKeyhole, TerminalSquare } from "lucide-react";
import type { Evidence } from "@/lib/types";

const icons = {
  TEST_RESULT: FlaskConical,
  EXECUTION_ERROR: TerminalSquare,
  AST_FINDING: Braces,
  STATIC_FINDING: FileCode2,
  SOURCE_CODE_LOCATION: FileCode2,
};

export function EvidencePanel({ evidence }: { evidence: Evidence[] }) {
  return (
    <section className="stack" aria-labelledby="primary-evidence-heading">
      <div>
        <p className="section-label">Observed facts</p>
        <h2 className="section-title" id="primary-evidence-heading">Primary Evidence</h2>
        <p className="subtle" style={{ margin: "7px 0 0", fontSize: 13 }}>
          Test, execution, AST, static, and source-location records only. AI interpretation is kept separate.
        </p>
      </div>
      {evidence.length === 0 ? <div className="card card-pad subtle">No Primary Evidence has been recorded for the latest execution.</div> : null}
      {evidence.map((item) => {
        const Icon = icons[item.kind];
        const Visibility = item.visibility === "INTERNAL" ? LockKeyhole : item.visibility === "REVIEWER_ONLY" ? EyeOff : Eye;
        return (
          <article className="card card-pad" id={item.id} key={item.id}>
            <div className="row-between" style={{ alignItems: "flex-start" }}>
              <div className="row" style={{ alignItems: "flex-start" }}>
                <span className="brand-mark" style={{ width: 31, height: 31, borderRadius: 9 }}><Icon size={15} /></span>
                <div>
                  <div className="row wrap">
                    <strong style={{ fontSize: 14 }}>{item.title}</strong>
                    <span className={`badge ${item.passed === true ? "badge-green" : item.passed === false ? "badge-red" : "badge-gray"}`}>
                      {item.passed === true ? "Pass" : item.passed === false ? "Fail" : "Finding"}
                    </span>
                  </div>
                  <p className="subtle" style={{ margin: "8px 0 0", fontSize: 13, lineHeight: 1.55 }}>{item.message}</p>
                </div>
              </div>
              <span className="badge badge-gray"><Visibility size={11} />{item.visibility.replaceAll("_", " ")}</span>
            </div>
            <div className="row wrap" style={{ marginTop: 13 }}>
              <code style={{ fontSize: 11, color: "var(--muted)" }}>{item.id}</code>
              {item.lineStart ? <span className="badge badge-gray">Lines {item.lineStart}–{item.lineEnd ?? item.lineStart}</span> : null}
              {item.testCase ? <span className="badge badge-gray">Test {item.testCase}</span> : null}
            </div>
          </article>
        );
      })}
    </section>
  );
}
