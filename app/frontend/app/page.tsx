"use client";

import { FormEvent, useEffect, useState } from "react";
import ResultCard, { SearchResult } from "@/components/ResultCard";

type SearchResponse = {
  query: string;
  detected_language: string;
  scripts: string[];
  rtl: boolean;
  retrieval_mode: string;
  abstained: boolean;
  abstention_reason: string;
  result_count: number;
  latency_ms: number;
  results: SearchResult[];
};

type Health = {
  status: string;
  data_ready: boolean;
  model_available: boolean;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export default function Home() {
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_URL}/health`, { signal: controller.signal })
      .then((result) => {
        if (!result.ok) throw new Error("Health check failed");
        return result.json() as Promise<Health>;
      })
      .then((value) => {
        setHealth(value);
        setHealthError(false);
      })
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setHealthError(true);
      });
    return () => controller.abort();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResponse(null);
    try {
      const result = await fetch(`${API_URL}/api/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, top_k: 3 }),
      });
      if (!result.ok) {
        let detail = `Search failed (${result.status})`;
        try {
          const body = (await result.json()) as { detail?: string };
          if (body.detail) detail = body.detail;
        } catch {
          // Preserve the HTTP error if the backend did not return JSON.
        }
        throw new Error(detail);
      }
      setResponse((await result.json()) as SearchResponse);
      setHealthError(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The backend is unavailable.");
    } finally {
      setLoading(false);
    }
  }

  const online = health?.status === "ok" && !healthError;

  return (
    <main>
      <nav className="topbar" aria-label="Application header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">D</span>
          <span>Devoteam <strong>Reference Finder</strong></span>
        </div>
        <div className={`health ${online ? "online" : healthError ? "offline" : "checking"}`}>
          <span aria-hidden="true" />
          {online ? "Backend ready" : healthError ? "Backend unavailable" : "Checking backend"}
        </div>
      </nav>

      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Multilingual evidence retrieval · FR / EN / AR</p>
          <h1>Find the reference.<br /><em>Show the evidence.</em></h1>
          <p className="intro">
            Search validated Devoteam project references across languages. Every result is grounded in
            a source passage and page-level citation.
          </p>
        </div>

        <form className="search-panel" onSubmit={submit}>
          <label htmlFor="query">What capability, sector, client, or project do you need?</label>
          <textarea
            id="query"
            dir="auto"
            rows={4}
            maxLength={1000}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. Références PCA pour une banque · Cloud strategy · مراجع استمرارية الأعمال"
            aria-describedby="query-help"
          />
          <div className="search-actions">
            <p id="query-help">French, English, Arabic, or mixed text · up to 3 references</p>
            <button type="submit" disabled={loading}>
              {loading ? <><span className="spinner" aria-hidden="true" /> Searching corpus…</> : <>Search references <span aria-hidden="true">→</span></>}
            </button>
          </div>
        </form>
      </section>

      <section className="results-section" aria-live="polite" aria-busy={loading}>
        {error && (
          <div className="state-card error-state" role="alert">
            <span aria-hidden="true">!</span>
            <div><h2>Search could not reach the backend</h2><p>{error}</p></div>
          </div>
        )}

        {response && response.abstained && (
          <div className="state-card empty-state">
            <span aria-hidden="true">∅</span>
            <div>
              <h2>No supported reference found</h2>
              <p>The evidence gate abstained: <code>{response.abstention_reason}</code>. Try a more specific technology, capability, client, sector, or offering.</p>
            </div>
          </div>
        )}

        {response && !response.abstained && (
          <>
            <header className="results-header">
              <div>
                <p className="eyebrow">Evidence-backed results</p>
                <h2>{response.result_count} reference{response.result_count === 1 ? "" : "s"} found</h2>
              </div>
              <p>{response.retrieval_mode} · {response.detected_language} · {Math.round(response.latency_ms)} ms</p>
            </header>
            <div className="results-list">
              {response.results.slice(0, 3).map((result) => (
                <ResultCard result={result} key={result.reference_id} />
              ))}
            </div>
          </>
        )}

        {!response && !error && !loading && (
          <div className="idle-note">
            <span>1185</span> evidence passages indexed · BM25 + multilingual E5 · deterministic abstention
          </div>
        )}
      </section>

      <footer className="page-footer">
        <p>Internship prototype · Internal corpus · Retrieval, not generated answers</p>
        <p>Reranker disabled · Maximum 3 cited references</p>
      </footer>
    </main>
  );
}

