export type FacetValue = { value: string; count: number };

export type PeriodSelection = {
  start_year?: number;
  end_year?: number;
  preset?: "last_3_years" | "last_5_years" | "last_10_years";
};

type Props = {
  facets: Record<string, FacetValue[]>;
  filters: Record<string, string[]>;
  period: PeriodSelection;
  onToggle: (category: string, value: string) => void;
  onPeriodChange: (period: PeriodSelection) => void;
  onClear: () => void;
};

const PRIMARY = [
  ["country", "Country"],
  ["sector", "Sector"],
  ["offering", "Offering"],
  ["client", "Client"],
] as const;

const ADVANCED = [
  ["service_nature", "Service"],
  ["technology", "Technology"],
  ["status", "Project status"],
  ["evidence_available", "Source availability"],
  ["evidence_type", "Source type"],
  ["language", "Language"],
  ["themes", "Themes"],
  ["business_unit", "Business unit"],
] as const;

function Facet({ category, label, facets, selected, onToggle }: {
  category: string;
  label: string;
  facets: FacetValue[];
  selected: string[];
  onToggle: (category: string, value: string) => void;
}) {
  return (
    <details className="filter-group">
      <summary>{label}{selected.length > 0 && <span>{selected.length}</span>}</summary>
      <div className="facet-options">
        {facets.length === 0 ? <p>No available values</p> : facets.map((facet) => (
          <label key={facet.value} title={facet.value}>
            <input type="checkbox" checked={selected.includes(facet.value)} onChange={() => onToggle(category, facet.value)} />
            <span>{facet.value}</span>
          </label>
        ))}
      </div>
    </details>
  );
}

export default function FilterPanel({ facets, filters, period, onToggle, onPeriodChange, onClear }: Props) {
  const selectionCount = Object.values(filters).reduce((sum, values) => sum + values.length, 0)
    + (Object.keys(period).length ? 1 : 0);

  return (
    <details className="filter-panel">
      <summary>
        <span><strong>Filters</strong><small>Country, sector, offering, client and period</small></span>
        {selectionCount > 0 && <b>{selectionCount} active</b>}
      </summary>
      <div className="filter-panel-body">
        <header>
          <div><p className="eyebrow">Refine the shortlist</p><h2>Commercial filters</h2></div>
          <button type="button" className="text-button" onClick={onClear} disabled={!selectionCount}>Clear all</button>
        </header>
        <div className="primary-filter-grid">
          <details className="filter-group">
            <summary>Period{Object.keys(period).length > 0 && <span>1</span>}</summary>
            <div className="period-controls">
              <select aria-label="Relative period preset" value={period.preset ?? ""} onChange={(event) => {
                const value = event.target.value as PeriodSelection["preset"] | "";
                onPeriodChange(value ? { preset: value } : {});
              }}>
                <option value="">Custom period</option>
                <option value="last_3_years">Last 3 years</option>
                <option value="last_5_years">Last 5 years</option>
                <option value="last_10_years">Last 10 years</option>
              </select>
              {!period.preset && <div className="year-range">
                <input type="number" min={1900} max={2100} placeholder="From" aria-label="Period start year" value={period.start_year ?? ""} onChange={(event) => onPeriodChange({ ...period, start_year: event.target.value ? Number(event.target.value) : undefined })} />
                <span>to</span>
                <input type="number" min={1900} max={2100} placeholder="To" aria-label="Period end year" value={period.end_year ?? ""} onChange={(event) => onPeriodChange({ ...period, end_year: event.target.value ? Number(event.target.value) : undefined })} />
              </div>}
            </div>
          </details>
          {PRIMARY.map(([category, label]) => <Facet key={category} category={category} label={label} facets={facets[category] ?? []} selected={filters[category] ?? []} onToggle={onToggle} />)}
        </div>
        <details className="advanced-filters">
          <summary>More filters</summary>
          <div className="primary-filter-grid">
            {ADVANCED.map(([category, label]) => <Facet key={category} category={category} label={label} facets={facets[category] ?? []} selected={filters[category] ?? []} onToggle={onToggle} />)}
          </div>
        </details>
      </div>
    </details>
  );
}
