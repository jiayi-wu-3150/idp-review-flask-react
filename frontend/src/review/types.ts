/**
 * The server does the shape discovery, so the client only renders what it is
 * given. These types mirror `review/fields.py` exactly.
 */
export type Field = {
  path: string;
  type_key: string;
  group_name: string | null;
  item_index: number | null;
  /** The agreed value: the approved one if there is one, else the model's. */
  value: string | null;
  model_value: string | null;
  confidence: number | null;
  human_changed: boolean;
  /** [x1, y1, x2, y2] in page pixels, or null when nothing cites this value. */
  coord: number[] | null;
  page_id: number | null;
  image_file: string | null;
  kind: 'number' | 'text' | 'json';
};

export type DocumentRow = {
  id: string;
  approved: boolean;
  approved_at: string | null;
  approval_count: number;
};

export type Detail = {
  fields: Field[];
  has_confidence: boolean;
  has_citations: boolean;
  approver: string | null;
  approved_at: string | null;
  approval_count: number;
};
