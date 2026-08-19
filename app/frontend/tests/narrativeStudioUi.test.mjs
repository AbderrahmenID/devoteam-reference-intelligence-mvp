import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (name) => readFileSync(join(root, "components", name), "utf8");
const studio = read("NarrativeStudio.tsx");
const section = read("NarrativeSectionEditor.tsx");
const reference = read("NarrativeReferenceEditor.tsx");
const validation = read("NarrativeValidationPanel.tsx");

test("studio covers generation loading and clear local-model errors", () => {
  assert.match(studio, /\/api\/reference-narrative\/generate/);
  assert.match(studio, /Preparing AI-assisted draft…/);
  assert.match(studio, /aria-busy=\{loading\}/);
  assert.match(studio, /role="alert"/);
  assert.match(studio, /local AI drafting service is currently unavailable/i);
});

test("generation waits for the backend and blocks duplicate Generate clicks", () => {
  const generation = studio.match(/async function generateEntireNarrative\(\) \{[\s\S]*?\n  \}/)?.[0] || "";
  assert.doesNotMatch(generation, /AbortController|signal:|setTimeout/);
  assert.match(studio, /const generationInFlight = useRef\(false\)/);
  assert.match(generation, /if \(generationInFlight\.current\) return/);
  assert.match(generation, /generationInFlight\.current = true/);
  assert.match(generation, /generationInFlight\.current = false/);
  assert.match(studio, /disabled=\{loading \|\| !options\.opportunity_title\.trim\(\)\}/);
});

test("connection timeout uses professional copy and keeps technical details collapsed", () => {
  assert.match(studio, /REFERENCE_NARRATIVE_CONNECTION_TIMEOUT/);
  assert.match(studio, /The local AI service could not be reached\./);
  assert.match(studio, /connection to the local drafting service timed out/i);
  assert.match(studio, /<details><summary>Technical details<\/summary>/);
});

test("generation streams section-first progress and keeps isolated failures", () => {
  assert.match(studio, /\/api\/reference-narrative\/generate-stream/);
  assert.match(studio, /Preparing section narrative/);
  assert.match(studio, /Reference \$\{index \+ 1\} of \$\{references\.length\}/);
  assert.match(studio, /Final validation/);
  assert.match(studio, /Generation failed — Retry reference below/);
  assert.match(studio, /Generating…/);
  assert.match(studio, /Waiting…/);
  assert.match(studio, /setGenerationFailures/);
  assert.match(studio, /generationFailures\.length === 0/);
});

test("opportunity and all generation controls are rendered", () => {
  assert.match(studio, /Opportunity title/);
  assert.match(studio, /Opportunity description/);
  assert.match(studio, /Requirements/);
  for (const label of ["French", "English", "Arabic", "Executive", "Commercial", "Technical", "Concise", "Procurement", "Mixed", "Short", "Medium", "Detailed"]) {
    assert.match(studio, new RegExp(`>${label}<`));
  }
});

test("studio opens with the selected references in narrative order", () => {
  assert.match(studio, /studio-selected-references/);
  assert.match(studio, /references\.map/);
  assert.match(studio, /In narrative order/);
});

test("section and reference editors render every editable field", () => {
  assert.match(section, /Section introduction/);
  assert.match(section, /Overall storyline/);
  assert.match(section, /Why these references/);
  for (const label of ["Commercial headline", "Short description", "Client challenge", "Devoteam contribution", "Réalisations", "Bénéfices", "Relevance to this opportunity"]) {
    assert.match(reference, new RegExp(label));
  }
});

test("deterministic facts are read-only and never emitted as form controls", () => {
  assert.match(reference, /Verified reference information/);
  assert.match(reference, /Reference details are verified from trusted source data/);
  assert.match(reference, /readonly-facts/);
  assert.match(reference, /\["client", "country", "sector", "period", "offering"\]/);
  assert.doesNotMatch(reference, /<input[^>]+metadata/);
});

