import { FieldValidation, NarrativeWarning } from "@/components/NarrativeValidationPanel";

type SupportedText = { text: string; support_ids: string[] };
export type NarrativeReference = {
  reference_id: string;
  headline: SupportedText;
  short_description: SupportedText;
  challenge: SupportedText;
  devoteam_contribution: SupportedText;
  realisations: SupportedText[];
  benefits: SupportedText[];
  why_relevant_to_opportunity: SupportedText;
  warnings: string[];
};

export type NarrativeReferenceMetadata = {
  reference_id: string;
  mission_title: string;
  client: string;
  country: string;
  sector: string;
  period: string;
  offering: string;
};

type ScalarField = "headline" | "short_description" | "challenge" | "devoteam_contribution" | "why_relevant_to_opportunity";
type ListField = "realisations" | "benefits";

type Props = {
  index: number;
  reference: NarrativeReference;
  metadata: NarrativeReferenceMetadata;
  warnings: NarrativeWarning[];
  disabled: boolean;
  onScalarChange: (field: ScalarField, value: string) => void;
  onListChange: (field: ListField, value: string[]) => void;
  onRegenerate: () => void;
};

const scalarFields: { key: ScalarField; label: string; rows: number; placeholder: string }[] = [
  { key: "headline", label: "Commercial headline", rows: 2, placeholder: "Short, proposal-ready reference title" },
  { key: "short_description", label: "Short description", rows: 3, placeholder: "Not supported by the selected source; leave blank." },
  { key: "challenge", label: "Client challenge", rows: 3, placeholder: "Not supported by the selected source; leave blank." },
  { key: "devoteam_contribution", label: "Devoteam contribution", rows: 4, placeholder: "Not supported by the selected source; leave blank." },
  { key: "why_relevant_to_opportunity", label: "Relevance to this opportunity", rows: 3, placeholder: "Explain the fit only when supported by the selected source." },
];

function BulletEditor({ label, values, disabled, onChange, path, warnings }: {
  label: string;
  values: string[];
  disabled: boolean;
  onChange: (values: string[]) => void;
  path: string;
  warnings: NarrativeWarning[];
}) {
  return (
    <fieldset className="bullet-editor">
      <legend>{label}</legend>
      {values.length === 0 && <p>{label === "Bénéfices" ? "No sufficiently supported benefit identified." : "No sufficiently supported delivery identified."} You may leave this section empty.</p>}
      <div>
        {values.map((value, itemIndex) => (
          <label key={`${path}-${itemIndex}`}>
            <span aria-hidden="true">•</span>
            <textarea aria-label={`${label} bullet ${itemIndex + 1}`} dir="auto" rows={2} value={value} disabled={disabled} onChange={(event) => onChange(values.map((item, index) => index === itemIndex ? event.target.value : item))} />
            <button type="button" disabled={disabled} onClick={() => onChange(values.filter((_item, index) => index !== itemIndex))} aria-label={`Remove ${label} bullet ${itemIndex + 1}`}>Remove</button>
          </label>
        ))}
      </div>
      <button type="button" className="add-bullet" disabled={disabled} onClick={() => onChange([...values, ""])}>+ Add bullet</button>
      <FieldValidation warnings={warnings} path={path} />
    </fieldset>
  );
}

export default function NarrativeReferenceEditor({ index, reference, metadata, warnings, disabled, onScalarChange, onListChange, onRegenerate }: Props) {
  const root = `references[${index}]`;
  const referenceWarnings = warnings.filter((warning) => warning.field_path?.startsWith(root));
  const referenceBlocked = referenceWarnings.some((warning) => warning.blocking);
  return (
    <article className="narrative-editor-card reference-editor">
      <header>
        <div>
          <p className="eyebrow">Reference {index + 1}</p>
          <h2 dir="auto">{metadata.mission_title || "Devoteam reference"}</h2>
          <span className={`editor-status ${referenceBlocked ? "needs-review" : "complete"}`}>{referenceBlocked ? "Needs review" : "Complete"}</span>
        </div>
        <button type="button" className="secondary-action" onClick={onRegenerate} disabled={disabled}>Regenerate this reference</button>
      </header>
      <dl className="readonly-facts" aria-label="Verified reference information">
        {(["client", "country", "sector", "period", "offering"] as const).map((field) => <div key={field}><dt>{field}</dt><dd dir="auto">{metadata[field] || "Not provided in the source"}</dd></div>)}
      </dl>
      <p className="readonly-note">Reference details are verified from trusted source data. Narrative fields below remain editable until approval.</p>
      <div className="narrative-fields">
        {scalarFields.map((field) => (
          <label key={field.key} className={reference[field.key].text.trim() ? "has-content" : "is-empty"}>
            <span>{field.label}</span>
            <textarea dir="auto" rows={field.rows} value={reference[field.key].text} placeholder={field.placeholder} disabled={disabled} onChange={(event) => onScalarChange(field.key, event.target.value)} />
            {!reference[field.key].text.trim() && field.key !== "headline" && <small className="unsupported-field">No supported content available</small>}
            <FieldValidation warnings={warnings} path={`${root}.${field.key}`} />
          </label>
        ))}
        <BulletEditor label="Réalisations" values={reference.realisations.map((item) => item.text)} disabled={disabled} onChange={(values) => onListChange("realisations", values)} path={`${root}.realisations`} warnings={warnings} />
        <BulletEditor label="Bénéfices" values={reference.benefits.map((item) => item.text)} disabled={disabled} onChange={(values) => onListChange("benefits", values)} path={`${root}.benefits`} warnings={warnings} />
      </div>
    </article>
  );
}
