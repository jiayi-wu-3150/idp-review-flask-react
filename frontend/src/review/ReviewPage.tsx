import { useCallback, useEffect, useRef, useState } from 'react';
import { DocumentList } from './DocumentList';
import { FieldList } from './FieldList';
import { OverviewBox, OverviewPages } from './Overview';
import { PageViewer } from './PageViewer';
import { Skeleton } from './ui';
import { shortLabels } from './bands';
import type { Detail, DocumentRow } from './types';

export function ReviewPage() {
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [loadingQueue, setLoadingQueue] = useState(true);

  const [docId, setDocId] = useState<string>();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const [fieldPath, setFieldPath] = useState<string>();
  const [view, setView] = useState<'overview' | 'review'>('overview');
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [approving, setApproving] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);
  /** Covers the gap between a successful write and the next queue load. */
  const [approvedLocally, setApprovedLocally] = useState<Record<string, string>>({});

  const loadQueue = useCallback(async () => {
    setLoadingQueue(true);
    try {
      const res = await fetch('/api/documents');
      const body: unknown = await res.json();
      if (!res.ok) throw new Error((body as { error?: string }).error ?? `HTTP ${res.status}`);
      setDocuments(body as DocumentRow[]);
      setQueueError(null);
    } catch (err) {
      setQueueError(err instanceof Error ? err.message : 'Failed to load the queue');
    } finally {
      setLoadingQueue(false);
    }
  }, []);

  useEffect(() => {
    void loadQueue();
  }, [loadQueue]);

  /* Select the top of the queue exactly once, and only when it is complete: a
     queue that finishes loading mid-render would otherwise move the selection. */
  const autoSelected = useRef(false);
  useEffect(() => {
    if (autoSelected.current || docId || loadingQueue || !documents.length) return;
    autoSelected.current = true;
    setDocId(documents[0].id);
  }, [docId, loadingQueue, documents]);

  useEffect(() => {
    if (!docId) return;
    let cancelled = false;
    setLoadingDetail(true);
    void (async () => {
      try {
        const res = await fetch(`/api/document?id=${encodeURIComponent(docId)}`);
        const body: unknown = await res.json();
        if (!res.ok) throw new Error((body as { error?: string }).error ?? `HTTP ${res.status}`);
        if (!cancelled) setDetail(body as Detail);
      } catch (err) {
        if (!cancelled) setApproveError(err instanceof Error ? err.message : 'Failed to load');
      } finally {
        if (!cancelled) setLoadingDetail(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [docId]);

  const fields = detail?.fields ?? [];
  const selectedField = fields.find((f) => f.path === fieldPath) ?? fields[0];
  const label = docId ? shortLabels(documents.map((d) => d.id))[docId] : '';
  const approvedAt = detail?.approved_at ?? (docId ? (approvedLocally[docId] ?? null) : null);

  const select = (path: string) => {
    setFieldPath(path);
    setView('review');
  };

  const approve = async () => {
    if (!docId) return;
    setApproving(true);
    setApproveError(null);
    try {
      const res = await fetch('/api/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: docId, edits }),
      });
      const body: unknown = await res.json();
      if (!res.ok) throw new Error((body as { error?: string }).error ?? `HTTP ${res.status}`);
      setApprovedLocally((prev) => ({ ...prev, [docId]: new Date().toISOString() }));
      setEdits({});
      await loadQueue();
    } catch (err) {
      setApproveError(err instanceof Error ? err.message : 'Failed to approve');
    } finally {
      setApproving(false);
    }
  };

  if (queueError) {
    return (
      <div className="rounded-md bg-red-950/40 p-4 text-sm text-red-300">
        <p className="font-semibold">{queueError}</p>
        <p className="mt-1 text-xs">
          Set <code>INPUT_TABLE</code> to your <code>catalog.schema.table</code>, then run{' '}
          <code>python scripts/setup.py</code> to create the approval log and view.
        </p>
      </div>
    );
  }
  if (loadingQueue) return <Skeleton className="h-96 w-full" />;

  const pending = documents.filter((d) => !d.approved && !(d.id in approvedLocally)).length;

  return (
    <div className="flex h-[calc(100vh-8rem)] overflow-hidden rounded-lg border border-neutral-800">
      <DocumentList
        documents={documents.map((d) => (d.id in approvedLocally ? { ...d, approved: true } : d))}
        pending={pending}
        selected={docId}
        onSelect={(id) => {
          setDocId(id);
          setFieldPath(undefined);
          setView('overview');
          setEdits({});
          setApproveError(null);
        }}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        {/* The id is a volume path sharing a long prefix with every other
            document, so it gets its own line at full length. */}
        <div className="border-b border-neutral-800 px-4 py-2">
          <div className="flex items-baseline gap-3">
            <span className="text-sm font-semibold">{label}</span>
            {approvedAt && (
              <span className="text-xs text-neutral-400">
                Approved by {detail?.approver ?? 'you'}
                {detail?.approval_count ? ` · ${detail.approval_count} approval${detail.approval_count > 1 ? 's' : ''}` : ''}
              </span>
            )}
          </div>
          <div className="break-all text-xs text-neutral-500">{docId}</div>
        </div>
        {loadingDetail ? (
          <Skeleton className="m-4 flex-1" />
        ) : view === 'overview' ? (
          <OverviewPages fields={fields} onSelect={select} />
        ) : (
          <PageViewer fields={fields} selected={selectedField} />
        )}
      </div>

      <div className="flex w-80 shrink-0 flex-col overflow-hidden border-l border-neutral-800 p-4">
        <OverviewBox
          fields={fields}
          hasConfidence={detail?.has_confidence ?? false}
          active={view === 'overview'}
          onClick={() => setView('overview')}
        />
        <FieldList
          fields={fields}
          hasConfidence={detail?.has_confidence ?? false}
          selected={view === 'review' ? selectedField?.path : undefined}
          onSelect={select}
          edits={edits}
          onEdit={(path, value) => setEdits((prev) => ({ ...prev, [path]: value }))}
          onApprove={() => {
            void approve();
          }}
          approving={approving}
          approvedAt={approvedAt}
          error={approveError}
        />
      </div>
    </div>
  );
}
