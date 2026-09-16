import { useMemo, useState, type SVGProps } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Badge } from "../components/Badge";
import { useAuth } from "../auth/AuthProvider";
import { api, ApiError } from "../lib/api";
import {
  AGENT_REC_TYPE_LABELS,
  RECOMMENDATION_STATUS_TONE,
  RISK_TIER_TONE,
  type AgentRunListResponse,
  type AgentRunSummary,
  type RecommendationDetail,
  type RecommendationListResponse,
  type RecommendationStatus,
  type RecommendationType,
  type RelationshipListResponse,
} from "../types";

const EVIDENCE_LABELS: Record<string, string> = {
  trigger: "Trigger",
  days_since_last_contact: "Days since last contact",
  score: "Score",
  band: "Relationship band",
  open_moments: "Open moments",
};

const RISK_BORDER: Record<string, string> = {
  low: "border-l-accent",
  medium: "border-l-saffron",
  high: "border-l-destructive",
};

const STATUS_ORDER: RecommendationStatus[] = ["pending", "approved", "rejected", "expired"];

function IconSparkle(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" {...props}>
      <path d="M9.5 2.2c.16-.5.86-.5 1.02 0l1.2 3.75a3.2 3.2 0 0 0 2.05 2.05l3.75 1.2c.5.16.5.86 0 1.02l-3.75 1.2a3.2 3.2 0 0 0-2.05 2.05l-1.2 3.75c-.16.5-.86.5-1.02 0l-1.2-3.75a3.2 3.2 0 0 0-2.05-2.05l-3.75-1.2c-.5-.16-.5-.86 0-1.02l3.75-1.2a3.2 3.2 0 0 0 2.05-2.05l1.2-3.75z" />
    </svg>
  );
}

function IconTask(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <rect x="3.5" y="3.5" width="13" height="13" rx="3" />
      <path d="M6.8 10.2l2 2 4.4-4.6" />
    </svg>
  );
}

function IconMoment(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <rect x="3" y="4.5" width="14" height="12" rx="2.5" />
      <path d="M3 8.3h14M7 3v3M13 3v3" />
      <path d="M10 14.1c-1.7-1.2-2.7-2-2.7-3.1a1.55 1.55 0 0 1 2.7-1 1.55 1.55 0 0 1 2.7 1c0 1.1-1 1.9-2.7 3.1z" />
    </svg>
  );
}

function IconOpportunity(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M3 14.2l4.4-4.7 3 3L17 5" />
      <path d="M12.6 5H17v4.4" />
    </svg>
  );
}

const REC_TYPE_ICON: Record<RecommendationType, (props: SVGProps<SVGSVGElement>) => JSX.Element> = {
  create_task: IconTask,
  draft_moment: IconMoment,
  create_opportunity: IconOpportunity,
};

