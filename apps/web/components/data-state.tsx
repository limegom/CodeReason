import { AlertTriangle, Inbox } from "lucide-react";
import Link from "next/link";

export function ErrorState({
  title = "This data could not be loaded.",
  message,
  code,
}: {
  title?: string;
  message: string;
  code?: string;
}) {
  return (
    <section className="card card-strong card-pad stack" role="alert" style={{ maxWidth: 760 }}>
      <div className="row" style={{ alignItems: "flex-start" }}>
        <span className="brand-mark" style={{ background: "var(--red-soft)", color: "var(--red)", boxShadow: "none" }}>
          <AlertTriangle size={17} />
        </span>
        <div>
          <h2 className="section-title">{title}</h2>
          <p className="subtle" style={{ lineHeight: 1.6 }}>{message}</p>
          {code ? <span className="badge badge-red">{code.replaceAll("_", " ")}</span> : null}
        </div>
      </div>
      <div><Link className="button button-secondary" href="/assignments">Back to assignments</Link></div>
    </section>
  );
}

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: React.ReactNode;
}) {
  return (
    <section className="card card-pad" style={{ textAlign: "center", paddingBlock: 48 }}>
      <Inbox size={25} style={{ margin: "0 auto 14px", color: "var(--muted)" }} />
      <h2 className="section-title">{title}</h2>
      <p className="subtle" style={{ margin: "9px auto 18px", maxWidth: 560, lineHeight: 1.6 }}>{message}</p>
      {action}
    </section>
  );
}
