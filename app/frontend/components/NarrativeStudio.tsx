"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import NarrativeReferenceEditor, { NarrativeReference, NarrativeReferenceMetadata } from "@/components/NarrativeReferenceEditor";
import NarrativeSectionEditor from "@/components/NarrativeSectionEditor";
import NarrativeValidationPanel, { NarrativeWarning } from "@/components/NarrativeValidationPanel";
import { SelectedReference } from "@/components/SelectionDrawer";
import {
  NARRATIVE_SESSION_KEY,
  canApproveNarrative,
  editableNarrative,
  generationRequest,
  studioStatus,
  validStudioSession,
} from "@/lib/narrativeStudioState.mjs";

type Language = "fr" | "en" | "ar";
type Tone = "executive" | "commercial" | "technical" | "concise";
type Audience = "executive" | "technical" | "procurement" | "mixed";
type DetailLevel = "short" | "medium" | "detailed";
type PresentationTemplateId = "orange_bank_compact" | "detailed_reference";
type SupportedText = { text: string; support_ids: string[] };
type UiFailure = { title?: string; message: string; technical: string };
type GenerationFailure = { unit: "section" | "reference"; reference_id?: string | null; index?: number; reason: string; message: string };
type ProgressUnit = {
  key: string;
  label: string;
  status: "pending" | "active" | "completed" | "failed";
  preview?: string;
};
type GenerationProgress = { message: string; units: ProgressUnit[] };

type Narrative = {
  section_intro: SupportedText;
  overall_storyline: SupportedText;
  why_these_references: SupportedText;
  references: NarrativeReference[];
};

type ReviewResponse = {
  narrative: Narrative;
  validation: { valid: boolean; export_blocked: boolean; export_eligible: boolean; warnings: NarrativeWarning[] };
  warnings: NarrativeWarning[];
  support_plan: unknown;
  reference_metadata: NarrativeReferenceMetadata[];
};

type PresentationResponse = {
  generation_id: string;
  status: "completed";
  template_id: PresentationTemplateId;
  selected_reference_count: number;
  slide_count: number;
  pptx_download_url: string;
  pdf_download_url: string;
  manifest_download_url: string;
  warnings: string[];
};

type Options = {
  opportunity_title: string;
  opportunity_description: string;
  requirements: string;
  target_language: Language;
  tone: Tone;
  audience: Audience;
  detail_level: DetailLevel;
};

type Props = {
  apiUrl: string;
  references: SelectedReference[];
  initialOpportunity: string;
  onClose: () => void;
};

function apiError(body: unknown, fallback: string): UiFailure {
  if (typeof body === "object" && body && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "object" && detail) {
      const record = detail as { reason?: unknown; message?: unknown };
      const reason = typeof record.reason === "string" ? record.reason : "";
      const technical = JSON.stringify(detail);
      const friendly: Record<string, { title?: string; message: string }> = {
        PPTX_CONTENT_OVERFLOW: { message: "This presentation contains more text than the selected template can safely display. Shorten the highlighted field and generate again." },
        REFERENCE_NARRATIVE_CONNECTION_TIMEOUT: {
          title: "The local AI service could not be reached.",
          message: "The connection to the local drafting service timed out. Check that Ollama is running and try again.",
        },
        REFERENCE_NARRATIVE_MODEL_UNAVAILABLE: { message: "The local AI drafting service is currently unavailable." },
        REFERENCE_NARRATIVE_PROVIDER_UNAVAILABLE: { message: "The local AI drafting service is currently unavailable." },
        REFERENCE_NARRATIVE_DISABLED: { message: "The local AI drafting service is currently unavailable." },
        EVIDENCE_SOURCE_NOT_FOUND: { message: "One selected reference does not have an available approved evidence page." },
        EVIDENCE_PAGE_NOT_APPROVED: { message: "One selected reference does not have an available approved evidence page." },
        PDF_CONVERSION_FAILED: { message: "The editable presentation was created, but its PDF could not be prepared safely." },
      };
      const friendlyError = friendly[reason];
      return {
        title: friendlyError?.title,
        message: friendlyError?.message || (typeof record.message === "string" ? record.message : fallback),
        technical,
      };
    }
    if (typeof detail === "string") return { message: detail, technical: detail };
  }
  return { message: fallback, technical: fallback };
}

function requestFailure(cause: unknown, fallback: string): UiFailure {
  if (typeof cause === "object" && cause && "message" in cause && "technical" in cause) {
    return cause as UiFailure;
  }
  const message = cause instanceof Error ? cause.message : fallback;
  return { message, technical: message };
}

