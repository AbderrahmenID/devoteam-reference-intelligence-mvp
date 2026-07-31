export type SearchResult = {
  reference_id: string;
  title: string;
  client: string;
  sector: string;
  offering: string;
  supporting_passage: string;
  source_document: string;
  source_page: number;
  citation_label: string;
  citation_uri: string;
  evidence_language: string;
  match_reasons: string[];
  rank: number;
  score_components: {
    bm25_score: number;
    dense_cosine: number;
    hybrid_rrf: number;
    query_term_coverage: number;
    supporting_passages: number;
  };
};

function MetadataPill({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <span className="metadata-pill">
      <span>{label}</span>
      {value}
    </span>
  );
}

export default function ResultCard({ result }: { result: SearchResult }) {
  const evidenceDirection = result.evidence_language.toLowerCase().startsWith("ar") ? "rtl" : "auto";

  return (
    <article className="result-card">
      <div className="result-rank" aria-label={`Result ${result.rank}`}>
        {String(result.rank).padStart(2, "0")}
      </div>
      <div className="result-content">
        <div className="result-heading">
          <div>
            <p className="eyebrow">Verified corpus reference</p>
            <h2 dir="auto">{result.title}</h2>
          </div>
          <span className="language-badge">{result.evidence_language || "und"}</span>
        </div>

        <div className="metadata-row">
          <MetadataPill label="Client" value={result.client} />
          <MetadataPill label="Sector" value={result.sector} />
          <MetadataPill label="Offering" value={result.offering} />
        </div>

        <blockquote dir={evidenceDirection}>
          <span className="quote-mark" aria-hidden="true">“</span>
          {result.supporting_passage}
        </blockquote>

        <div className="reason-list" aria-label="Match reasons">
          {result.match_reasons.map((reason) => (
            <span key={reason}>{reason}</span>
          ))}
        </div>

        <footer className="citation-row">
          <div>
            <span className="citation-label">Source</span>
            <span dir="auto">{result.source_document} · page {result.source_page}</span>
          </div>
          <a href={result.citation_uri} target="_blank" rel="noreferrer">
            Open citation <span aria-hidden="true">↗</span>
          </a>
        </footer>
        <p className="reference-id" dir="ltr">Reference ID · {result.reference_id}</p>
      </div>
    </article>
  );
}

