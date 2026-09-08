import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import type { AuditListResponse } from "../types";

const PAGE = 50;

export function AuditLogPage() {
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [offset, setOffset] = useState(0);

  const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  if (action) params.set("action", action);
  if (entityType) params.set("entity_type", entityType);

  const query = useQuery({
    queryKey: ["audit", action, entityType, offset],
    queryFn: () => api<AuditListResponse>(`/audit-logs?${params}`),
  });

  const control =
    "rounded-md border border-input bg-background px-3 py-1.5 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";
  const data = query.data;

  return (
    <div>
      <h1 className="font-heading text-xl font-bold text-foreground">Audit Log</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Every mutation and AI action — who, what, when, and the before/after state.
        Admin only.
      </p>

      {query.error instanceof ApiError && query.error.status === 403 && (
        <p className="mt-6 text-sm text-destructive">
          You need an admin account to view the audit log.
        </p>
      )}

      {!(query.error instanceof ApiError && query.error.status === 403) && (
        <>
          <div className="mt-4 flex flex-wrap gap-2">
            <input
              className={control}
              placeholder="action (e.g. official.create)"
              value={action}
              onChange={(e) => {
                setAction(e.target.value);
                setOffset(0);
              }}
            />
            <input
              className={control}
              placeholder="entity type (e.g. relationship)"
              value={entityType}
              onChange={(e) => {
                setEntityType(e.target.value);
                setOffset(0);
              }}
            />
          </div>

          <div className="mt-4 overflow-x-auto rounded-lg border border-border bg-card shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-muted text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">When</th>
                  <th className="px-3 py-2 font-medium">Actor</th>
                  <th className="px-3 py-2 font-medium">Action</th>
                  <th className="px-3 py-2 font-medium">Entity</th>
                  <th className="px-3 py-2 font-medium">After</th>
                </tr>
              </thead>
              <tbody>
                {query.isPending && (
                  <tr>
                    <td className="px-3 py-3 text-muted-foreground" colSpan={5}>
                      Loading…
                    </td>
                  </tr>
                )}
                {data?.items.map((e) => (
                  <tr key={e.id} className="border-t border-border align-top">
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {new Date(e.at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {e.actor_id ? `#${e.actor_id}` : "system"}
                    </td>
                    <td className="px-3 py-2 font-medium text-foreground">{e.action}</td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {e.entity_type}
                      {e.entity_id ? ` · ${e.entity_id}` : ""}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {e.after ? (
                        <code className="whitespace-pre-wrap break-all">
                          {JSON.stringify(e.after)}
                        </code>
                      ) : (
                        ""
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data && data.total > PAGE && (
            <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
              <span>
                {offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}
              </span>
              <div className="flex gap-2">
                <button
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE))}
                  className="rounded border border-border px-2 py-1 disabled:opacity-40"
                >
                  Prev
                </button>
                <button
                  disabled={offset + PAGE >= data.total}
                  onClick={() => setOffset(offset + PAGE)}
                  className="rounded border border-border px-2 py-1 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
