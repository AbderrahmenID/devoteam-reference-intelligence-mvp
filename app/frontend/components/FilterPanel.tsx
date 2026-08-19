"use client";

import { useEffect, useState } from "react";

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

function FilterGroup({ id, label, count = 0, open, onOpen, children }: {
  id: string;
  label: string;
  count?: number;
  open: boolean;
  onOpen: (id: string) => void;
  children: React.ReactNode;
}) {
  const panelId = `filter-panel-${id}`;
  return (
    <section className={`filter-group${open ? " is-open" : ""}`}>
      <button type="button" className="filter-group-trigger" aria-expanded={open} aria-controls={panelId} onClick={() => onOpen(id)}>
        <span>{label}</span>
        <span className="filter-group-meta">
          {count > 0 && <b>{count}</b>}
          <i aria-hidden="true">{open ? "−" : "+"}</i>
        </span>
      </button>
      {open && <div className="filter-group-content" id={panelId}>{children}</div>}
    </section>
  );
}

function Facet({ category, label, facets, selected, open, onOpen, onToggle }: {
  category: string;
  label: string;
  facets: FacetValue[];
  selected: string[];
  open: boolean;
  onOpen: (id: string) => void;
  onToggle: (category: string, value: string) => void;
}) {
  return (
    <FilterGroup id={category} label={label} count={selected.length} open={open} onOpen={onOpen}>
      <div className="facet-options">
        {facets.length === 0 ? <p>No available values</p> : facets.map((facet) => (
          <label key={facet.value} title={facet.value}>
            <input type="checkbox" checked={selected.includes(facet.value)} onChange={() => onToggle(category, facet.value)} />
            <span>{facet.value}</span>
          </label>
        ))}
      </div>
    </FilterGroup>
  );
}

export default function FilterPanel({ facets, filters, period, onToggle, onPeriodChange, onClear }: Props) {
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const [moreOpen, setMoreOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const selectionCount = Object.values(filters).reduce((sum, values) => sum + values.length, 0)
    + (Object.keys(period).length ? 1 : 0);
  const advancedSelectionCount = ADVANCED.reduce((sum, [category]) => sum + (filters[category]?.length ?? 0), 0);
  const toggleGroup = (id: string) => {
    setMoreOpen(false);
    setOpenGroup((current) => current === id ? null : id);
  };
  const toggleMore = () => {
    setOpenGroup(null);
    setMoreOpen((current) => !current);
  };
  const toggleAdvancedGroup = (id: string) => setOpenGroup((current) => current === id ? null : id);

  useEffect(() => {
    if (!drawerOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [drawerOpen]);

  return (
    <div className="filter-shell">
      <button type="button" className="filter-mobile-toggle" aria-expanded={drawerOpen} onClick={() => setDrawerOpen(true)}>
        <span>Filter results</span>
        {selectionCount > 0 && <b>{selectionCount}</b>}
      </button>
      <aside className={`filter-panel${drawerOpen ? " drawer-open" : ""}`} aria-label="Reference filters">
        <header>
          <h2>Filters</h2>
          <div className="filter-panel-actions">
            <button type="button" className="text-button" onClick={onClear} disabled={!selectionCount}>Clear all</button>
            <button type="button" className="filter-drawer-close" aria-label="Close filters" onClick={() => setDrawerOpen(false)}>×</button>
          </div>
        </header>
        {selectionCount > 0 && <p className="filter-selection-count">{selectionCount} active filter{selectionCount === 1 ? "" : "s"}</p>}

        <div className="filter-groups">
          <FilterGroup id="period" label="Period" count={Object.keys(period).length ? 1 : 0} open={openGroup === "period"} onOpen={toggleGroup}>
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
          </FilterGroup>

          {PRIMARY.map(([category, label]) => (
            <Facet key={category} category={category} label={label} facets={facets[category] ?? []} selected={filters[category] ?? []} open={openGroup === category} onOpen={toggleGroup} onToggle={onToggle} />
          ))}

          <FilterGroup id="more-filters" label="More filters" count={advancedSelectionCount} open={moreOpen} onOpen={toggleMore}>
            <div className="advanced-filter-groups">
              {ADVANCED.map(([category, label]) => (
                <Facet key={category} category={category} label={label} facets={facets[category] ?? []} selected={filters[category] ?? []} open={openGroup === category} onOpen={toggleAdvancedGroup} onToggle={onToggle} />
              ))}
            </div>
          </FilterGroup>
        </div>
      </aside>
      {drawerOpen && <button type="button" className="filter-drawer-backdrop" aria-label="Close filter drawer" onClick={() => setDrawerOpen(false)} />}
    </div>
  );
}
