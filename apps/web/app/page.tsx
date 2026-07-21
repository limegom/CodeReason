import { ArrowRight, Braces, Eye, GitCompareArrows, ShieldCheck } from "lucide-react";
import Link from "next/link";

const principles = [
  { icon: Braces, title: "Observe before interpreting", body: "Tests, execution errors, AST, static findings, and source locations are the only Primary Evidence." },
  { icon: Eye, title: "Make every deduction inspectable", body: "Derived Analysis can suggest partial credit only by citing evidence already collected by deterministic checks." },
  { icon: ShieldCheck, title: "Keep final grades human", body: "AI suggestions remain separate. A final total exists only after an instructor approves the rubric scores." },
];

export default function LandingPage() {
  return (
    <div className="shell page">
      <section style={{ padding: "min(10vh, 92px) 0 54px" }}>
        <p className="eyebrow">Evidence before judgment</p>
        <h1 className="display">See more than whether code is wrong.</h1>
        <p className="lede">
          CodeReason combines reproducible execution evidence with rubric-bound GPT-5.6 analysis, then gives the final decision back to the professor or TA.
        </p>
        <div className="row wrap" style={{ marginTop: 28 }}>
          <Link className="button button-primary" href="/assignments/demo/grading">Try Demo Assignment <ArrowRight size={16} /></Link>
          <Link className="button button-secondary" href="/assignments/new">Create assignment</Link>
        </div>
      </section>

      <section className="card card-strong" style={{ overflow: "hidden", marginBottom: 24 }}>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.12fr) minmax(320px, .88fr)" }}>
          <div className="card-pad" style={{ padding: 30 }}>
            <div className="row-between wrap">
              <div>
                <p className="section-label">Submission · student-02</p>
                <h2 className="section-title">Correct structure. Wrong index.</h2>
              </div>
              <span className="badge badge-amber">Human review required</span>
            </div>
            <pre className="code-viewer" style={{ margin: "24px 0 0", padding: 20 }}><code>{`for row in range(rows):
    current = []
    for column in range(cols):
        index = row * cols + column + 1
        current.append(data[index])`}</code></pre>
          </div>
          <div style={{ padding: 30, color: "#eaf4f0", background: "#12231e" }}>
            <p className="section-label" style={{ color: "#75d9b0" }}>Evidence-linked partial credit</p>
            <div className="row-between" style={{ marginTop: 18 }}><span>2D list construction</span><strong style={{ fontSize: 25 }}>5 / 5</strong></div>
            <div className="row-between" style={{ marginTop: 14 }}><span>Value order</span><strong style={{ fontSize: 25, color: "#ff949b" }}>0 / 6</strong></div>
            <div className="divider" style={{ background: "rgba(255,255,255,.12)", margin: "22px 0" }} />
            <p style={{ color: "#9fb5ad", fontSize: 13, lineHeight: 1.65 }}>
              The nested loops show evidence of a matrix-building approach. Test evidence suggests an off-by-one defect. This is Derived Analysis, not a claim about the student’s private reasoning.
            </p>
            <div className="row wrap" style={{ marginTop: 18 }}><span className="badge badge-green">AST-14</span><span className="badge badge-red">TEST-07</span></div>
          </div>
        </div>
      </section>

      <section className="grid-3" style={{ marginTop: 24 }}>
        {principles.map(({ icon: Icon, title, body }) => (
          <article className="card card-pad" key={title}>
            <span className="brand-mark"><Icon size={17} /></span>
            <h2 className="section-title" style={{ marginTop: 22 }}>{title}</h2>
            <p className="subtle" style={{ lineHeight: 1.65, fontSize: 14 }}>{body}</p>
          </article>
        ))}
      </section>

      <section className="row-between wrap" style={{ marginTop: 62, paddingTop: 28, borderTop: "1px solid var(--border)" }}>
        <div className="row"><GitCompareArrows size={18} /><strong>Consistency checks raise potential issues, never automatic grade changes.</strong></div>
        <span className="subtle" style={{ fontSize: 13 }}>Python 3.12 MVP · human-in-the-loop</span>
      </section>
    </div>
  );
}

