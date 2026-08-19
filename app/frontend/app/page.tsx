"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import CompactSelectionBar from "@/components/CompactSelectionBar";
import FilterPanel, { FacetValue, PeriodSelection } from "@/components/FilterPanel";
import PresentationGeneratorModal from "@/components/PresentationGeneratorModal";
import ResultCard, { SearchResult } from "@/components/ResultCard";
import SelectionDrawer, { SelectedReference } from "@/components/SelectionDrawer";
import { clearBasket, hydrateBasket, moveReference, removeReference, SESSION_KEY, toggleReference } from "@/lib/selectionBasket.mjs";

type SearchResponse = {
  query: string;
  applied_filters: Record<string, unknown>;
  resolved_period: { start_year: number; end_year: number } | null;
  detected_language: string;
  scripts: string[];
  rtl: boolean;
  retrieval_mode: string;
  abstained: boolean;
  abstention_reason: string;
  total_count: number;
  result_count: number;
  page: number;
  page_size: number;
  total_pages: number;
  sort: string;
  latency_ms: number;
  results: SearchResult[];
};

type FacetResponse = { facets: Record<string, FacetValue[] | Record<string, unknown>> };
type SortMode = "relevance" | "newest" | "oldest" | "project_title" | "client" | "country";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

function errorDetail(body: unknown, fallback: string): string {
  if (typeof body === "object" && body && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    return typeof detail === "string" ? detail : JSON.stringify(detail);
  }
  return fallback;
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Record<string, string[]>>({});
  const [period, setPeriod] = useState<PeriodSelection>({});
  const [facets, setFacets] = useState<Record<string, FacetValue[]>>({});
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [sort, setSort] = useState<SortMode>("relevance");
  const [pageSize, setPageSize] = useState<10 | 20 | 50>(20);
  const [selectionBasket, setSelectionBasket] = useState<SelectedReference[]>([]);
  const [basketReady, setBasketReady] = useState(false);
  const [showSelection, setShowSelection] = useState(false);
  const [showPresentationGenerator, setShowPresentationGenerator] = useState(false);
  const [includeSummary, setIncludeSummary] = useState(true);
  const [includeAnnex, setIncludeAnnex] = useState(true);
  const [includeEvidence, setIncludeEvidence] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetch(`${API_URL}/health`, { signal: controller.signal }),
      fetch(`${API_URL}/api/facets`, { signal: controller.signal }),
    ])
      .then(async ([healthResult, facetResult]) => {
        if (!healthResult.ok || !facetResult.ok) throw new Error("Backend initialization failed");
        const facetValue = await facetResult.json() as FacetResponse;
        const arrays = Object.fromEntries(
          Object.entries(facetValue.facets).filter((entry): entry is [string, FacetValue[]] => Array.isArray(entry[1]))
        );
        setFacets(arrays);
      })
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    setSelectionBasket(hydrateBasket(window.sessionStorage.getItem(SESSION_KEY)) as SelectedReference[]);
    setBasketReady(true);
  }, []);

  useEffect(() => {
    if (basketReady) window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(selectionBasket));
  }, [basketReady, selectionBasket]);

  const filterPayload = useMemo(() => {
    const active = Object.fromEntries(Object.entries(filters).filter(([, values]) => values.length));
    return Object.keys(period).length ? { ...active, period } : active;
  }, [filters, period]);
  const selectedIds = useMemo(() => new Set(selectionBasket.map((item) => item.reference_id)), [selectionBasket]);

  async function runSearch(nextPage: number, overrides?: { sort?: SortMode; pageSize?: 10 | 20 | 50 }) {
    const effectiveSort = overrides?.sort ?? sort;
    const effectivePageSize = overrides?.pageSize ?? pageSize;
    setLoading(true);
    setError("");
    try {
      const result = await fetch(`${API_URL}/api/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          filters: Object.keys(filterPayload).length ? filterPayload : undefined,
          page: nextPage,
          page_size: effectivePageSize,
          sort: effectiveSort,
        }),
      });
      const body = await result.json() as unknown;
      if (!result.ok) throw new Error(errorDetail(body, `Search failed (${result.status})`));
      setResponse(body as SearchResponse);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The backend is unavailable.");
    } finally {
      setLoading(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSelectionBasket(clearBasket() as SelectedReference[]);
    setShowSelection(false);
    setShowPresentationGenerator(false);
    void runSearch(1);
  }

  function toggleFilter(category: string, value: string) {
    setFilters((current) => {
      const values = new Set(current[category] ?? []);
      if (values.has(value)) values.delete(value); else values.add(value);
      return { ...current, [category]: [...values] };
    });
  }

  function clearFilters() {
    setFilters({});
    setPeriod({});
  }

  function removeFilter(category: string, value?: string) {
    if (category === "period") {
      setPeriod({});
      return;
    }
    if (!value) return;
    toggleFilter(category, value);
  }

  function toggleSelection(referenceId: string) {
    const reference = response?.results.find((item) => item.reference_id === referenceId);
    if (!reference) return;
    setSelectionBasket((current) => toggleReference(current, reference) as SelectedReference[]);
  }

  function clearSelection() {
    setSelectionBasket(clearBasket() as SelectedReference[]);
    setShowSelection(false);
  }

  function openGeneration() {
    setShowSelection(false);
    setShowPresentationGenerator(true);
  }

  async function exportDocx() {
    if (!response || selectedIds.size === 0) return;
    setExporting(true);
    setError("");
    try {
      const result = await fetch(`${API_URL}/api/export/docx`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          filters: Object.keys(filterPayload).length ? filterPayload : undefined,
          selected_reference_ids: [...selectedIds],
          export_all_filtered: false,
          sort,
          options: {
            include_summary_table: includeSummary,
            include_detailed_annex: includeAnnex,
            include_evidence_passages: includeEvidence,
            include_scores: false,
            missing_value_policy: "blank",
          },
        }),
      });
      if (!result.ok) {
        const body = await result.json() as unknown;
        throw new Error(errorDetail(body, `Export failed (${result.status})`));
      }
      const blob = await result.blob();
      const disposition = result.headers.get("Content-Disposition") ?? "";
      const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? "devoteam-references.docx";
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "DOCX export failed.");
    } finally {
      setExporting(false);
    }
  }

  const selectedCount = selectedIds.size;
  const rangeStart = response?.result_count ? (response.page - 1) * response.page_size + 1 : 0;
  const rangeEnd = response ? rangeStart + response.result_count - 1 : 0;
  const noEligible = response?.abstention_reason === "NO_ELIGIBLE_REFERENCE";
  const workflowActive = showPresentationGenerator ? 3 : selectedCount > 0 ? 2 : 1;
  const presentationLanguage = "fr" as const;

  return (
    <main className={selectedCount ? "has-selection" : ""}>
      <header className="topbar">
        <div className="brand"><span className="brand-mark" aria-hidden="true">d</span><span><strong>Devoteam</strong><small>Reference Intelligence</small></span></div>
        <span className="internal-product">Proposal enablement workspace</span>
      </header>

      <nav className="workflow-stepper" aria-label="Reference presentation workflow">
        {["Find references", "Select references", "Generate presentation"].map((label, index) => (
          <div className={`${workflowActive === index + 1 ? "active" : ""} ${workflowActive > index + 1 ? "complete" : ""}`} key={label} aria-current={workflowActive === index + 1 ? "step" : undefined}>
            <span>{workflowActive > index + 1 ? "✓" : index + 1}</span><strong>{label}</strong>
          </div>
        ))}
      </nav>

      <section className="hero compact-hero">
        <div className="hero-copy">
          <p className="eyebrow">Devoteam client experience</p>
          <h1>Find the right references.<br /><em>Generate the presentation.</em></h1>
          <p className="intro">Select trusted Devoteam experience and generate an editable reference presentation in the real approved format.</p>
        </div>
        <form className="search-panel" onSubmit={submit}>
          <label htmlFor="query">What experience do you need for this opportunity?</label>
          <textarea id="query" dir="auto" rows={3} maxLength={1000} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. PCA for a retail bank, cloud strategy, data governance" aria-describedby="query-help" />
          <div className="search-actions"><p id="query-help">Search in French, English or Arabic. You can refine the shortlist afterwards.</p><button type="submit" disabled={loading}>{loading ? <><span className="spinner" aria-hidden="true" /> Searching references…</> : <>Find references <span aria-hidden="true">→</span></>}</button></div>
        </form>
      </section>

      <section className="workspace">
        <div className="results-section" aria-live="polite" aria-busy={loading}>
          <FilterPanel facets={facets} filters={filters} period={period} onToggle={toggleFilter} onPeriodChange={setPeriod} onClear={clearFilters} />
          {Object.entries(filters).flatMap(([category, values]) => values.map((value) => ({ category, value }))).length > 0 || Object.keys(period).length > 0 ? (
            <div className="active-filters" aria-label="Active filters">
              <span>Active filters</span>
              {Object.entries(filters).flatMap(([category, values]) => values.map((value) => <button type="button" key={`${category}-${value}`} onClick={() => removeFilter(category, value)}>{value} ×</button>))}
              {Object.keys(period).length > 0 && <button type="button" onClick={() => removeFilter("period")}>{period.preset?.replaceAll("_", " ") ?? `${period.start_year ?? "…"}–${period.end_year ?? "…"}`} ×</button>}
            </div>
          ) : null}

          {error && <div className="state-card error-state" role="alert"><span aria-hidden="true">!</span><div><h2>Request could not be completed</h2><p>{error}</p></div></div>}

          {response?.abstained && (
            <div className="state-card empty-state"><span aria-hidden="true">∅</span><div><h2>{noEligible ? "No reference matches these filters" : "No sufficiently supported match was found"}</h2><p>{noEligible ? "Broaden or clear one or more filters." : "Try a more specific capability, sector, client or offering."}</p></div></div>
          )}

          {response && !response.abstained && (
            <>
              <header className="results-header">
                <div><p className="eyebrow">Relevant experience</p><h2>{response.total_count} reference{response.total_count === 1 ? "" : "s"}</h2><p className="range-copy">Showing {rangeStart}–{rangeEnd}. Select the examples that best support the opportunity.</p></div>
                <div className="result-controls">
                  <label>Sort<select value={sort} onChange={(event) => { const value = event.target.value as SortMode; setSort(value); void runSearch(1, { sort: value }); }}><option value="relevance">Relevance</option><option value="newest">Newest</option><option value="oldest">Oldest</option><option value="project_title">Project title</option><option value="client">Client</option><option value="country">Country</option></select></label>
                  <label>Page size<select value={pageSize} onChange={(event) => { const value = Number(event.target.value) as 10 | 20 | 50; setPageSize(value); void runSearch(1, { pageSize: value }); }}><option value={10}>10</option><option value={20}>20</option><option value={50}>50</option></select></label>
                </div>
              </header>

              <div className="results-list">{response.results.map((result) => <ResultCard result={result} key={result.reference_id} selected={selectedIds.has(result.reference_id)} onToggle={toggleSelection} />)}</div>

              <nav className="pagination" aria-label="Search result pages">
                <button type="button" disabled={response.page <= 1 || loading} onClick={() => void runSearch(response.page - 1)}>← Previous</button>
                <span>Page <strong>{response.page}</strong> of {response.total_pages}</span>
                <button type="button" disabled={response.page >= response.total_pages || loading} onClick={() => void runSearch(response.page + 1)}>Next →</button>
              </nav>

              <details className="secondary-export">
                <summary>Need a Word reference dossier instead?</summary>
                <div className="export-options">
                  <label><input type="checkbox" checked={includeSummary} onChange={(event) => setIncludeSummary(event.target.checked)} /> Summary table</label>
                  <label><input type="checkbox" checked={includeAnnex} onChange={(event) => setIncludeAnnex(event.target.checked)} /> Detailed annex</label>
                  <label><input type="checkbox" checked={includeEvidence} onChange={(event) => setIncludeEvidence(event.target.checked)} /> Source passages</label>
                </div>
                <button type="button" className="export-button" disabled={exporting || selectedCount === 0 || (!includeSummary && !includeAnnex)} onClick={() => void exportDocx()}>{exporting ? "Preparing DOCX…" : "Download selected DOCX"}</button>
              </details>
            </>
          )}

          {!response && !error && !loading && <div className="idle-note">Start with the opportunity, capability, sector or client you need to support.</div>}
        </div>
      </section>

      <footer className="page-footer"><p>Devoteam internal use</p><p>Every presentation remains subject to consultant review and approval.</p></footer>
      <CompactSelectionBar count={selectedCount} onView={() => setShowSelection(true)} onClear={clearSelection} onGenerate={openGeneration} />
      {showSelection && (
        <SelectionDrawer
          items={selectionBasket}
          onClose={() => setShowSelection(false)}
          onRemove={(referenceId) => setSelectionBasket((current) => removeReference(current, referenceId) as SelectedReference[])}
          onMove={(referenceId, direction) => setSelectionBasket((current) => moveReference(current, referenceId, direction) as SelectedReference[])}
          onGenerate={openGeneration}
        />
      )}
      {showPresentationGenerator && (
        <PresentationGeneratorModal
          apiUrl={API_URL}
          references={selectionBasket}
          opportunityContext={query}
          targetLanguage={presentationLanguage}
          onClose={() => setShowPresentationGenerator(false)}
        />
      )}
    </main>
  );
}
