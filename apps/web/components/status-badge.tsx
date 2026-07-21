import { AlertTriangle, CheckCircle2, Clock3, FlaskConical, RefreshCw, XCircle } from "lucide-react";
import type { Provenance, SubmissionStatus } from "@/lib/types";

const statusStyle: Record<SubmissionStatus, { style: string; icon: typeof Clock3 }> = {
  PENDING: { style: "badge-gray", icon: Clock3 },
  RUNNING: { style: "badge-blue", icon: RefreshCw },
  ANALYZED: { style: "badge-green", icon: CheckCircle2 },
  REVIEW_REQUIRED: { style: "badge-amber", icon: AlertTriangle },
  APPROVED: { style: "badge-blue", icon: CheckCircle2 },
  FAILED: { style: "badge-red", icon: XCircle },
  STALE: { style: "badge-amber", icon: RefreshCw },
};

export function StatusBadge({ status }: { status: SubmissionStatus }) {
  const item = statusStyle[status] ?? statusStyle.PENDING;
  const Icon = item.icon;
  return <span className={`badge ${item.style}`}><Icon size={12} />{status.replaceAll("_", " ")}</span>;
}

export function ProvenanceBadge({ provenance }: { provenance: Provenance }) {
  if (provenance === "DEMO_FIXTURE") {
    return <span className="badge badge-amber"><FlaskConical size={12} />Demo fixture · not live</span>;
  }
  if (provenance === "UNAVAILABLE") return <span className="badge badge-red">Unavailable</span>;
  return <span className="badge badge-green"><CheckCircle2 size={12} />{provenance.replaceAll("_", " ")}</span>;
}
