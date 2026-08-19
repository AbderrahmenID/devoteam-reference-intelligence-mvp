"use client";

import { useMemo, useRef, useState } from "react";
import { SelectedReference } from "@/components/SelectionDrawer";

type PresentationStyle = "orange_bank_compact" | "detailed_reference";
type OutputFormat = "pptx" | "pdf" | "both";
type UnitStatus = "waiting" | "active" | "complete";

type PresentationResponse = {
  generation_id: string;
  template_id: PresentationStyle;
  selected_reference_count: number;
  slide_count: number;
  pptx_download_url?: string | null;
  pdf_download_url?: string | null;
};

type ProgressUnit = { key: string; label: string; status: UnitStatus };

type Props = {
  apiUrl: string;
  references: SelectedReference[];
  opportunityContext: string;
  targetLanguage: "fr" | "en" | "ar";
  onClose: () => void;
};

export default function PresentationGeneratorModal({ apiUrl, references, opportunityContext, targetLanguage, onClose }: Props) {
  const [style, setStyle] = useState<PresentationStyle>("orange_bank_compact");
  const [output, setOutput] = useState<OutputFormat>("both");
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState<ProgressUnit[]>([]);
  const [message, setMessage] = useState("Generating your reference presentation");
  const [error, setError] = useState("");
  const [result, setResult] = useState<PresentationResponse | null>(null);
  const inFlight = useRef(false);
  const selectedIds = useMemo(() => references.map((reference) => reference.reference_id), [references]);

  function initialProgress(): ProgressUnit[] {
    return [
      { key: "prepare", label: "Preparing selected references", status: "waiting" },
      ...references.map((reference, index) => ({
        key: reference.reference_id,
        label: `Writing reference ${index + 1} of ${references.length} — ${reference.client || "Client"}`,
        status: "waiting" as const,
      })),
      { key: "fit", label: "Optimizing slide content", status: "waiting" },
      { key: "build", label: "Building presentation", status: "waiting" },
      ...(output === "pptx" ? [] : [{ key: "pdf", label: "Preparing PDF", status: "waiting" as const }]),
    ];
  }

  function updateUnit(key: string, status: UnitStatus) {
    setProgress((current) => current.map((unit) => unit.key === key ? { ...unit, status } : unit));
  }

  async function generate() {
    if (inFlight.current) return;
    inFlight.current = true;
    setGenerating(true);
    setError("");
    setResult(null);
    setProgress(initialProgress());
    try {
      const response = await fetch(`${apiUrl}/api/presentations/generate-stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          selected_reference_ids: selectedIds,
          opportunity_context: opportunityContext,
          target_language: targetLanguage,
          template_id: style,
          output_format: output,
        }),
      });
      if (!response.ok) throw new Error(`Presentation generation failed (${response.status}).`);
      if (!response.body) throw new Error("Presentation generation returned no progress stream.");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const finalState: { current: PresentationResponse | null } = { current: null };
      const applyEvent = (event: Record<string, unknown>) => {
        const eventName = String(event.event || "");
        if (typeof event.message === "string") setMessage(event.message);
        if (eventName === "fatal") throw new Error(typeof event.message === "string" ? event.message : "Presentation generation failed.");
        if (eventName === "started") updateUnit("prepare", "complete");
        if (eventName === "reference_started" && typeof event.reference_id === "string") updateUnit(event.reference_id, "active");
        if (eventName === "reference_completed" && typeof event.reference_id === "string") updateUnit(event.reference_id, "complete");
        if (eventName === "fit_started") updateUnit("fit", "active");
        if (eventName === "build_started") {
          updateUnit("fit", "complete");
          updateUnit("build", "active");
        }
        if (eventName === "pdf_started") {
          updateUnit("build", "complete");
          updateUnit("pdf", "active");
        }
        if (eventName === "completed") {
          setProgress((current) => current.map((unit) => ({ ...unit, status: "complete" })));
          finalState.current = event.response as PresentationResponse;
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
      if (!finalState.current) throw new Error("Presentation generation ended before the files were ready.");
      setResult(finalState.current);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Presentation generation failed.");
    } finally {
      inFlight.current = false;
      setGenerating(false);
    }
  }

  return (
    <div className="presentation-modal-backdrop" role="presentation" onMouseDown={generating ? undefined : onClose}>
      <section className="presentation-modal" role="dialog" aria-modal="true" aria-labelledby="presentation-modal-title" onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div><p className="eyebrow">{references.length} selected reference{references.length === 1 ? "" : "s"}</p><h2 id="presentation-modal-title">Generate reference presentation</h2></div>
          <button type="button" aria-label="Close" disabled={generating} onClick={onClose}>×</button>
        </header>

        {!generating && !result && (
          <div className="presentation-choices">
            <fieldset>
              <legend>Presentation style</legend>
              <label className={style === "orange_bank_compact" ? "selected" : ""}>
                <input type="radio" name="presentation-style" checked={style === "orange_bank_compact"} onChange={() => setStyle("orange_bank_compact")} />
                <span><strong>Compact References</strong><small>Orange Bank style · Multiple references per slide</small></span>
              </label>
              <label className={style === "detailed_reference" ? "selected" : ""}>
                <input type="radio" name="presentation-style" checked={style === "detailed_reference"} onChange={() => setStyle("detailed_reference")} />
                <span><strong>Detailed Reference</strong><small>Challenges / Réalisations / Bénéfices · One reference per slide</small></span>
              </label>
            </fieldset>
            <fieldset className="output-choices">
              <legend>Output</legend>
              <label><input type="radio" name="output-format" checked={output === "pptx"} onChange={() => setOutput("pptx")} /> PowerPoint (.pptx)</label>
              <label><input type="radio" name="output-format" checked={output === "pdf"} onChange={() => setOutput("pdf")} /> PDF</label>
              <label><input type="radio" name="output-format" checked={output === "both"} onChange={() => setOutput("both")} /> PowerPoint + PDF</label>
            </fieldset>
          </div>
        )}

        {(generating || progress.length > 0) && !result && (
          <div className="presentation-progress" aria-live="polite" aria-busy={generating}>
            <h3>{message}</h3>
            <ol>{progress.map((unit) => <li key={unit.key} className={unit.status}><span>{unit.status === "complete" ? "✓" : unit.status === "active" ? "●" : "○"}</span>{unit.label}</li>)}</ol>
          </div>
        )}

        {error && <div className="presentation-error" role="alert">{error}</div>}

        {result && (
          <div className="presentation-ready" role="status">
            <span aria-hidden="true">✓</span><h3>Your presentation is ready</h3><p>{result.slide_count} slide{result.slide_count === 1 ? "" : "s"} generated from the selected trusted references.</p>
            <div>
              {result.pptx_download_url && <a href={`${apiUrl}${result.pptx_download_url}`}>Download PowerPoint</a>}
              {result.pdf_download_url && <a href={`${apiUrl}${result.pdf_download_url}`}>Download PDF</a>}
            </div>
          </div>
        )}

        <footer>
          <button type="button" disabled={generating} onClick={onClose}>{result ? "Close" : "Cancel"}</button>
          {!result && <button type="button" className="primary" disabled={generating} onClick={() => void generate()}>{generating ? "Generating presentation…" : "Generate"}</button>}
        </footer>
      </section>
    </div>
  );
}
