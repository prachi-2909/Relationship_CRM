import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Badge } from "../components/Badge";
import { bandFor } from "../components/ScoreDial";
import { useAuth } from "../auth/AuthProvider";
import { api, ApiError } from "../lib/api";
import {
  IMPORTANCE_VALUES,
  RELATIONSHIP_STATUSES,
  type Importance,
  type OfficialSummary,
  type RelationshipListResponse,
  type RelationshipStatus,
  type RiskLevel,
} from "../types";

const PAGE = 25;
const RISK_TONE: Record<RiskLevel, "good" | "warn" | "danger"> = {
  low: "good",
  medium: "warn",
  high: "danger",
};

export function RelationshipsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canEdit = user?.role === "admin" || user?.role === "relationship_manager";

  const [mine, setMine] = useState(false);
  const [status, setStatus] = useState<RelationshipStatus | "">("");
  const [importance, setImportance] = useState<Importance | "">("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [showForm, setShowForm] = useState(false);

  const params = new URLSearchParams({
    limit: String(PAGE),
    offset: String(offset),
    sort: "-score",
  });
  if (mine) params.set("mine", "true");
  if (status) params.set("status", status);
  if (importance) params.set("importance", importance);
  if (q) params.set("q", q);

  const listQuery = useQuery({
    queryKey: ["relationships", mine, status, importance, q, offset],
    queryFn: () => api<RelationshipListResponse>(`/relationships?${params}`),
  });

  const data = listQuery.data;
  const input =
    "rounded-md border border-input bg-background px-3 py-1.5 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-xl font-bold text-foreground">Relationships</h1>
        {canEdit && (
          <button
            onClick={() => setShowForm((v) => !v)}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground hover:bg-secondary"
          >
            {showForm ? "Cancel" : "New relationship"}
          </button>
        )}
      </div>

      {showForm && (
        <NewRelationshipForm
          onDone={() => {
            queryClient.invalidateQueries({ queryKey: ["relationships"] });
            setShowForm(false);
          }}
        />
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={mine}
            onChange={(e) => {
              setMine(e.target.checked);
              setOffset(0);
            }}
          />
          Mine only
        </label>
        <input
          className={input}
          placeholder="Official name…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
        />
        <select
          className={input}
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as RelationshipStatus | "");
            setOffset(0);
          }}
        >
          <option value="">Any status</option>
          {RELATIONSHIP_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s.replace("_", " ")}
            </option>
          ))}
        </select>
        <select
          className={input}
          value={importance}
          onChange={(e) => {
            setImportance(e.target.value as Importance | "");
            setOffset(0);
          }}
        >
          <option value="">Any importance</option>
          {IMPORTANCE_VALUES.map((i) => (
            <option key={i} value={i}>
              {i}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card shadow-sm">
        {listQuery.isPending && (
          <div className="p-4 text-sm text-muted-foreground">Loading…</div>
        )}
        {data && data.items.length === 0 && (
          <div className="p-6 text-sm text-muted-foreground">No relationships match.</div>
        )}
        {data && data.items.length > 0 && (
          <table className="w-full text-sm">
            <thead className="bg-muted text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">Official</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Importance</th>
                <th className="px-4 py-2 font-medium">Score</th>
                <th className="px-4 py-2 font-medium">Owner</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => {
                const band = bandFor(r.score);
                return (
                  <tr key={r.id} className="border-t border-border hover:bg-muted/50">
                    <td className="px-4 py-2">
                      <Link
                        to={`/relationships/${r.id}`}
                        className="font-medium text-secondary hover:underline"
                      >
                        {r.official_name}
                      </Link>
                      {r.official_level && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          {r.official_level}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 capitalize text-muted-foreground">
                      {r.status.replace("_", " ")}
                    </td>
                    <td className="px-4 py-2 capitalize">{r.importance}</td>
                    <td className="px-4 py-2">
                      <span className="mr-2 font-semibold tabular-nums">{r.score}</span>
                      <Badge tone={RISK_TONE[band.risk]}>{band.label}</Badge>
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">
                      {r.owner_id ? `user #${r.owner_id}` : "unowned"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
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

function NewRelationshipForm({ onDone }: { onDone: () => void }) {
  const [q, setQ] = useState("");
  const [officialId, setOfficialId] = useState<number | null>(null);

  const search = useQuery({
    queryKey: ["officials", "picker", q],
    queryFn: () =>
      api<{ items: OfficialSummary[] }>(
        `/officials?limit=10${q ? `&q=${encodeURIComponent(q)}` : ""}`,
      ),
  });

  const create = useMutation({
    mutationFn: () =>
      api("/relationships", {
        method: "POST",
        body: JSON.stringify({ official_id: officialId }),
      }),
    onSuccess: onDone,
  });

  const input =
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <div className="mt-4 rounded-lg border border-border bg-card shadow-sm p-4">
      <input
        className={input}
        placeholder="Search officials…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <div className="mt-2 max-h-48 overflow-y-auto rounded border border-border">
        {search.data?.items.map((o) => (
          <button
            key={o.id}
            onClick={() => setOfficialId(o.id)}
            className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-muted ${
              officialId === o.id ? "bg-primary/10" : ""
            }`}
          >
            <span className="font-medium text-foreground">{o.name}</span>
            <span className="text-xs text-muted-foreground">{o.level ?? ""}</span>
          </button>
        ))}
        {search.data?.items.length === 0 && (
          <div className="px-3 py-2 text-sm text-muted-foreground">No matches.</div>
        )}
      </div>
      {create.error instanceof ApiError && (
        <p className="mt-2 text-sm text-destructive">{create.error.message}</p>
      )}
      <button
        disabled={!officialId || create.isPending}
        onClick={() => create.mutate()}
        className="mt-3 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-secondary disabled:opacity-50"
      >
        {create.isPending ? "Creating…" : "Create relationship"}
      </button>
    </div>
  );
}
