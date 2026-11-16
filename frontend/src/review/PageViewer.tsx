import { useState } from 'react';
import { hexOf, labelFor } from './bands';
import type { Field } from './types';

const imageUrl = (file: string) => `/api/files/raw?path=${encodeURIComponent(file)}`;

/** Citations are shared: several values usually cite one region. */
function boxesForPage(fields: Field[], page: number | null) {
  const seen = new Map<string, Field[]>();
  for (const f of fields) {
    if (!f.coord || f.page_id !== page) continue;
    const key = f.coord.join(',');
    seen.set(key, [...(seen.get(key) ?? []), f]);
  }
  return [...seen.values()];
}

export function PageViewer({ fields, selected }: { fields: Field[]; selected: Field | undefined }) {
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);

  if (!selected?.image_file) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-neutral-400">
        No page image for this document.
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto bg-neutral-900/40 p-4">
      <div className="relative mx-auto max-w-2xl">
        <img
          key={selected.image_file}
          src={imageUrl(selected.image_file)}
          alt="Document page"
          className="block w-full rounded-md border border-neutral-800"
          onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
        />
        {size &&
          boxesForPage(fields, selected.page_id)
            .filter((group) => group.some((f) => f.path === selected.path))
            .map((group) => {
              const coord = group[0].coord!;
              /* Fixed blue, not a theme colour: this sits on white paper and
                 marks the link between the selected field and the page. */
              const hex = group.some((f) => f.path === selected.path) ? '#2563eb' : hexOf(null);
              return (
                <div
                  key={coord.join(',')}
                  className="absolute rounded-sm"
                  style={{
                    left: `${(coord[0] / size.w) * 100}%`,
                    top: `${(coord[1] / size.h) * 100}%`,
                    width: `${((coord[2] - coord[0]) / size.w) * 100}%`,
                    height: `${((coord[3] - coord[1]) / size.h) * 100}%`,
                    border: `2px solid ${hex}`,
                    background: `${hex}1f`,
                  }}
                >
                  <span
                    className="absolute -top-4 left-0 whitespace-nowrap rounded px-1 text-[9px] font-medium leading-4 text-white"
                    style={{ background: hex }}
                  >
                    {labelFor(group[0].type_key)}
                    {group.length > 1 && ` +${group.length - 1}`}
                  </span>
                </div>
              );
            })}
      </div>
    </div>
  );
}
