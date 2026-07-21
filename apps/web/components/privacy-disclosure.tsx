import { ShieldCheck } from "lucide-react";
import type { ExternalDataManifest, Provenance } from "@/lib/types";
import { ProvenanceBadge } from "./status-badge";

const plannedFields = [
  "assignment_description",
  "human_approved_rubric",
  "redacted_source_code",
  "sanitized_primary_evidence",
  "score_bounds",
];

export function PrivacyDisclosure({
  manifest,
  provider,
  provenance,
  preflightFields = plannedFields,
}: {
  manifest?: ExternalDataManifest;
  provider?: string;
  provenance?: Provenance;
  preflightFields?: string[];
}) {
  const fields = manifest?.fieldsSent ?? preflightFields;
  const status = manifest?.status ?? "PREFLIGHT_POLICY";
  const isFixture = provenance === "DEMO_FIXTURE";
  const wasSent = status === "SENT";
  const transmissionAttempted = status === "TRANSMISSION_FAILED";
  return (
    <aside className="card card-pad" style={{ borderColor: "color-mix(in srgb, var(--blue) 24%, var(--border))" }}>
      <div className="row" style={{ alignItems: "flex-start" }}>
        <span className="brand-mark" style={{ background: "var(--blue-soft)", color: "var(--blue)", boxShadow: "none" }}>
          <ShieldCheck size={17} />
        </span>
        <div style={{ minWidth: 0 }}>
          <div className="row wrap">
            <strong style={{ fontSize: 14 }}>External AI transmission disclosure</strong>
            {provenance ? <ProvenanceBadge provenance={provenance} /> : null}
            <span className={`badge ${status === "SENT" ? "badge-blue" : "badge-gray"}`}>{status.replaceAll("_", " ")}</span>
          </div>
          <p className="subtle" style={{ margin: "7px 0 0", fontSize: 13, lineHeight: 1.55 }}>
            {isFixture
              ? "This is a stored Demo Fixture manifest. No external provider call occurred for this record."
              : wasSent
                ? `This server-recorded manifest confirms which redacted fields were sent to ${provider ?? "the configured provider"}.`
                : transmissionAttempted
                  ? `The server attempted a provider call to ${provider ?? "the configured provider"}. These prepared fields may have been transmitted before the failure was recorded.`
                  : manifest
                    ? `This server-recorded manifest lists fields prepared for ${provider ?? "the configured provider"}; its status does not claim a successful transmission.`
                : "Before any provider call, the server redacts identifiers and secrets and shows the planned data categories. Redaction is a best-effort control."}
          </p>
          <p className="section-label" style={{ marginTop: 12 }}>{wasSent ? "Fields sent" : transmissionAttempted ? "Fields prepared for attempted transfer" : "Fields prepared or planned"}</p>
          <div className="row wrap" style={{ marginTop: 12 }}>
            {fields.length ? fields.map((field) => <span className="badge badge-blue" key={field}>{field.replaceAll("_", " ")}</span>) : <span className="badge badge-gray">No fields sent</span>}
          </div>
          {manifest ? (
            <div className="row wrap" style={{ marginTop: 10 }}>
              <span className="badge badge-gray">Redactions: {manifest.redactionCount ?? 0}</span>
              {manifest.redactionCategories.map((category) => <span className="badge badge-amber" key={category}>{category.replaceAll("_", " ")}</span>)}
              {manifest.hiddenTestValuesWithheld ? <span className="badge badge-green">Hidden values withheld</span> : null}
              {manifest.modelToolsEnabled === false ? <span className="badge badge-green">Model tools off</span> : null}
            </div>
          ) : null}
        </div>
      </div>
    </aside>
  );
}