test("edits debounce backend validation and clear approval", () => {
  assert.match(studio, /setApproved\(false\)[\s\S]*setDirty\(true\)[\s\S]*setPendingNarrative/);
  assert.match(studio, /window\.setTimeout\(async \(\) =>/);
  assert.match(studio, /\/api\/reference-narrative\/validate/);
});

test("blocking findings are visible and disable approval", () => {
  assert.match(validation, /INFO/);
  assert.match(validation, /WARNING/);
  assert.match(validation, /BLOCKING/);
  assert.match(studio, /canApproveNarrative/);
  assert.match(studio, /disabled=\{!approvalAllowed\}/);
  assert.match(studio, /Approve narrative/);
});

test("whole, section and reference regeneration are wired", () => {
  assert.match(studio, /Regenerate draft/);
  assert.match(section, /Regenerate introduction/);
  assert.match(reference, /Regenerate this reference/);
  assert.match(studio, /\/api\/reference-narrative\/regenerate/);
  assert.match(studio, /regenerate\("section_intro"\)/);
  assert.match(studio, /regenerate\("reference", reference\.reference_id\)/);
});

test("human review message and three export statuses are explicit", () => {
  assert.match(studio, /AI-assisted draft/);
  assert.match(studio, /Review every statement before approval/);
  assert.match(validation, /narrative-status/);
  assert.match(studio, /READY FOR PRESENTATION/);
});

test("approved narratives expose exactly two presentation formats and deterministic downloads", () => {
  assert.match(studio, /status === "READY FOR PRESENTATION"/);
  assert.match(studio, /\/api\/reference-narrative\/presentations/);
  assert.match(studio, /approved_narrative_status: "READY_FOR_PRESENTATION"/);
  assert.match(studio, /template_id: templateId/);
  assert.equal((studio.match(/value="orange_bank_compact"/g) || []).length, 1);
  assert.equal((studio.match(/value="detailed_reference"/g) || []).length, 1);
  assert.match(studio, />Compact References</);
  assert.match(studio, />Detailed Case Study</);
  assert.match(studio, /function chooseTemplate/);
  const switchBody = studio.match(/function chooseTemplate[\s\S]*?\n  }/)?.[0] ?? "";
  assert.doesNotMatch(switchBody, /fetch|generateEntireNarrative|validateGenerated/);
  assert.doesNotMatch(studio, /TEMPLATE_D_REFERENCE_CASE/);
  assert.match(studio, /Generate presentation/);
  assert.match(studio, /Your presentation is ready/);
  assert.match(studio, /Download editable PPTX/);
  assert.match(studio, /Download PDF/);
  assert.match(studio, /pdf_download_url/);
});

test("professional defaults are French, Commercial, Executive and Medium", () => {
  assert.match(studio, /target_language: "fr"/);
  assert.match(studio, /tone: "commercial"/);
  assert.match(studio, /audience: "executive"/);
  assert.match(studio, /detail_level: "medium"/);
});

test("loading copy names narrative, presentation and PDF preparation clearly", () => {
  assert.match(studio, /Preparing AI-assisted draft…/);
  assert.match(studio, /Generating presentation…/);
  assert.match(studio, /Preparing PDF…/);
});

test("known backend failures use professional copy with expandable technical details", () => {
  assert.match(studio, /PPTX_CONTENT_OVERFLOW/);
  assert.match(studio, /more text than the selected template can safely display/);
  assert.match(studio, /local AI drafting service is currently unavailable/);
  assert.match(studio, /does not have an available approved evidence page/);
  assert.match(studio, /<summary>Technical details<\/summary>/);
});

test("validation is summarized with field labels and expandable technical details", () => {
  assert.match(validation, /View validation details/);
  assert.match(validation, /Technical details/);
  assert.match(validation, /fieldLabel/);
  assert.match(validation, /displayMessage/);
  assert.match(validation, /All checks passed/);
});

test("reference bullets are edited individually and unsupported fields are explicit", () => {
  assert.match(reference, /function BulletEditor/);
  assert.match(reference, /Add bullet/);
  assert.match(reference, /Remove.*bullet/);
  assert.match(reference, /Not supported by the selected source/);
  assert.match(reference, /No supported content available/);
  assert.match(reference, /No sufficiently supported benefit identified/);
});
