import { Badge, Button, Input } from './ui';
import { confidenceVariant, labelFor } from './bands';
import type { Field } from './types';

/** Form generated from what the server discovered, in the order it returned. */
export function FieldList({
  fields,
  hasConfidence,
  selected,
  onSelect,
  edits,
  onEdit,
  onApprove,
  approving,
  approvedAt,
  error,
}: {
  fields: Field[];
  hasConfidence: boolean;
  selected: string | undefined;
  onSelect: (path: string) => void;
  edits: Record<string, string>;
  onEdit: (path: string, value: string) => void;
  onApprove: () => void;
  approving: boolean;
  approvedAt: string | null;
  error: string | null;
}) {
  const valueOf = (f: Field) => edits[f.path] ?? f.value ?? '';

  /*
    A value the model never found cannot be approved away: with nothing in the
    box there is no agreed value to record. Blocking depends on emptiness alone,
    which behaves identically with or without confidence.
  */
  const missing = fields.filter((f) => f.kind !== 'json' && valueOf(f).trim() === '');
  const blocked = missing.length > 0;
  /* A reviewed document stays editable, but the button only wakes up once
     something differs from what is already recorded. */
  const dirty = fields.some((f) => edits[f.path] !== undefined && edits[f.path] !== (f.value ?? ''));
  const actionLabel = approvedAt ? 'Update' : 'Approve';

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Same card frame as the Overview box, so the two read as peer sections. */}
      <div className="mb-4 rounded-md border border-neutral-800 p-3">
        <h2 className="text-lg font-semibold">Response fields</h2>
        <p className="text-xs text-neutral-400">{fields.length} values discovered at runtime</p>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {fields.map((field, i) => {
          const unresolved = field.kind !== 'json' && valueOf(field).trim() === '';
          const isSelected = field.path === selected;
          const startsGroup = field.group_name && field.group_name !== fields[i - 1]?.group_name;
          const groupSize = field.group_name
            ? new Set(fields.filter((f) => f.group_name === field.group_name).map((f) => f.item_index)).size
            : 0;

          return (
            <div key={field.path}>
              {startsGroup && (
                <div className="mb-1.5 mt-3 flex items-baseline gap-2">
                  <h3 className="text-xs font-semibold">{labelFor(field.group_name!)}</h3>
                  <span className="text-[10px] text-neutral-400">{groupSize} items</span>
                </div>
              )}

              <div
                onClick={() => onSelect(field.path)}
                className={`mb-2 cursor-pointer rounded-md border p-2 ${field.group_name ? 'ml-3' : ''} ${
                  isSelected ? 'border-blue-500' : 'border-neutral-800'
                }`}
              >
                <div className="mb-1.5 flex items-center gap-2">
                  {field.item_index !== null && (
                    <span className="text-[10px] text-neutral-400">#{field.item_index + 1}</span>
                  )}
                  <span className="text-xs font-semibold">{labelFor(field.type_key)}</span>
                  {isSelected && field.coord && (
                    <Badge variant="outline" className="border-blue-600/40 bg-blue-600/10 text-[10px] text-blue-400">
                      on page
                    </Badge>
                  )}
                  <span className="flex-1" />
                  {field.human_changed && (
                    <Badge variant="secondary" className="text-[10px]">
                      corrected
                    </Badge>
                  )}
                  {field.kind === 'json' ? (
                    <Badge variant="outline" className="text-[10px]">
                      nested
                    </Badge>
                  ) : field.confidence !== null ? (
                    <Badge variant={confidenceVariant(field.confidence)} className="text-[10px]">
                      {`${Math.round(field.confidence * 100)}%`}
                    </Badge>
                  ) : unresolved ? (
                    <Badge variant="destructive" className="text-[10px]">
                      needs review
                    </Badge>
                  ) : null}
                </div>

                {field.kind === 'json' ? (
                  <pre className="max-h-32 overflow-auto rounded-md border border-neutral-800 bg-neutral-900/60 p-2 text-[10px]">
                    {field.value ?? '—'}
                  </pre>
                ) : (
                  /* Always type="text": a native number input coerces DECIMAL to
                     a float, so 109303.32 round-trips as 109303.3203125. */
                  <Input
                    type="text"
                    inputMode={field.kind === 'number' ? 'decimal' : 'text'}
                    value={valueOf(field)}
                    onChange={(e) => onEdit(field.path, e.target.value)}
                    placeholder={unresolved ? 'enter value' : ''}
                    className={unresolved ? 'border-red-700 placeholder:text-red-400' : ''}
                  />
                )}
                {field.human_changed && field.model_value !== null && (
                  <p className="mt-1 truncate text-[10px] text-neutral-400">was {field.model_value} · model</p>
                )}
                <p className="mt-1 truncate text-[10px] text-neutral-500">
                  {hasConfidence || field.confidence !== null ? field.kind : `${field.kind} · no confidence reported`}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {error && <p className="mt-3 text-xs text-red-400">{error}</p>}
      {blocked && (
        <p className="mt-3 text-xs text-red-400">
          {missing.length} value{missing.length === 1 ? '' : 's'} still needs a value before this document can be
          approved.
        </p>
      )}

      <Button
        className="mt-3 w-full"
        disabled={blocked || approving || (approvedAt !== null && !dirty)}
        onClick={onApprove}
      >
        {approving ? 'Saving…' : actionLabel}
      </Button>
    </div>
  );
}
