import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Badge } from "../components/Badge";
import { useAuth } from "../auth/AuthProvider";
import { api, ApiError } from "../lib/api";
import {
  OPPORTUNITY_ACTIVITY_TYPES,
  OPPORTUNITY_STAGES,
  OPPORTUNITY_STAGE_LABELS,
  OPPORTUNITY_STATUS_TONE,
  type OpportunityActivityType,
  type OpportunityDetail,
  type OpportunityListResponse,
  type OpportunityStage,
  type OpportunityStatus,
  type OpportunitySummary,
  type RelationshipListResponse,
} from "../types";

export function OpportunitiesPage() {
  const { user } = useAuth();
  const canEdit = user?.role === "admin" || user?.role === "relationship_manager";
  const queryClient = useQueryClient();

  const [status, setStatus] = useState<OpportunityStatus | "">("");
  const [selected, setSelected] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);

  const params = new URLSearchParams({ limit: "200" });
  if (status) params.set("status", status);

  const listQuery = useQuery({
    queryKey: ["opportunities", status],
    queryFn: () => api<OpportunityListResponse>(`/opportunities?${params}`),
  });
  const detailQuery = useQuery({
    queryKey: ["opportunity", selected],
    queryFn: () => api<OpportunityDetail>(`/opportunities/${selected}`),
    enabled: selected !== null,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["opportunities"] });
    queryClient.invalidateQueries({ queryKey: ["opportunity", selected] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const createOpportunity = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<OpportunityDetail>("/opportunities", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      invalidate();
      setShowForm(false);
    },
  });

  const grouped = useMemo(() => {
    const byStage = new Map<OpportunityStage, OpportunitySummary[]>();
    for (const stage of OPPORTUNITY_STAGES) byStage.set(stage, []);
    for (const opp of listQuery.data?.items ?? []) {
      byStage.get(opp.stage)?.push(opp);
    }
    return byStage;
  }, [listQuery.data]);

  const control =
    "rounded-md border border-input bg-background px-3 py-1.5 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-heading text-xl font-bold text-foreground">Opportunities</h1>
        {canEdit && (
          <button
            onClick={() => setShowForm((v) => !v)}
            className={
              showForm
                ? "rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-semibold text-muted-foreground transition-colors hover:bg-muted"
                : "rounded-lg bg-gradient-to-br from-saffron to-[hsl(36_78%_46%)] px-3 py-1.5 text-sm font-semibold text-secondary-foreground shadow-glow-gold transition-transform hover:-translate-y-0.5"
            }
          >
            {showForm ? "Cancel" : "New opportunity"}
          </button>
        )}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        Detected from interaction notes, or added by hand. Every suggestion needs a
        human to confirm or dismiss it before it enters the pipeline.
      </p>

      {showForm && (
        <NewOpportunityForm
          pending={createOpportunity.isPending}
          error={createOpportunity.error}
          onSubmit={(body) => createOpportunity.mutate(body)}
        />
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <select
          className={control}
          value={status}
          onChange={(e) => setStatus(e.target.value as OpportunityStatus | "")}
        >
          <option value="">Any status</option>
          {(["suggested", "confirmed", "dismissed"] as const).map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4 grid gap-6 lg:grid-cols-[1.2fr_1.4fr]">
        <div className="space-y-4">
          {listQuery.isPending && (
            <div className="p-4 text-sm text-muted-foreground">Loading…</div>
          )}
          {listQuery.data && listQuery.data.items.length === 0 && (
            <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground shadow-sm">
              No opportunities yet.
            </div>
          )}
          {OPPORTUNITY_STAGES.map((stage) => {
            const items = grouped.get(stage) ?? [];
            if (items.length === 0) return null;
            return (
              <div
                key={stage}
                className="overflow-hidden rounded-lg border border-border bg-card shadow-sm"
              >
                <div className="border-b border-border bg-muted px-4 py-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {OPPORTUNITY_STAGE_LABELS[stage]}{" "}
                  <span className="text-muted-foreground/60">({items.length})</span>
                </div>
                {items.map((o) => (
                  <button
                    key={o.id}
                    onClick={() => setSelected(o.id)}
                    className={`block w-full border-b border-border px-4 py-3 text-left text-sm last:border-b-0 hover:bg-muted ${
                      selected === o.id ? "bg-primary/10" : ""
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-foreground">{o.title}</span>
                      <Badge tone={OPPORTUNITY_STATUS_TONE[o.status]}>{o.status}</Badge>
                    </div>
                    <div className="mt-1 text-muted-foreground">{o.official_name}</div>
                  </button>
                ))}
              </div>
            );
          })}
        </div>

        <div>
          {!detailQuery.data && (
            <p className="text-sm text-muted-foreground">
              Select an opportunity to review it.
            </p>
          )}
          {detailQuery.data && (
            <OpportunityPanel
              key={detailQuery.data.id}
              opp={detailQuery.data}
              canEdit={canEdit}
              onChanged={invalidate}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function NewOpportunityForm({
  pending,
  error,
  onSubmit,
}: {
  pending: boolean;
  error: unknown;
  onSubmit: (body: Record<string, unknown>) => void;
}) {
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<{ id: number; name: string } | null>(null);
  const [title, setTitle] = useState("");
  const [detail, setDetail] = useState("");

  const searchQuery = useQuery({
    queryKey: ["relationships", "opportunity-picker", query],
    queryFn: () =>
      api<RelationshipListResponse>(
        `/relationships?limit=6${query ? `&q=${encodeURIComponent(query)}` : ""}`,
      ),
    enabled: query.trim().length >= 2 && !picked,
  });

  const field =
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (picked) onSubmit({ relationship_id: picked.id, title, detail: detail || null });
      }}
      className="mt-4 grid gap-3 rounded-lg border border-border bg-card shadow-sm p-4 sm:grid-cols-2"
    >
      <div className="relative sm:col-span-2">
        <label className="mb-1 block text-sm font-medium text-foreground">Relationship</label>
        {picked ? (
          <span className="flex items-center gap-2 text-sm">
            {picked.name}
            <button
              type="button"
              onClick={() => setPicked(null)}
              className="text-xs text-muted-foreground hover:underline"
            >
              change
            </button>
          </span>
        ) : (
          <>
            <input
              className={field}
              placeholder="Search officials…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {searchQuery.data && searchQuery.data.items.length > 0 && (
              <ul className="absolute z-10 mt-1 w-full rounded-md border border-border bg-card shadow-sm">
                {searchQuery.data.items.map((r) => (
                  <li key={r.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setPicked({ id: r.id, name: r.official_name });
                        setQuery("");
                      }}
                      className="block w-full px-3 py-1.5 text-left text-sm hover:bg-muted"
                    >
                      {r.official_name}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Title</span>
        <input
          className={field}
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Detail (optional)</span>
        <input
          className={field}
          value={detail}
          onChange={(e) => setDetail(e.target.value)}
        />
      </label>
      <div className="sm:col-span-2">
        {error instanceof ApiError && (
          <p className="mb-2 text-sm text-destructive">{error.message}</p>
        )}
        <button
          type="submit"
          disabled={!picked || !title.trim() || pending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-secondary disabled:opacity-60"
        >
          {pending ? "Saving…" : "Create opportunity"}
        </button>
      </div>
    </form>
  );
}

function OpportunityPanel({
  opp,
  canEdit,
  onChanged,
}: {
  opp: OpportunityDetail;
  canEdit: boolean;
  onChanged: () => void;
}) {
  const [outcomeNote, setOutcomeNote] = useState("");
  const [pendingStage, setPendingStage] = useState<OpportunityStage | "">("");
  const [activityType, setActivityType] = useState<OpportunityActivityType>("note");
  const [activityNote, setActivityNote] = useState("");

  const decide = useMutation({
    mutationFn: (nextStatus: "confirmed" | "dismissed") =>
      api(`/opportunities/${opp.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      }),
    onSuccess: onChanged,
  });

  const changeStage = useMutation({
    mutationFn: (vars: { stage: OpportunityStage; outcome_note?: string | null }) =>
      api(`/opportunities/${opp.id}/stage`, { method: "POST", body: JSON.stringify(vars) }),
    onSuccess: () => {
      setPendingStage("");
      setOutcomeNote("");
      onChanged();
    },
  });

  const addActivity = useMutation({
    mutationFn: () =>
      api(`/opportunities/${opp.id}/activities`, {
        method: "POST",
        body: JSON.stringify({ type: activityType, note: activityNote }),
      }),
    onSuccess: () => {
      setActivityNote("");
      onChanged();
    },
  });

  const field =
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  const submitStage = (stage: OpportunityStage) => {
    if (stage === "won" || stage === "lost") {
      setPendingStage(stage);
      return;
    }
    changeStage.mutate({ stage });
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-card shadow-sm p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="font-heading text-sm font-semibold text-foreground">{opp.title}</span>
          <Badge tone={OPPORTUNITY_STATUS_TONE[opp.status]}>{opp.status}</Badge>
        </div>
        {opp.detail && <p className="text-sm text-muted-foreground">{opp.detail}</p>}
        <p className="mt-2 text-xs text-muted-foreground">Source: {opp.source}</p>
        <Link
          to={`/relationships/${opp.relationship_id}`}
          className="mt-2 inline-block text-sm text-secondary hover:underline"
        >
          {opp.official_name} · open relationship →
        </Link>
      </div>

      {opp.status === "suggested" && canEdit && (
        <div className="rounded-lg border border-border bg-card shadow-sm p-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Detected — confirm or dismiss
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => decide.mutate("confirmed")}
              disabled={decide.isPending}
              className="rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-accent-foreground hover:opacity-90 disabled:opacity-60"
            >
              Confirm
            </button>
            <button
              onClick={() => decide.mutate("dismissed")}
              disabled={decide.isPending}
              className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted disabled:opacity-60"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {opp.status === "confirmed" && (
        <div className="rounded-lg border border-border bg-card shadow-sm p-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Pipeline stage
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <select
              className={field}
              value={opp.stage}
              disabled={!canEdit || changeStage.isPending}
              onChange={(e) => submitStage(e.target.value as OpportunityStage)}
            >
              {OPPORTUNITY_STAGES.map((s) => (
                <option key={s} value={s}>
                  {OPPORTUNITY_STAGE_LABELS[s]}
                </option>
              ))}
            </select>
          </div>
          {pendingStage && (
            <div className="mt-3 space-y-2 border-t border-border pt-3">
              <label className="text-xs text-muted-foreground">
                Outcome note (optional)
                <textarea
                  className={`${field} mt-1`}
                  rows={2}
                  value={outcomeNote}
                  onChange={(e) => setOutcomeNote(e.target.value)}
                />
              </label>
              <div className="flex gap-2">
                <button
                  onClick={() =>
                    changeStage.mutate({ stage: pendingStage, outcome_note: outcomeNote || null })
                  }
                  disabled={changeStage.isPending}
                  className="rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground hover:bg-secondary disabled:opacity-60"
                >
                  Confirm {OPPORTUNITY_STAGE_LABELS[pendingStage]}
                </button>
                <button
                  onClick={() => setPendingStage("")}
                  className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
          {opp.closed_at && (
            <p className="mt-2 text-xs text-muted-foreground">
              Closed {new Date(opp.closed_at).toLocaleDateString()}
              {opp.outcome_note ? ` · ${opp.outcome_note}` : ""}
            </p>
          )}
        </div>
      )}

      <div className="rounded-lg border border-border bg-card shadow-sm p-4">
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Activity
        </p>
        {opp.activities.length === 0 && (
          <p className="text-sm text-muted-foreground">Nothing logged yet.</p>
        )}
        <ul className="space-y-2">
          {opp.activities.map((a) => (
            <li
              key={a.id}
              className={`text-sm ${a.type === "stage_change" ? "italic text-muted-foreground" : "text-foreground"}`}
            >
              <span className="text-xs text-muted-foreground">
                {new Date(a.occurred_at).toLocaleDateString()} ·{" "}
              </span>
              {a.note}
            </li>
          ))}
        </ul>

        {opp.status === "confirmed" && canEdit && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (activityNote.trim()) addActivity.mutate();
            }}
            className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3"
          >
            <select
              className={field}
              value={activityType}
              onChange={(e) => setActivityType(e.target.value as OpportunityActivityType)}
            >
              {OPPORTUNITY_ACTIVITY_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <input
              className={`${field} flex-1 min-w-[10rem]`}
              placeholder="What happened?"
              value={activityNote}
              onChange={(e) => setActivityNote(e.target.value)}
            />
            <button
              type="submit"
              disabled={!activityNote.trim() || addActivity.isPending}
              className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted disabled:opacity-60"
            >
              Log
            </button>
          </form>
        )}
        {(decide.error instanceof ApiError ||
          changeStage.error instanceof ApiError ||
          addActivity.error instanceof ApiError) && (
          <p className="mt-2 text-xs text-destructive">
            {(decide.error as ApiError)?.message ??
              (changeStage.error as ApiError)?.message ??
              (addActivity.error as ApiError)?.message}
          </p>
        )}
      </div>
    </div>
  );
}
