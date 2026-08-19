import test from "node:test";
import assert from "node:assert/strict";

import { downloadActions, generationFailed, generationLoading, generationSucceeded, validateGenerationForm } from "../lib/referencePackState.mjs";

const validForm = {
  title: "Références pertinentes",
  client_name: "Client",
  preparation_date: "2026-08-03",
  language: "fr",
  include_summary: true,
  include_reference_details: true,
  include_evidence_annex: true,
  output_formats: ["pptx", "pdf"],
};

test("generation is disabled for zero selections and invalid forms", () => {
  assert.match(validateGenerationForm(validForm, 0)[0], /Select at least one/);
  assert.match(validateGenerationForm({ ...validForm, title: "" }, 1)[0], /title is required/i);
  assert.match(validateGenerationForm({ ...validForm, include_summary: false, include_reference_details: false, include_evidence_annex: false }, 1)[0], /section/i);
  assert.deepEqual(validateGenerationForm(validForm, 3), []);
});

test("generation progress, success and error states are precise", () => {
  assert.equal(generationLoading().status, "loading");
  assert.equal(generationSucceeded({ generation_id: "one" }).status, "success");
  assert.deepEqual(generationFailed("evidence is not displayable"), { status: "error", result: null, error: "evidence is not displayable" });
});

test("download actions expose only returned artifacts", () => {
  const actions = downloadActions({
    pptx_download_url: "/download/pptx",
    pdf_download_url: null,
    manifest_download_url: "/download/manifest",
  });
  assert.deepEqual(actions.map((action) => action.kind), ["pptx", "manifest"]);
  assert.equal(actions[0].url, "/download/pptx");
});
