export type EvidencePassage = {
  text: string;
  source_document: string;
  source_page: number;
  citation_label: string;
  citation_uri: string;
  language: string;
};

export type MatchReason = {
  category: string;
  values: string[];
  description: string;
};

export type SearchResult = {
  reference_id: string;
  reference_number: string | null;
  display_title: string;
  project_title: string;
  mission_name: string;
  client: string;
  contracting_authority: string;
  country: string;
  country_code: string | null;
  project_start_date: string | null;
  completion_date: string | null;
  period: string;
  status: string | null;
  sector: string;
  offerings: string[];
  service_nature: string;
  technologies: string[];
  key_themes: string[];
  description: string;
  services_delivered: string[];
  supporting_passages: EvidencePassage[];
  evidence_available: boolean;
  evidence_types: string[];
  document_languages: string[];
  match_reasons: string[];
  match_details: MatchReason[];
  rank: number;
  relevance_rank: number;
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
  return <span className="metadata-pill"><span>{label}</span>{value}</span>;
}

type Props = {
  result: SearchResult;
  selected: boolean;
  selectionDisabled?: boolean;
  onToggle: (referenceId: string) => void;
};

export default function ResultCard({ result, selected, selectionDisabled, onToggle }: Props) {
  const passage = result.supporting_passages[0];
  const fitSignals = Array.from(new Set([
    ...result.match_details.flatMap((reason) => reason.values),
    ...result.offerings,
    result.sector,
  ].filter(Boolean))).slice(0, 4);

  return (
    <article className={`result-card ${selected ? "selected" : ""}`} id={`reference-${result.reference_id}`}>
      <div className="result-rank" aria-label={`Result ${result.rank}`}>
        <span>{String(result.rank).padStart(2, "0")}</span>
      </div>
      <div className="result-content">
        <div className="result-heading">
          <div>
            <p className="result-client" dir="auto">{result.client || result.contracting_authority || "Devoteam client"}</p>
            <h2 dir="auto">{result.display_title || result.project_title}</h2>
            <p className="result-client-line">{[result.country, result.sector, result.period].filter(Boolean).join(" · ")}</p>
          </div>
          <div className="result-side-actions">
            <label className={`pack-checkbox ${selected ? "is-selected" : ""}`}>
              <input
                type="checkbox"
                checked={selected}
                disabled={selectionDisabled}
                onChange={() => onToggle(result.reference_id)}
              />
              <span>{selected ? "Selected" : "Add to selection"}</span>
            </label>
          </div>
        </div>

        <div className="metadata-row">
          <MetadataPill label="Offering" value={result.offerings.join(", ")} />
          <MetadataPill label="Service" value={result.service_nature} />
        </div>

        <p className="result-summary" dir="auto">{result.description || result.services_delivered[0] || passage?.text || "No additional project summary is available."}</p>

        <div className="commercial-fit" aria-label="Relevant experience signals">
          <strong>Why it fits</strong>
          <div>{fitSignals.map((value) => <span key={value}>{value}</span>)}</div>
        </div>

        <details className="annex-details">
          <summary>
            <span>View evidence</span>
            <span className="details-toggle-label" aria-hidden="true">Show</span>
          </summary>
          {passage && (
            <blockquote dir="auto" lang={passage.language}>
              <span className="quote-mark" aria-hidden="true">“</span>
              {passage.text}
            </blockquote>
          )}
          <dl>
            <div><dt>Reference number</dt><dd>{result.reference_number ?? "Not provided in the source"}</dd></div>
            <div><dt>Full mission title</dt><dd dir="auto">{result.project_title || "Not provided in the source"}</dd></div>
            <div><dt>Contracting authority</dt><dd>{result.contracting_authority || "Not provided in the source"}</dd></div>
            <div><dt>Dates</dt><dd>{[result.project_start_date, result.completion_date].filter(Boolean).join("–") || result.period || "Not provided in the source"}</dd></div>
            <div><dt>Project description</dt><dd dir="auto">{result.description || "Not supported by the available source"}</dd></div>
            <div><dt>Services delivered</dt><dd dir="auto">{result.services_delivered[0] || "Not supported by the available source"}</dd></div>
            <div><dt>Key themes</dt><dd>{result.key_themes.join(", ") || "Not provided in the source"}</dd></div>
            <div><dt>Technologies</dt><dd>{result.technologies.join(", ") || "Not provided in the source"}</dd></div>
          </dl>
          {passage && (
            <footer className="citation-row">
              <div>
                <span className="citation-label">Source</span>
                <span dir="auto">{passage.source_document} · page {passage.source_page}</span>
              </div>
              {passage.citation_uri && (
                <a href={passage.citation_uri} target="_blank" rel="noreferrer">Open source <span aria-hidden="true">↗</span></a>
              )}
            </footer>
          )}
        </details>
      </div>
    </article>
  );
}
