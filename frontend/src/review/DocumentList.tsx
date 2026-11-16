import { Badge } from './ui';
import { shortLabels } from './bands';
import type { DocumentRow } from './types';

/**
 * Review queue, pending first. Approval is per document, so the badge is a state
 * and not a count. Both states are labelled so an absent badge can never read as
 * "not loaded yet"; `approved` stays the louder of the two.
 */
export function DocumentList({
  documents,
  pending,
  selected,
  onSelect,
}: {
  documents: DocumentRow[];
  pending: number;
  selected: string | undefined;
  onSelect: (id: string) => void;
}) {
  const labels = shortLabels(documents.map((d) => d.id));
  return (
    <div className="w-60 shrink-0 overflow-auto border-r border-neutral-800 p-4">
      <h2 className="text-lg font-semibold">Documents</h2>
      <p className="mb-3 text-xs text-neutral-400">
        {pending} of {documents.length} pending
      </p>
      {documents.map((doc) => (
        <div
          key={doc.id}
          onClick={() => onSelect(doc.id)}
          className={`mb-0.5 flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 ${
            doc.id === selected ? 'bg-neutral-800' : 'hover:bg-neutral-900'
          }`}
        >
          <span className="flex-1 truncate text-sm" title={doc.id}>
            {labels[doc.id]}
          </span>
          {doc.approved ? (
            <Badge variant="outline" className="text-[10px]">
              approved
            </Badge>
          ) : (
            <Badge variant="secondary" className="text-[10px] text-neutral-400">
              pending
            </Badge>
          )}
        </div>
      ))}
    </div>
  );
}
