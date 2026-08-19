import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const page = readFileSync(join(root, "app", "page.tsx"), "utf8");
const compactBar = readFileSync(join(root, "components", "CompactSelectionBar.tsx"), "utf8");
const drawer = readFileSync(join(root, "components", "SelectionDrawer.tsx"), "utf8");
const filterPanel = readFileSync(join(root, "components", "FilterPanel.tsx"), "utf8");
const resultCard = readFileSync(join(root, "components", "ResultCard.tsx"), "utf8");
const presentationModal = readFileSync(join(root, "components", "PresentationGeneratorModal.tsx"), "utf8");

test("selection stays in a compact optional bottom bar", () => {
  assert.match(page, /<CompactSelectionBar/);
  assert.doesNotMatch(page, /<SelectionBasket|className="selection-basket"/);
  assert.match(compactBar, /if \(count < 1\) return null/);
  assert.match(compactBar, /Review selection/);
  assert.match(compactBar, /Generate presentation/);
});

test("submitting a new search clears selections from the previous search", () => {
  assert.match(page, /function submit\([\s\S]*setSelectionBasket\(clearBasket\(\)/);
  assert.match(page, /function submit\([\s\S]*setShowSelection\(false\)/);
  assert.match(page, /function submit\([\s\S]*setShowPresentationGenerator\(false\)/);
});

test("selection drawer exposes only compact metadata and controls", () => {
  assert.match(drawer, /mission_title/);
  assert.match(drawer, /item\.client, item\.country/);
  assert.match(drawer, /onMove/);
  assert.match(drawer, /Remove/);
  assert.doesNotMatch(drawer, /description|services_delivered|supporting_passages/);
});

test("compact presentation generator is mounted only after an explicit generation action", () => {
  assert.match(page, /showPresentationGenerator && \(/);
  assert.match(page, /<PresentationGeneratorModal/);
  assert.match(page, /function openGeneration\(\)/);
  assert.doesNotMatch(page, /generate-inline/);
  assert.doesNotMatch(page, /NarrativeStudio/);
  assert.match(presentationModal, /Generate reference presentation/);
});

test("filter options do not expose corpus facet counts", () => {
  assert.doesNotMatch(filterPanel, /facet\.count/);
});

test("application shell exposes the three direct presentation stages", () => {
  for (const label of ["Find references", "Select references", "Generate presentation"]) {
    assert.match(page, new RegExp(label));
  }
  assert.doesNotMatch(page, /Prepare narrative/);
  assert.match(page, /workflow-stepper/);
});

test("generator offers exactly two styles and exactly three output choices", () => {
  assert.equal((presentationModal.match(/setStyle\("orange_bank_compact"\)/g) || []).length, 1);
  assert.equal((presentationModal.match(/setStyle\("detailed_reference"\)/g) || []).length, 1);
  assert.equal((presentationModal.match(/setOutput\("pptx"\)/g) || []).length, 1);
  assert.equal((presentationModal.match(/setOutput\("pdf"\)/g) || []).length, 1);
  assert.equal((presentationModal.match(/setOutput\("both"\)/g) || []).length, 1);
  assert.doesNotMatch(presentationModal, /tone|audience|detail_level|Approve narrative|validation dashboard/i);
});

test("presentation language defaults to French instead of following search detection", () => {
  assert.match(page, /const presentationLanguage = "fr" as const/);
  assert.doesNotMatch(page, /presentationLanguage\s*=\s*response\?\.detected_language/);
});

test("generator streams reference progress without a total timeout", () => {
  assert.match(presentationModal, /\/api\/presentations\/generate-stream/);
  assert.match(presentationModal, /Preparing selected references/);
  assert.match(presentationModal, /Writing reference/);
  assert.match(presentationModal, /Optimizing slide content/);
  assert.match(presentationModal, /Building presentation/);
  assert.match(presentationModal, /Preparing PDF/);
  assert.doesNotMatch(presentationModal, /AbortController|setTimeout|token|elapsed|technical code/i);
});

test("main search and result UI hide retrieval internals and stable identifiers", () => {
  assert.doesNotMatch(page, /hybrid retrieval|evidence gate|abstention_reason\}/i);
  assert.doesNotMatch(resultCard, /className="reference-id"|Stable reference ID/);
  assert.doesNotMatch(resultCard, /score_components\./);
  assert.match(resultCard, /result\.display_title \|\| result\.project_title/);
});

test("header does not expose backend operational status", () => {
  assert.doesNotMatch(page, /Checking backend|Backend ready|Backend unavailable/);
  assert.doesNotMatch(page, /className=\{`health/);
});

test("results use one responsive block without a separate details view", () => {
  assert.doesNotMatch(page, /SummaryTable|Result view|setView|ViewMode/);
  assert.match(page, /className="results-list"/);
  assert.match(resultCard, /<details className="annex-details">/);
  assert.match(resultCard, /<summary>/);
  assert.doesNotMatch(resultCard, /<details className="annex-details" open/);
});
