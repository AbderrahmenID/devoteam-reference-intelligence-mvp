import test from "node:test";
import assert from "node:assert/strict";

import {
  canApproveNarrative,
  editableNarrative,
  generationRequest,
  studioStatus,
  validStudioSession,
  warningCounts,
  warningsForField,
} from "../lib/narrativeStudioState.mjs";

const id = "a".repeat(64);
const options = (language) => ({
  opportunity_title: "Opportunity",
  opportunity_description: "Description",
  requirements: "First requirement\n\nSecond requirement",
  target_language: language,
  tone: "commercial",
  audience: "executive",
  detail_level: "medium",
});

const warning = (severity, path = "references[0].headline") => ({
  code: `${severity}_CODE`,
  message: "Review this field",
  severity,
  blocking: severity === "BLOCKING",
  field_path: path,
});

test("French, English and Arabic options are passed unchanged to generation", () => {
  for (const language of ["fr", "en", "ar"]) {
    const request = generationRequest(options(language), [id]);
    assert.equal(request.target_language, language);
    assert.deepEqual(request.requirements, ["First requirement", "Second requirement"]);
    assert.deepEqual(request.selected_reference_ids, [id]);
  }
});

test("editable payload strips backend identity and support assignment", () => {
  const supported = (text) => ({ text, support_ids: ["S001"] });
  const draft = editableNarrative({
    section_intro: supported("Intro"),
    overall_storyline: supported("Story"),
    why_these_references: supported("Why"),
    references: [{
      reference_id: id,
      headline: supported("Headline"),
      short_description: supported("Description"),
      challenge: supported(""),
      devoteam_contribution: supported("Contribution"),
      realisations: [supported("Delivered")],
      benefits: [],
      why_relevant_to_opportunity: supported("Relevant"),
    }],
  });
  assert.equal(draft.references[0].headline, "Headline");
  assert.equal("reference_id" in draft.references[0], false);
  assert.equal(JSON.stringify(draft).includes("support_ids"), false);
});

test("validation levels, field matching and approval gate are deterministic", () => {
  const warnings = [warning("INFO"), warning("WARNING"), warning("BLOCKING", "references[0].benefits[0]")];
  assert.deepEqual(warningCounts(warnings), { INFO: 1, WARNING: 1, BLOCKING: 1 });
  assert.equal(warningsForField(warnings, "references[0].benefits").length, 1);
  assert.equal(canApproveNarrative(warnings, false), false);
  assert.equal(canApproveNarrative([warning("WARNING")], false), true);
  assert.equal(canApproveNarrative([], true), false);
});

test("status requires explicit approval and edits after approval reset readiness", () => {
  assert.equal(studioStatus({ hasNarrative: true, approved: false, dirty: false, warnings: [] }), "DRAFT");
  assert.equal(studioStatus({ hasNarrative: true, approved: false, dirty: true, warnings: [] }), "NEEDS REVIEW");
  assert.equal(studioStatus({ hasNarrative: true, approved: true, dirty: false, warnings: [] }), "READY FOR PRESENTATION");
  assert.equal(studioStatus({ hasNarrative: true, approved: true, dirty: false, warnings: [warning("BLOCKING")] }), "NEEDS REVIEW");
});

test("session state is accepted only for the same selected references", () => {
  const state = { reference_ids: [id], options: options("fr"), review: { narrative: {} } };
  assert.equal(validStudioSession(state, [id]), true);
  assert.equal(validStudioSession(state, ["b".repeat(64)]), false);
});
