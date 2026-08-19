import { FieldValidation, NarrativeWarning } from "@/components/NarrativeValidationPanel";

type SupportedText = { text: string; support_ids: string[] };
export type SectionNarrative = {
  section_intro: SupportedText;
  overall_storyline: SupportedText;
  why_these_references: SupportedText;
};

type Props = {
  narrative: SectionNarrative;
  warnings: NarrativeWarning[];
  disabled: boolean;
  onChange: (field: keyof SectionNarrative, value: string) => void;
  onRegenerateIntro: () => void;
};

const fields: { key: keyof SectionNarrative; label: string }[] = [
  { key: "section_intro", label: "Section introduction" },
  { key: "overall_storyline", label: "Overall storyline" },
  { key: "why_these_references", label: "Why these references" },
];

export default function NarrativeSectionEditor({ narrative, warnings, disabled, onChange, onRegenerateIntro }: Props) {
  return (
    <section className="narrative-editor-card section-editor">
      <header><div><p className="eyebrow">Opening narrative</p><h2>Portfolio storyline</h2></div><button type="button" className="secondary-action" onClick={onRegenerateIntro} disabled={disabled}>Regenerate introduction</button></header>
      <div className="narrative-fields">
        {fields.map((field) => (
          <label key={field.key}>
            <span>{field.label}</span>
            <textarea dir="auto" rows={4} value={narrative[field.key].text} placeholder="No supported content available; leave blank." disabled={disabled} onChange={(event) => onChange(field.key, event.target.value)} />
            <FieldValidation warnings={warnings} path={field.key} />
          </label>
        ))}
      </div>
    </section>
  );
}
