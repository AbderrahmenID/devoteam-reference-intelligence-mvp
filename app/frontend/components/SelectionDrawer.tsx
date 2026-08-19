export type SelectedReference = {
  reference_id: string;
  display_title: string;
  mission_title: string;
  client: string;
  country: string;
  period: string;
  sector: string;
  offering: string;
};

type Props = {
  items: SelectedReference[];
  onClose: () => void;
  onRemove: (referenceId: string) => void;
  onMove: (referenceId: string, direction: -1 | 1) => void;
  onGenerate: () => void;
};

export default function SelectionDrawer({ items, onClose, onRemove, onMove, onGenerate }: Props) {
  return (
    <div className="selection-drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside className="selection-drawer" role="dialog" aria-modal="true" aria-labelledby="selection-drawer-title" onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div><p className="eyebrow">Step 2 of 3</p><h2 id="selection-drawer-title">Review your selection</h2><p>Order the references as they should appear in the presentation.</p></div>
          <button type="button" aria-label="Close selection" onClick={onClose}>×</button>
        </header>
        <ol>
          {items.map((item, index) => (
            <li key={item.reference_id}>
              <span className="selection-position">{index + 1}</span>
              <div className="selection-copy">
                <strong dir="auto">{item.display_title || item.mission_title}</strong>
                <span>{[item.client, item.country].filter(Boolean).join(" · ")}</span>
              </div>
              <div className="selection-row-actions">
                <button type="button" disabled={index === 0} onClick={() => onMove(item.reference_id, -1)} aria-label={`Move ${item.display_title || item.mission_title} up`}>↑</button>
                <button type="button" disabled={index === items.length - 1} onClick={() => onMove(item.reference_id, 1)} aria-label={`Move ${item.display_title || item.mission_title} down`}>↓</button>
                <button type="button" className="remove" onClick={() => onRemove(item.reference_id)}>Remove</button>
              </div>
            </li>
          ))}
        </ol>
        <footer>
          <button type="button" onClick={onClose}>Continue browsing</button>
          <button type="button" className="primary" disabled={!items.length} onClick={onGenerate}>Generate presentation →</button>
        </footer>
      </aside>
    </div>
  );
}