export function AgentPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const canEdit = isAdmin || user?.role === "relationship_manager";
  const queryClient = useQueryClient();

  const [view, setView] = useState<"recommendations" | "runs">("recommendations");
  const [status, setStatus] = useState<RecommendationStatus | "">("pending");
  const [type, setType] = useState<RecommendationType | "">("");
  const [selected, setSelected] = useState<number | null>(null);

  const params = new URLSearchParams({ limit: "100" });
  if (status) params.set("status", status);
  if (type) params.set("type", type);

  const listQuery = useQuery({
    queryKey: ["agent", "recommendations", status, type],
    queryFn: () => api<RecommendationListResponse>(`/agent/recommendations?${params}`),
    enabled: view === "recommendations",
  });
  const allRecsQuery = useQuery({
    queryKey: ["agent", "recommendations", "all-for-stats"],
    queryFn: () => api<RecommendationListResponse>(`/agent/recommendations?limit=200`),
  });
  const runsQuery = useQuery({
    queryKey: ["agent", "runs"],
    queryFn: () => api<AgentRunListResponse>("/agent/runs?limit=20"),
    enabled: view === "runs",
  });
  const detailQuery = useQuery({
    queryKey: ["agent", "recommendation", selected],
    queryFn: () => api<RecommendationDetail>(`/agent/recommendations/${selected}`),
    enabled: selected !== null,
  });

  const statusCounts = useMemo(() => {
    const counts: Record<RecommendationStatus, number> = {
      pending: 0,
      approved: 0,
      rejected: 0,
      expired: 0,
    };
    for (const r of allRecsQuery.data?.items ?? []) counts[r.status]++;
    return counts;
  }, [allRecsQuery.data]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["agent"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    queryClient.invalidateQueries({ queryKey: ["tasks"] });
    queryClient.invalidateQueries({ queryKey: ["moments"] });
    queryClient.invalidateQueries({ queryKey: ["opportunities"] });
  };

  const control =
    "rounded-lg border border-input bg-surface px-3 py-1.5 text-sm text-foreground outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/25";

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-secondary text-primary-foreground shadow-glow-primary">
          <IconSparkle className="h-5 w-5" />
        </span>
        <div>
          <h1 className="font-heading text-xl font-bold text-foreground">Autonomous Agent</h1>
          <p className="text-sm text-muted-foreground">
            Observe and recommend only — nothing is created or sent until a human approves it.
          </p>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {STATUS_ORDER.map((s) => (
          <button
            key={s}
            onClick={() => {
              setView("recommendations");
              setStatus(s === status ? "" : s);
            }}
            className={`rounded-xl border bg-card p-3.5 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md ${
              status === s ? "border-primary ring-2 ring-ring/25" : "border-border"
            }`}
          >
            <div className="text-2xl font-bold tabular-nums text-foreground">
              {statusCounts[s]}
            </div>
            <div className="mt-0.5 text-xs capitalize text-muted-foreground">{s}</div>
          </button>
        ))}
      </div>

      {canEdit && (
        <div className="mt-5 rounded-xl border border-border bg-card p-4 shadow-sm">
          <TriggerRunControl isAdmin={isAdmin} onDone={invalidate} />
        </div>
      )}

      <div className="mt-5 inline-flex rounded-lg border border-border bg-card p-0.5 text-xs shadow-sm">
        {(["recommendations", "runs"] as const).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
              view === v
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:bg-muted"
            }`}
          >
            {v === "recommendations" ? "Recommendations" : "Run history"}
          </button>
        ))}
      </div>

      {view === "recommendations" && (
        <>
          <div className="mt-4 flex flex-wrap gap-2">
            <select
              className={control}
              value={status}
              onChange={(e) => setStatus(e.target.value as RecommendationStatus | "")}
            >
              <option value="">Any status</option>
              {STATUS_ORDER.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select
              className={control}
              value={type}
              onChange={(e) => setType(e.target.value as RecommendationType | "")}
            >
              <option value="">Any type</option>
              {(Object.keys(AGENT_REC_TYPE_LABELS) as RecommendationType[]).map((t) => (
                <option key={t} value={t}>
                  {AGENT_REC_TYPE_LABELS[t]}
                </option>
              ))}
            </select>
          </div>

          <div className="mt-4 grid gap-6 lg:grid-cols-[1fr_1.4fr]">
            <div className="space-y-2.5">
              {listQuery.isPending && (
                <div className="rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground shadow-sm">
                  Loading…
                </div>
              )}
              {listQuery.data && listQuery.data.items.length === 0 && (
                <div className="rounded-xl border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground shadow-sm">
                  <IconSparkle className="mx-auto mb-2 h-6 w-6 text-muted-foreground/40" />
                  No recommendations. Run the agent on a relationship, or your whole
                  portfolio, to generate some.
                </div>
              )}
              {listQuery.data?.items.map((r) => {
                const Icon = REC_TYPE_ICON[r.type];
                return (
                  <button
                    key={r.id}
                    onClick={() => setSelected(r.id)}
                    className={`flex w-full items-start gap-3 rounded-xl border-l-4 border border-border bg-card p-3.5 text-left text-sm shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md ${
                      RISK_BORDER[r.risk_tier]
                    } ${selected === r.id ? "ring-2 ring-ring/30" : ""}`}
                  >
                    <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-secondary">
                      <Icon className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="font-medium text-foreground">
                          {AGENT_REC_TYPE_LABELS[r.type]}
                        </span>
                        <Badge tone={RECOMMENDATION_STATUS_TONE[r.status]}>{r.status}</Badge>
                      </span>
                      <span className="mt-0.5 block truncate text-muted-foreground">
                        {r.official_name}
                      </span>
                      <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground/80">
                        <Badge tone={RISK_TIER_TONE[r.risk_tier]}>{r.risk_tier} risk</Badge>
                        <span>{new Date(r.created_at).toLocaleDateString()}</span>
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>

            <div>
              {!detailQuery.data && (
                <div className="flex h-full min-h-[12rem] items-center justify-center rounded-xl border border-dashed border-border text-sm text-muted-foreground">
                  Select a recommendation to review it.
                </div>
              )}
              {detailQuery.data && (
                <RecommendationPanel
                  key={detailQuery.data.id}
                  rec={detailQuery.data}
                  canEdit={canEdit}
                  onChanged={invalidate}
                />
              )}
            </div>
          </div>
        </>
      )}

      {view === "runs" && (
        <div className="mt-4 overflow-hidden rounded-xl border border-border bg-card shadow-sm">
          {runsQuery.isPending && (
            <div className="p-4 text-sm text-muted-foreground">Loading…</div>
          )}
          {runsQuery.data && runsQuery.data.items.length === 0 && (
            <div className="p-6 text-sm text-muted-foreground">No runs yet.</div>
          )}
          {runsQuery.data && runsQuery.data.items.length > 0 && (
            <table className="w-full text-sm">
              <thead className="bg-muted text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 font-medium">Started</th>
                  <th className="px-4 py-2 font-medium">Trigger</th>
                  <th className="px-4 py-2 font-medium">Scope</th>
                  <th className="px-4 py-2 font-medium">Model</th>
                  <th className="px-4 py-2 font-medium">Considered</th>
                  <th className="px-4 py-2 font-medium">Recommendations</th>
                  <th className="px-4 py-2 font-medium">Duration</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {runsQuery.data.items.map((r: AgentRunSummary) => (
                  <tr key={r.id} className="border-t border-border align-top hover:bg-muted/40">
                    <td className="px-4 py-2 text-xs text-muted-foreground">
                      {new Date(r.started_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-2 capitalize">{r.trigger}</td>
                    <td className="px-4 py-2 capitalize">
                      {r.scope}
                      {r.relationship_id && (
                        <Link
                          to={`/relationships/${r.relationship_id}`}
                          className="ml-1 text-xs text-secondary hover:underline"
                        >
                          view
                        </Link>
                      )}
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">{r.model}</td>
                    <td className="px-4 py-2 tabular-nums">{r.relationships_considered}</td>
                    <td className="px-4 py-2 tabular-nums">{r.recommendations_created}</td>
                    <td className="px-4 py-2 text-muted-foreground">
                      {r.duration_ms != null ? `${r.duration_ms} ms` : "—"}
                    </td>
                    <td className="px-4 py-2">
                      <Badge
                        tone={
                          r.status === "completed"
                            ? "good"
                            : r.status === "failed"
                              ? "danger"
                              : "neutral"
                        }
                      >
                        {r.status}
                      </Badge>
                      {r.error && (
                        <div className="mt-0.5 text-xs text-destructive">{r.error}</div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

function TriggerRunControl({ isAdmin, onDone }: { isAdmin: boolean; onDone: () => void }) {
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<{ id: number; name: string } | null>(null);

  const searchQuery = useQuery({
    queryKey: ["relationships", "agent-picker", query],
    queryFn: () =>
      api<RelationshipListResponse>(
        `/relationships?limit=6${query ? `&q=${encodeURIComponent(query)}` : ""}`,
      ),
    enabled: query.trim().length >= 2 && !picked,
  });

  const trigger = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api("/agent/runs", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      setPicked(null);
      setQuery("");
      onDone();
    },
  });

  return (
    <div className="flex flex-wrap items-center gap-2.5">
      <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Run the agent
      </span>
      <div className="relative">
        {picked ? (
          <span className="flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm">
            {picked.name}
            <button
              onClick={() => setPicked(null)}
              className="text-xs text-muted-foreground hover:underline"
            >
              change
            </button>
          </span>
        ) : (
          <input
            className="w-56 rounded-lg border border-input bg-surface px-3 py-1.5 text-sm outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/25"
            placeholder="Search a relationship…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        )}
        {!picked && searchQuery.data && searchQuery.data.items.length > 0 && (
          <ul className="absolute z-10 mt-1 w-56 overflow-hidden rounded-lg border border-border bg-card shadow-md">
            {searchQuery.data.items.map((r) => (
              <li key={r.id}>
                <button
                  onClick={() => {
                    setPicked({ id: r.id, name: r.official_name });
                    setQuery("");
                  }}
                  className="block w-full px-2.5 py-1.5 text-left text-sm hover:bg-muted"
                >
                  {r.official_name}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <button
        disabled={!picked || trigger.isPending}
        onClick={() =>
          picked &&
          trigger.mutate({ scope: "relationship", relationship_id: picked.id })
        }
        className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-saffron to-[hsl(36_78%_46%)] px-3.5 py-1.5 text-sm font-semibold text-secondary-foreground shadow-glow-gold transition-transform hover:-translate-y-0.5 disabled:pointer-events-none disabled:opacity-50 disabled:shadow-none"
      >
        <IconSparkle className="h-3.5 w-3.5" />
        {trigger.isPending ? "Running…" : "Run on relationship"}
      </button>
      <button
        disabled={trigger.isPending}
        onClick={() => trigger.mutate({ scope: "portfolio" })}
        className="rounded-lg border border-border bg-surface px-3.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted disabled:opacity-50"
        title={isAdmin ? "Evaluates the whole portfolio" : "Evaluates your own relationships"}
      >
        {trigger.isPending ? "Running…" : isAdmin ? "Run on whole portfolio" : "Run on my portfolio"}
      </button>
      {trigger.error instanceof ApiError && (
        <span className="text-xs text-destructive">{trigger.error.message}</span>
      )}
    </div>
  );
}

function RecommendationPanel({
  rec,
  canEdit,
  onChanged,
}: {
  rec: RecommendationDetail;
  canEdit: boolean;
  onChanged: () => void;
}) {
  const approve = useMutation({
    mutationFn: () => api(`/agent/recommendations/${rec.id}/approve`, { method: "POST" }),
    onSuccess: onChanged,
  });
  const reject = useMutation({
    mutationFn: () =>
      api(`/agent/recommendations/${rec.id}/reject`, {
        method: "POST",
        body: JSON.stringify({ reason: null }),
      }),
    onSuccess: onChanged,
  });

  const evidenceEntries = Object.entries(rec.evidence).filter(
    ([, v]) => v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0),
  );
  const Icon = REC_TYPE_ICON[rec.type];

  return (
    <div className="fade-in-up space-y-4">
      <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
        <div className="mb-2 flex items-start justify-between gap-2">
          <span className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-secondary">
              <Icon className="h-4 w-4" />
            </span>
            <span className="font-heading text-sm font-semibold text-foreground">
              {AGENT_REC_TYPE_LABELS[rec.type]}
            </span>
          </span>
          <Link
            to={`/relationships/${rec.relationship_id}`}
            className="shrink-0 text-xs text-secondary hover:underline"
          >
            {rec.official_name} →
          </Link>
        </div>
        <p className="text-sm text-foreground">{rec.reasoning}</p>
      </div>

      <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
        <div className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          <IconSparkle className="h-3.5 w-3.5 text-saffron" />
          Why now?
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
          {evidenceEntries.map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="text-muted-foreground">{EVIDENCE_LABELS[key] ?? key}</dt>
              <dd className="text-right font-medium text-foreground">
                {typeof value === "object" ? JSON.stringify(value) : String(value)}
              </dd>
            </div>
          ))}
          {evidenceEntries.length === 0 && (
            <dd className="col-span-2 text-muted-foreground">No structured evidence.</dd>
          )}
        </dl>
      </div>

      <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Decision
          </span>
          <Badge tone={RECOMMENDATION_STATUS_TONE[rec.status]}>{rec.status}</Badge>
        </div>

        {rec.status === "pending" && canEdit && (
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => approve.mutate()}
              disabled={approve.isPending}
              className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-saffron to-[hsl(36_78%_46%)] px-4 py-1.5 text-sm font-semibold text-secondary-foreground shadow-glow-gold transition-transform hover:-translate-y-0.5 disabled:pointer-events-none disabled:opacity-60 disabled:shadow-none"
            >
              <IconTask className="h-3.5 w-3.5" />
              {approve.isPending ? "Approving…" : "Approve"}
            </button>
            <button
              onClick={() => reject.mutate()}
              disabled={reject.isPending}
              className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted disabled:opacity-60"
            >
              {reject.isPending ? "Rejecting…" : "Reject"}
            </button>
          </div>
        )}
        {rec.status !== "pending" && rec.result_ref && (
          <p className="rounded-lg bg-muted px-3 py-2 font-mono text-xs text-muted-foreground">
            {JSON.stringify(rec.result_ref)}
          </p>
        )}
        {(approve.error instanceof ApiError || reject.error instanceof ApiError) && (
          <p className="mt-2 text-xs text-destructive">
            {(approve.error as ApiError)?.message ?? (reject.error as ApiError)?.message}
          </p>
        )}
      </div>
    </div>
  );
}
