export function validateGenerationForm(form, selectedCount) {
  const errors = [];
  if (!String(form.title || "").trim()) errors.push("Presentation title is required.");
  if (!String(form.client_name || "").trim()) errors.push("Client or opportunity name is required.");
  if (!form.preparation_date) errors.push("Preparation date is required.");
  if (!['fr', 'en', 'ar'].includes(form.language)) errors.push("A supported output language is required.");
  if (selectedCount < 1) errors.push("Select at least one reference.");
  if (!form.include_summary && !form.include_reference_details && !form.include_evidence_annex) errors.push("Select at least one presentation section.");
  if (!Array.isArray(form.output_formats) || form.output_formats.length === 0) errors.push("Select at least one output format.");
  return errors;
}

export function generationLoading() {
  return { status: "loading", result: null, error: "" };
}

export function generationSucceeded(result) {
  return { status: "success", result, error: "" };
}

export function generationFailed(message) {
  return { status: "error", result: null, error: message };
}

export function downloadActions(result) {
  if (!result) return [];
  return [
    result.pptx_download_url && { kind: "pptx", label: "Download editable PPTX", url: result.pptx_download_url },
    result.pdf_download_url && { kind: "pdf", label: "Download PDF", url: result.pdf_download_url },
    result.manifest_download_url && { kind: "manifest", label: "Download manifest", url: result.manifest_download_url },
  ].filter(Boolean);
}