export default function NarrativeStudio({ apiUrl, references, initialOpportunity, onClose }: Props) {
  const referenceIds = useMemo(() => references.map((reference) => reference.reference_id), [references]);
  const [options, setOptions] = useState<Options>({
    opportunity_title: initialOpportunity || "Selected-reference opportunity",
    opportunity_description: initialOpportunity,
    requirements: "",
    target_language: "fr",
    tone: "commercial",
    audience: "executive",
    detail_level: "medium",
  });
  const [review, setReview] = useState<ReviewResponse | null>(null);
  const [pendingNarrative, setPendingNarrative] = useState<Narrative | null>(null);
  const [loading, setLoading] = useState(false);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<UiFailure | null>(null);
  const [approved, setApproved] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [sessionReady, setSessionReady] = useState(false);
  const [pptxGenerating, setPptxGenerating] = useState(false);
  const [pptxError, setPptxError] = useState<UiFailure | null>(null);
  const [presentation, setPresentation] = useState<PresentationResponse | null>(null);
  const [templateId, setTemplateId] = useState<PresentationTemplateId>("detailed_reference");
  const [generationProgress, setGenerationProgress] = useState<GenerationProgress | null>(null);
  const [generationFailures, setGenerationFailures] = useState<GenerationFailure[]>([]);
  const generationInFlight = useRef(false);

  const request = useMemo(() => generationRequest(options, referenceIds), [options, referenceIds]);
  const status = studioStatus({ hasNarrative: Boolean(review), approved, dirty, warnings: review?.warnings ?? [] }) as "DRAFT" | "NEEDS REVIEW" | "READY FOR PRESENTATION";
  const approvalAllowed = canApproveNarrative(review?.warnings ?? [], validating) && Boolean(review) && generationFailures.length === 0;

  useEffect(() => {
    try {
      const saved = JSON.parse(window.sessionStorage.getItem(NARRATIVE_SESSION_KEY) || "null");
      if (validStudioSession(saved, referenceIds)) {
        setOptions(saved.options as Options);
        setReview(saved.review as ReviewResponse);
        setApproved(Boolean(saved.approved));
        setDirty(Boolean(saved.dirty));
        if (saved.template_id === "orange_bank_compact" || saved.template_id === "detailed_reference") {
          setTemplateId(saved.template_id);
        }
      }
    } catch {
      window.sessionStorage.removeItem(NARRATIVE_SESSION_KEY);
    } finally {
      setSessionReady(true);
    }
  }, [referenceIds]);

  useEffect(() => {
    if (!sessionReady) return;
    if (!review) {
      window.sessionStorage.removeItem(NARRATIVE_SESSION_KEY);
      return;
    }
    window.sessionStorage.setItem(NARRATIVE_SESSION_KEY, JSON.stringify({
      reference_ids: referenceIds,
      options,
      review,
      approved,
      dirty,
      template_id: templateId,
    }));
  }, [approved, dirty, options, referenceIds, review, sessionReady, templateId]);

  useEffect(() => {
    if (!pendingNarrative) return;
    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      setValidating(true);
      setError(null);
      try {
        const response = await fetch(`${apiUrl}/api/reference-narrative/validate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ generation_request: request, narrative: editableNarrative(pendingNarrative) }),
          signal: controller.signal,
        });
        const body = await response.json() as unknown;
        if (!response.ok) throw apiError(body, `Narrative validation failed (${response.status})`);
        setReview(body as ReviewResponse);
      } catch (cause) {
        if (!(cause instanceof DOMException && cause.name === "AbortError")) {
          setError(requestFailure(cause, "Narrative validation failed."));
        }
      } finally {
        setValidating(false);
        setPendingNarrative(null);
      }
    }, 450);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [apiUrl, pendingNarrative, request]);

  async function generateEntireNarrative() {
    if (generationInFlight.current) return;
    generationInFlight.current = true;
    setLoading(true);
    setError(null);
    setApproved(false);
    setPresentation(null);
    setPptxError(null);
    setGenerationFailures([]);
    setGenerationProgress({
      message: "Preparing AI-assisted draft…",
      units: [
        { key: "section", label: "Section narrative", status: "pending" },
        ...references.map((reference, index) => ({
          key: reference.reference_id,
          label: `Reference ${index + 1} of ${references.length} — ${reference.client || "Client"}`,
          status: "pending" as const,
        })),
      ],
    });
    try {
      const response = await fetch(`${apiUrl}/api/reference-narrative/generate-stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      if (!response.ok) {
        const body = await response.json() as unknown;
        throw apiError(body, `Narrative generation failed (${response.status})`);
      }
      if (!response.body) throw new Error("The progressive generation response was empty.");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const finalState: { current: { event: string; review?: ReviewResponse; failures?: GenerationFailure[] } | null } = { current: null };

      const applyEvent = (event: Record<string, unknown>) => {
        const eventName = String(event.event || "");
        if (eventName === "fatal") {
          throw apiError({ detail: { reason: event.reason, message: event.message } }, "Narrative generation failed.");
        }
        if (eventName === "completed" || eventName === "partial") {
          finalState.current = event as typeof finalState.current;
        }
        const serverMessage = typeof event.message === "string" ? event.message : undefined;
        const message = eventName === "validation_started"
          ? "Final validation…"
          : eventName === "unit_started" && event.unit === "section"
            ? "Preparing section narrative…"
            : serverMessage;
        const unitKey = event.unit === "section" ? "section" : typeof event.reference_id === "string" ? event.reference_id : "";
        if (message || unitKey) {
          setGenerationProgress((current) => {
            if (!current) return current;
            const status = eventName === "unit_started" ? "active" : eventName === "unit_completed" ? "completed" : eventName === "unit_failed" ? "failed" : null;
            const result = event.result as { section_intro?: SupportedText; headline?: SupportedText } | undefined;
            const preview = result?.section_intro?.text || result?.headline?.text;
            return {
              message: message || current.message,
              units: status && unitKey
                ? current.units.map((unit) => unit.key === unitKey ? { ...unit, status, preview: preview || unit.preview } : unit)
                : current.units,
            };
          });
        }
      };

      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) if (line.trim()) applyEvent(JSON.parse(line) as Record<string, unknown>);
        if (done) break;
      }
      if (buffer.trim()) applyEvent(JSON.parse(buffer) as Record<string, unknown>);
      const finalEvent = finalState.current;
      if (!finalEvent?.review) throw new Error("Progressive narrative generation ended before final validation.");

      const failures = finalEvent.failures || [];
      setReview(finalEvent.review);
      setGenerationFailures(failures);
      setDirty(failures.length > 0);
      if (failures.length === 0) setGenerationProgress(null);
      else setError({
        title: "Some narrative units need attention.",
        message: "Completed content was kept. Use the scoped regenerate action only for each failed unit.",
        technical: JSON.stringify(failures),
      });
    } catch (cause) {
      setError(requestFailure(cause, "The local AI drafting service is currently unavailable."));
    } finally {
      generationInFlight.current = false;
      setLoading(false);
    }
  }

  function queueEdit(narrative: Narrative) {
    if (!review) return;
    setReview({ ...review, narrative });
    setApproved(false);
    setDirty(true);
    setPendingNarrative(narrative);
    setPresentation(null);
    setPptxError(null);
  }

  function updateSection(field: "section_intro" | "overall_storyline" | "why_these_references", value: string) {
    if (!review) return;
    queueEdit({ ...review.narrative, [field]: { ...review.narrative[field], text: value } });
  }

  function updateReference(index: number, field: keyof NarrativeReference, value: SupportedText | SupportedText[]) {
    if (!review) return;
    const items = [...review.narrative.references];
    items[index] = { ...items[index], [field]: value };
    queueEdit({ ...review.narrative, references: items });
  }

  async function regenerate(scope: "section_intro" | "reference", referenceId?: string) {
    if (!review) return;
    setLoading(true);
    setError(null);
    setApproved(false);
    setPresentation(null);
    setPptxError(null);
    try {
      const response = await fetch(`${apiUrl}/api/reference-narrative/regenerate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          generation_request: request,
          narrative: editableNarrative(review.narrative),
          scope,
          reference_id: referenceId,
        }),
      });
      const body = await response.json() as unknown;
      if (!response.ok) throw apiError(body, `Narrative regeneration failed (${response.status})`);
      setReview(body as ReviewResponse);
      setGenerationFailures((current) => current.filter((failure) => (
        scope === "section_intro" ? failure.unit !== "section" : failure.reference_id !== referenceId
      )));
      setDirty(true);
    } catch (cause) {
      setError(requestFailure(cause, "Narrative regeneration failed."));
    } finally {
      setLoading(false);
    }
  }

  function option<K extends keyof Options>(name: K, value: Options[K]) {
    setOptions((current) => ({ ...current, [name]: value }));
    if (review) {
      setApproved(false);
      setDirty(true);
      setPresentation(null);
      setPptxError(null);
    }
  }

  async function generatePptx() {
    if (!review || status !== "READY FOR PRESENTATION" || !approved || dirty) return;
    setPptxGenerating(true);
    setPptxError(null);
    setPresentation(null);
    try {
      const response = await fetch(`${apiUrl}/api/reference-narrative/presentations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          generation_request: request,
          narrative: editableNarrative(review.narrative),
          template_id: templateId,
          approved: true,
          approved_narrative_status: "READY_FOR_PRESENTATION",
          approved_reference_ids: referenceIds,
        }),
      });
      const body = await response.json() as unknown;
      if (!response.ok) throw apiError(body, `Presentation export failed (${response.status})`);
      setPresentation(body as PresentationResponse);
    } catch (cause) {
      setPptxError(requestFailure(cause, "Presentation export failed."));
    } finally {
      setPptxGenerating(false);
    }
  }

  function chooseTemplate(value: PresentationTemplateId) {
    setTemplateId(value);
    setPresentation(null);
    setPptxError(null);
  }

  return (
    <div className="narrative-studio-backdrop" role="presentation">
      <section className="narrative-studio" role="dialog" aria-modal="true" aria-labelledby="narrative-studio-title">
        <header className="studio-header">
          <div><p className="eyebrow">Step 3 of 4 · Prepare narrative</p><h1 id="narrative-studio-title">Reference Narrative Studio</h1><p>Shape selected Devoteam experience into a concise, proposal-ready story.</p></div>
          <button type="button" onClick={onClose} aria-label="Close Narrative Studio">×</button>
        </header>
        <p className="studio-ai-note"><strong>AI-assisted draft.</strong> Review every statement before approval; unsupported content remains blocked.</p>

        <section className="studio-options">
          <div className="opportunity-fields">
            <p className="eyebrow">Opportunity brief</p>
            <label>Opportunity title<input dir="auto" maxLength={180} value={options.opportunity_title} onChange={(event) => option("opportunity_title", event.target.value)} /></label>
            <label>Opportunity description<textarea dir="auto" rows={3} maxLength={4000} value={options.opportunity_description} onChange={(event) => option("opportunity_description", event.target.value)} /></label>
            <label>Requirements <small>one per line</small><textarea dir="auto" rows={3} value={options.requirements} onChange={(event) => option("requirements", event.target.value)} /></label>
          </div>
          <div className="generation-options" aria-busy={loading}>
            <p className="eyebrow">Draft settings</p>
            <label>Language<select value={options.target_language} onChange={(event) => option("target_language", event.target.value as Language)}><option value="fr">French</option><option value="en">English</option><option value="ar">Arabic</option></select></label>
            <label>Tone<select value={options.tone} onChange={(event) => option("tone", event.target.value as Tone)}><option value="executive">Executive</option><option value="commercial">Commercial</option><option value="technical">Technical</option><option value="concise">Concise</option></select></label>
            <label>Audience<select value={options.audience} onChange={(event) => option("audience", event.target.value as Audience)}><option value="executive">Executive</option><option value="technical">Technical</option><option value="procurement">Procurement</option><option value="mixed">Mixed</option></select></label>
            <label>Detail level<select value={options.detail_level} onChange={(event) => option("detail_level", event.target.value as DetailLevel)}><option value="short">Short</option><option value="medium">Medium</option><option value="detailed">Detailed</option></select></label>
            <button type="button" className="primary" disabled={loading || !options.opportunity_title.trim()} onClick={() => void generateEntireNarrative()}>{loading ? <><span className="spinner" aria-hidden="true" /> Preparing AI-assisted draft…</> : review ? "Regenerate draft" : "Generate draft"}</button>
          </div>
        </section>

        <details className="studio-selected-references">
          <summary><span><strong>{references.length} selected reference{references.length === 1 ? "" : "s"}</strong><small>In narrative order</small></span></summary>
          <ol>
            {references.map((reference) => (
              <li key={reference.reference_id}>
                <strong dir="auto">{reference.display_title || reference.mission_title || "Devoteam reference"}</strong>
                <span>{[reference.client, reference.country, reference.period].filter(Boolean).join(" · ")}</span>
              </li>
            ))}
          </ol>
        </details>

        {error && <div className="studio-error" role="alert"><strong>{error.title || "Narrative request could not be completed."}</strong><span>{error.message}</span><details><summary>Technical details</summary><code>{error.technical}</code></details></div>}

        {generationProgress && (
          <section className="narrative-generation-progress" aria-live="polite" aria-busy={loading}>
            <div><span className="spinner dark" aria-hidden="true" /><strong>{generationProgress.message}</strong></div>
            <ol>
              {generationProgress.units.map((unit) => (
                <li key={unit.key} className={`progress-${unit.status}`}>
                  <span aria-hidden="true">{unit.status === "completed" ? "✓" : unit.status === "failed" ? "!" : unit.status === "active" ? "…" : "·"}</span>
                  <div>
                    <strong>{unit.label}</strong>
                    {unit.status === "active" && <small>Generating…</small>}
                    {unit.status === "pending" && <small>Waiting…</small>}
                    {unit.status === "failed" && <small>Generation failed — Retry reference below</small>}
                    {unit.preview && <p dir="auto">{unit.preview}</p>}
                  </div>
                </li>
              ))}
            </ol>
          </section>
        )}

        {review ? (
          <div className="studio-review">
            <NarrativeSectionEditor narrative={review.narrative} warnings={review.warnings} disabled={loading} onChange={updateSection} onRegenerateIntro={() => void regenerate("section_intro")} />
            <section className="reference-editor-list">
              {review.narrative.references.map((reference, index) => (
                <NarrativeReferenceEditor
                  key={reference.reference_id}
                  index={index}
                  reference={reference}
                  metadata={review.reference_metadata[index]}
                  warnings={review.warnings}
                  disabled={loading}
                  onScalarChange={(field, value) => updateReference(index, field, { ...reference[field], text: value })}
                  onListChange={(field, values) => updateReference(index, field, values.map((text) => ({ text, support_ids: [] })))}
                  onRegenerate={() => void regenerate("reference", reference.reference_id)}
                />
              ))}
            </section>
            <NarrativeValidationPanel warnings={review.warnings} status={status} validating={validating} />
            <footer className="studio-approval">
              <div><strong>Consultant approval</strong><p>Resolve required items, review notes and confirm the narrative before presentation generation.</p></div>
              <div className="studio-approval-actions">
                <button type="button" className="primary" disabled={!approvalAllowed} onClick={() => { setApproved(true); setDirty(false); setPresentation(null); setPptxError(null); }}>Approve narrative</button>
              </div>
            </footer>
            {status === "READY FOR PRESENTATION" && (
              <section className="presentation-format-picker" aria-labelledby="presentation-format-title">
                <div className="presentation-format-heading">
                  <div><p className="eyebrow">Step 4 of 4</p><h3 id="presentation-format-title">Choose a presentation format</h3></div>
                  <p>{references.length > 3 ? "Compact References may be easier to read for this selection." : "Detailed Case Study may provide more context for this selection."}</p>
                </div>
                <div className="presentation-format-options">
                  <label className={templateId === "orange_bank_compact" ? "selected" : ""}>
                    <input type="radio" name="presentation-format" value="orange_bank_compact" checked={templateId === "orange_bank_compact"} onChange={() => chooseTemplate("orange_bank_compact")} />
                    <span><strong>Compact References</strong><small>Orange Bank source style. Best for several concise examples, up to three references per summary slide.</small></span>
                  </label>
                  <label className={templateId === "detailed_reference" ? "selected" : ""}>
                    <input type="radio" name="presentation-format" value="detailed_reference" checked={templateId === "detailed_reference"} onChange={() => chooseTemplate("detailed_reference")} />
                    <span><strong>Detailed Case Study</strong><small>Challenges / Réalisations / Bénéfices. Best for one reference per detailed slide.</small></span>
                  </label>
                </div>
                <button type="button" className="primary pptx-action" disabled={pptxGenerating} onClick={() => void generatePptx()}>
                  {pptxGenerating ? <><span className="spinner" aria-hidden="true" /> Generating presentation… <span className="pdf-progress">Preparing PDF…</span></> : "Generate presentation"}
                </button>
              </section>
            )}
            {pptxError && <div className="studio-error studio-export-message" role="alert"><strong>The presentation pack could not be generated.</strong><span>{pptxError.message}</span><details><summary>Technical details</summary><code>{pptxError.technical}</code></details></div>}
            {presentation && (
              <div className="studio-pptx-success" role="status">
                <div><strong>Your presentation is ready</strong><p>{presentation.slide_count} reviewed narrative and source slides in the selected {presentation.template_id === "orange_bank_compact" ? "Compact References" : "Detailed Case Study"} format.</p></div>
                <div className="studio-download-actions">
                  <a href={`${apiUrl}${presentation.pptx_download_url}`}>Download editable PPTX</a>
                  <a href={`${apiUrl}${presentation.pdf_download_url}`}>Download PDF</a>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="studio-empty"><span aria-hidden="true">✦</span><h2>Prepare the first narrative draft</h2><p>Source facts stay locked. You can edit the commercial wording before validation and approval.</p></div>
        )}
      </section>
    </div>
  );
}
