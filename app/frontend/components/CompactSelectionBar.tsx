type Props = {
  count: number;
  onView: () => void;
  onClear: () => void;
  onGenerate: () => void;
};

export default function CompactSelectionBar({ count, onView, onClear, onGenerate }: Props) {
  if (count < 1) return null;
  return (
    <div className="compact-selection-bar" role="region" aria-label="Selected reference basket">
      <strong><span>{count}</span> reference{count === 1 ? "" : "s"} selected</strong>
      <div>
        <button type="button" onClick={onView}>Review selection</button>
        <button type="button" onClick={onClear}>Clear</button>
        <button type="button" className="primary" onClick={onGenerate}>Generate presentation →</button>
      </div>
    </div>
  );
}
