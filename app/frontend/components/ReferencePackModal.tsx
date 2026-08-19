"use client";

import { FormEvent, useMemo, useState } from "react";
import { downloadActions, generationFailed, generationLoading, generationSucceeded, validateGenerationForm } from "@/lib/referencePackState.mjs";

type GenerationResponse = {
  generation_id: string;
  status: "completed" | "completed_with_warnings" | "failed";
  selected_reference_count: number;
  slide_count: number;
  pptx_download_url: string | null;
  pdf_download_url: string | null;
  manifest_download_url: string;
  warnings: string[];
};

type Props = {
  apiUrl: string;
  referenceIds: string[];
  defaultLanguage: "fr" | "en" | "ar";
  onClose: () => void;
};

function detail(body: unknown, fallback: string): string {
  if (typeof body === "object" && body && "detail" in body) {
    const value = (body as { detail: unknown }).detail;
    if (typeof value === "string") return value;
    if (typeof value === "object" && value && "message" in value) return String((value as { message: unknown }).message);
    return JSON.stringify(value);
  }
  return fallback;
}

export default function ReferencePackModal({ apiUrl, referenceIds, defaultLanguage, onClose }: Props) {
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({
    title: defaultLanguage === "fr" ? "Références pertinentes pour la mission" : defaultLanguage === "ar" ? "المراجع ذات الصلة بالفرصة" : "Relevant references for the opportunity",
    client_name: "",
    subtitle: defaultLanguage === "fr" ? "Sélection de références Devoteam" : defaultLanguage === "ar" ? "مجموعة مختارة من مراجع ديفوتيم" : "Selected Devoteam references",
    preparation_date: today,
    language: defaultLanguage,
    include_summary: true,
    include_reference_details: true,
    include_evidence_annex: true,
    include_logos: true,
    output_formats: ["pptx", "pdf"],
  });
  const [state, setState] = useState<{ status: string; result: GenerationResponse | null; error: string }>({ status: "idle", result: null, error: "" });
  const errors = useMemo(() => validateGenerationForm(form, referenceIds.length), [form, referenceIds.length]);

  function update(name: string, value: unknown) {
    setForm((current) => ({ ...current, [name]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (errors.length) return;
    setState(generationLoading());
    try {
      const response = await fetch(`${apiUrl}/api/reference-packs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, reference_ids: referenceIds }),
      });
      const body = await response.json() as unknown;
      if (!response.ok) throw new Error(detail(body, `Reference-pack generation failed (${response.status})`));
      setState(generationSucceeded(body as GenerationResponse));
    } catch (cause) {
      setState(generationFailed(cause instanceof Error ? cause.message : "Reference-pack generation failed."));
    }
  }

  const actions = downloadActions(state.result) as { kind: string; label: string; url: string }[];
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="reference-pack-modal" role="dialog" aria-modal="true" aria-labelledby="reference-pack-title">
        <header><div><p className="eyebrow">Deterministic generation</p><h2 id="reference-pack-title">Generate Reference Pack</h2></div><button type="button" onClick={onClose} aria-label="Close generation form">×</button></header>
        {state.status === "success" && state.result ? (
          <div className="generation-result">
            <span className="result-check" aria-hidden="true">✓</span>
            <h3>{state.result.status === "completed" ? "Reference pack ready" : "Pack ready with warnings"}</h3>
            <p>{state.result.selected_reference_count} selected reference{state.result.selected_reference_count === 1 ? "" : "s"} · {state.result.slide_count} slides</p>
            {state.result.warnings.length > 0 && <ul>{state.result.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
            <div className="download-actions">{actions.map((action) => <a key={action.kind} href={`${apiUrl}${action.url}`}>{action.label}</a>)}</div>
            <div className="result-actions"><button type="button" onClick={() => setState({ status: "idle", result: null, error: "" })}>Generate another pack</button><button type="button" onClick={onClose}>Done</button></div>
          </div>
        ) : (
          <form onSubmit={submit}>
            <div className="form-grid">
              <label className="wide">Presentation title<input value={form.title} maxLength={180} onChange={(event) => update("title", event.target.value)} required dir="auto" /></label>
              <label>Client or opportunity name<input value={form.client_name} maxLength={120} onChange={(event) => update("client_name", event.target.value)} required dir="auto" /></label>
              <label>Preparation date<input type="date" value={form.preparation_date} onChange={(event) => update("preparation_date", event.target.value)} required /></label>
              <label className="wide">Optional subtitle<input value={form.subtitle} maxLength={240} onChange={(event) => update("subtitle", event.target.value)} dir="auto" /></label>
              <label>Output language<select value={form.language} onChange={(event) => update("language", event.target.value)}><option value="fr">French</option><option value="en">English</option><option value="ar">Arabic</option></select></label>
              <div className="selected-count"><span>Selected references</span><strong>{referenceIds.length}</strong></div>
            </div>
            <fieldset><legend>Presentation sections</legend>
              <label><input type="checkbox" checked={form.include_summary} onChange={(event) => update("include_summary", event.target.checked)} /> Summary slides</label>
              <label><input type="checkbox" checked={form.include_reference_details} onChange={(event) => update("include_reference_details", event.target.checked)} /> One detailed slide per reference</label>
              <label><input type="checkbox" checked={form.include_evidence_annex} onChange={(event) => update("include_evidence_annex", event.target.checked)} /> Evidence annex</label>
              <label><input type="checkbox" checked={form.include_logos} onChange={(event) => update("include_logos", event.target.checked)} /> Client logos when approved locally</label>
            </fieldset>
            <fieldset><legend>Output formats</legend>
              <label><input type="radio" name="formats" checked={form.output_formats.join(",") === "pptx"} onChange={() => update("output_formats", ["pptx"])} /> PPTX</label>
              <label><input type="radio" name="formats" checked={form.output_formats.join(",") === "pdf"} onChange={() => update("output_formats", ["pdf"])} /> PDF</label>
              <label><input type="radio" name="formats" checked={form.output_formats.length === 2} onChange={() => update("output_formats", ["pptx", "pdf"])} /> PPTX + PDF</label>
            </fieldset>
            {state.error && <div className="modal-error" role="alert">{state.error}</div>}
            {errors.length > 0 && <p className="validation-copy">{errors[0]}</p>}
            <footer><button type="button" onClick={onClose}>Cancel</button><button type="submit" className="primary" disabled={state.status === "loading" || errors.length > 0}>{state.status === "loading" ? <><span className="spinner" aria-hidden="true" /> Generating PPTX and PDF…</> : "Generate pack"}</button></footer>
          </form>
        )}
      </section>
    </div>
  );
}
