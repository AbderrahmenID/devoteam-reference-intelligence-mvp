import { warningCounts, warningsForField } from "@/lib/narrativeStudioState.mjs";

export type NarrativeWarning = {
  code: string;
  message: string;
  severity: "INFO" | "WARNING" | "BLOCKING";
  blocking: boolean;
  field_path: string | null;
  reference_id: string | null;
  support_ids: string[];
};

function fieldLabel(path: string | null): string {
  if (!path) return "Narrative";
  return path
    .replace(/^references\[(\d+)\]\./, (_value, index) => `Reference ${Number(index) + 1} · `)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (value) => value.toUpperCase());
}

function displayMessage(message: string): string {
  return message
    .replaceAll("&amp;", "&")
    .replaceAll("&quot;", "\"")
    .replace(/\s+/g, " ")
    .trim();
}

export function FieldValidation({ warnings, path }: { warnings: NarrativeWarning[]; path: string }) {
  const matching = warningsForField(warnings, path) as NarrativeWarning[];
  if (!matching.length) return <span className="field-validation valid">Ready</span>;
  const blocking = matching.some((warning) => warning.blocking);
  return (
    <details className={`field-validation ${blocking ? "blocking" : "warning"}`}>
      <summary>{blocking ? "Action required" : "Review suggested"}</summary>
      <ul className="field-warning-list">
        {matching.map((warning) => (
          <li className={`severity-${warning.severity.toLowerCase()}`} key={`${warning.code}-${warning.field_path}`}>
            <span>{displayMessage(warning.message)}</span>
            <small>{warning.code}</small>
          </li>
        ))}
      </ul>
    </details>
  );
}

type Props = {
  warnings: NarrativeWarning[];
  status: "DRAFT" | "NEEDS REVIEW" | "READY FOR PRESENTATION";
  validating: boolean;
};

export default function NarrativeValidationPanel({ warnings, status, validating }: Props) {
  const counts = warningCounts(warnings) as Record<string, number>;
  const blocking = counts.BLOCKING > 0;
  const statusLabel = status === "READY FOR PRESENTATION" ? "Ready for approval" : status === "NEEDS REVIEW" ? "Review needed" : "Draft";
  return (
    <section className="narrative-validation-panel" aria-live="polite">
      <div className="validation-summary">
        <span className={`validation-icon ${blocking ? "blocking" : "ready"}`} aria-hidden="true">{blocking ? "!" : "✓"}</span>
        <div>
          <p className="eyebrow">Narrative checks</p>
          <h3>{blocking ? `${counts.BLOCKING} item${counts.BLOCKING === 1 ? "" : "s"} must be resolved` : warnings.length ? "Ready with review notes" : "All checks passed"}</h3>
          <p>{counts.WARNING} review note{counts.WARNING === 1 ? "" : "s"} · {counts.INFO} information item{counts.INFO === 1 ? "" : "s"}</p>
        </div>
      </div>
      <span className={`narrative-status status-${status.toLowerCase().replaceAll(" ", "-")}`}>{statusLabel}</span>
      {validating && <span className="validation-refresh"><span className="spinner dark" aria-hidden="true" /> Checking edits…</span>}
      {warnings.length > 0 && (
        <details className="validation-details">
          <summary>View validation details</summary>
          <ul className="validation-summary-list">
            {warnings.map((warning) => (
              <li className={`severity-${warning.severity.toLowerCase()}`} key={`${warning.code}-${warning.field_path}-${warning.reference_id}`}>
                <strong>{fieldLabel(warning.field_path)}</strong>
                <span>{displayMessage(warning.message)}</span>
                <details><summary>Technical details</summary><code>{warning.code}{warning.support_ids.length ? ` · ${warning.support_ids.length} support item${warning.support_ids.length === 1 ? "" : "s"}` : ""}</code></details>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
