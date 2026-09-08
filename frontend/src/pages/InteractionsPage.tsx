import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Badge } from "../components/Badge";
import { api } from "../lib/api";
import {
  INTERACTION_TYPES,
  SENTIMENT_TONE,
  type InteractionListResponse,
  type InteractionType,
} from "../types";

const PAGE = 30;

export function InteractionsPage() {
  const [type, setType] = useState<InteractionType | "">("");
  const [offset, setOffset] = useState(0);

  const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  if (type) params.set("type", type);

  const query = useQuery({
    queryKey: ["interactions", "all", type, offset],
    queryFn: () => api<InteractionListResponse>(`/interactions?${params}`),
  });

  const data = query.data;
  const input =
    "rounded-md border border-input bg-background px-3 py-1.5 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <div>
      <h1 className="font-heading text-xl font-bold text-foreground">Interactions</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Every logged contact across all relationships.
      </p>

      <div className="mt-4">
        <select
          className={input}
          value={type}
          onChange={(e) => {
            setType(e.target.value as InteractionType | "");
            setOffset(0);
          }}
        >
          <option value="">All types</option>
          {INTERACTION_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card shadow-sm">
        {query.isPending && (
          <div className="p-4 text-sm text-muted-foreground">Loading…</div>
        )}
        {data && data.items.length === 0 && (
          <div className="p-6 text-sm text-muted-foreground">Nothing logged yet.</div>
        )}
        {data?.items.map((it) => (
          <Link
            key={it.id}
            to={`/relationships/${it.relationship_id}`}
            className="flex items-start justify-between gap-3 border-b border-border px-4 py-3 text-sm last:border-b-0 hover:bg-muted/50"
          >
            <div>
              <div className="flex items-center gap-2">
                <span className="font-medium capitalize text-foreground">
                  {it.type} · {it.direction}
                </span>
                <Badge tone={SENTIMENT_TONE[it.sentiment]}>{it.sentiment}</Badge>
              </div>
              <p className="mt-1 text-muted-foreground">{it.ai_summary ?? "—"}</p>
            </div>
            <span className="shrink-0 text-xs text-muted-foreground">
              {new Date(it.occurred_at).toLocaleDateString()}
            </span>
          </Link>
        ))}
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
    </div>
  );
}
