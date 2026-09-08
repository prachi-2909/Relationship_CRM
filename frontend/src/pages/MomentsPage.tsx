import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Badge } from "../components/Badge";
import { useAuth } from "../auth/AuthProvider";
import { api, ApiError } from "../lib/api";
import {
  MOMENT_STATUS_TONE,
  MOMENT_TYPE_LABELS,
  type MomentDetail,
  type MomentListResponse,
  type MomentStatus,
  type MomentType,
} from "../types";

const EVIDENCE_LABELS: Record<string, string> = {
  trigger: "Trigger",
  source: "Source",
  days_since_last_interaction: "Days since last contact",
  last_sentiment: "Last sentiment",
  relationship_band: "Relationship band",
  relationship_status: "Relationship status",
  importance: "Importance",
  score: "Score",
  years: "Years of service",
  outcome: "Outcome",
  dismiss_reason: "Dismiss reason",
};

export function MomentsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const canEdit = isAdmin || user?.role === "relationship_manager";
  const queryClient = useQueryClient();

  const [status, setStatus] = useState<MomentStatus | "">("");
  const [type, setType] = useState<MomentType | "">("");
  const [selected, setSelected] = useState<number | null>(null);

  const params = new URLSearchParams({ limit: "100" });
  if (status) params.set("status", status);
  if (type) params.set("type", type);

  const listQuery = useQuery({
    queryKey: ["moments", status, type],
    queryFn: () => api<MomentListResponse>(`/moments?${params}`),
  });
  const detailQuery = useQuery({
    queryKey: ["moment", selected],
    queryFn: () => api<MomentDetail>(`/moments/${selected}`),
    enabled: selected !== null,
  });

  const detect = useMutation({
    mutationFn: () => api<{ created: number }>("/moments/detect", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["moments"] }),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["moments"] });
    queryClient.invalidateQueries({ queryKey: ["moment", selected] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const control =
    "rounded-md border border-input bg-background px-3 py-1.5 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-xl font-bold text-foreground">
          Engagement Moments
        </h1>
        {isAdmin && (
          <button
            onClick={() => detect.mutate()}
            disabled={detect.isPending}
            className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted disabled:opacity-60"
          >
            {detect.isPending ? "Detecting…" : "Run detection"}
          </button>
        )}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        Detected relationship events. Every draft is sent by a person — there is
        no automated send.
        {detect.error instanceof ApiError && (
          <span className="ml-2 text-destructive">{detect.error.message}</span>
        )}
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        <select
          className={control}
          value={status}
          onChange={(e) => setStatus(e.target.value as MomentStatus | "")}
        >
          <option value="">Any status</option>
          {(
            ["detected", "draft_ready", "approved", "sent_manually", "dismissed"] as const
          ).map((s) => (
            <option key={s} value={s}>
              {s.replace("_", " ")}
            </option>
          ))}
        </select>
        <select
          className={control}
          value={type}
          onChange={(e) => setType(e.target.value as MomentType | "")}
        >
          <option value="">Any type</option>
          {(Object.keys(MOMENT_TYPE_LABELS) as MomentType[]).map((t) => (
            <option key={t} value={t}>
              {MOMENT_TYPE_LABELS[t]}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4 grid gap-6 lg:grid-cols-[1fr_1.4fr]">
        <div className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
          {listQuery.isPending && (
            <div className="p-4 text-sm text-muted-foreground">Loading…</div>
          )}
          {listQuery.data && listQuery.data.items.length === 0 && (
            <div className="p-6 text-sm text-muted-foreground">No moments.</div>
          )}
          {listQuery.data?.items.map((m) => (
            <button
              key={m.id}
              onClick={() => setSelected(m.id)}
              className={`block w-full border-b border-border px-4 py-3 text-left text-sm last:border-b-0 hover:bg-muted ${
                selected === m.id ? "bg-primary/10" : ""
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-foreground">
                  {MOMENT_TYPE_LABELS[m.type]}
                </span>
                <Badge tone={MOMENT_STATUS_TONE[m.status]}>
                  {m.status.replace("_", " ")}
                </Badge>
              </div>
              <div className="mt-1 text-muted-foreground">{m.official_name}</div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                {m.event_date && <span>{new Date(m.event_date).toLocaleDateString()}</span>}
                {m.suppressed_reason && (
                  <Badge tone="warn">suppressed · {m.suppressed_reason}</Badge>
                )}
              </div>
            </button>
          ))}
        </div>

        <div>
          {!detailQuery.data && (
            <p className="text-sm text-muted-foreground">
              Select a moment to review it.
            </p>
          )}
          {detailQuery.data && (
            <MomentPanel
              moment={detailQuery.data}
              canEdit={canEdit}
              onChanged={invalidate}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function MomentPanel({
  moment,
  canEdit,
  onChanged,
}: {
  moment: MomentDetail;
  canEdit: boolean;
  onChanged: () => void;
}) {
  const [draft, setDraft] = useState(moment.draft_text ?? "");
  const [outcome, setOutcome] = useState("");
  const post = (path: string, body?: unknown) =>
    api(`/moments/${moment.id}${path}`, {
      method: "POST",
      ...(body ? { body: JSON.stringify(body) } : {}),
    });

  const doDraft = useMutation({ mutationFn: () => post("/draft"), onSuccess: onChanged });
  const doDraftForce = useMutation({
    mutationFn: () => post("/draft?force=true"),
    onSuccess: onChanged,
  });
  const saveDraft = useMutation({
    mutationFn: () =>
      api(`/moments/${moment.id}`, {
        method: "PATCH",
        body: JSON.stringify({ draft_text: draft }),
      }),
    onSuccess: onChanged,
  });
  const doApprove = useMutation({
    mutationFn: () => post("/approve"),
    onSuccess: onChanged,
  });
  const doDismiss = useMutation({
    mutationFn: () => post("/dismiss", { reason: "not appropriate" }),
    onSuccess: onChanged,
  });
  const doSent = useMutation({
    mutationFn: () => post("/sent", { outcome: outcome || null }),
    onSuccess: onChanged,
  });

  const field =
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-card shadow-sm p-4">
        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Why now?
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
          {Object.entries(moment.evidence).map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="text-muted-foreground">
                {EVIDENCE_LABELS[key] ?? key}
              </dt>
              <dd className="text-right font-medium text-foreground">
                {value === null ? "—" : String(value)}
              </dd>
            </div>
          ))}
        </dl>
        {moment.suppressed_reason && (
          <p className="mt-3 rounded bg-saffron/15 px-2 py-1 text-xs text-[hsl(38_80%_32%)]">
            Suppressed by the fatigue check: {moment.suppressed_reason}
          </p>
        )}
      </div>

      <div className="rounded-lg border border-border bg-card shadow-sm p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Draft
          </span>
          <Badge tone="neutral">{moment.status.replace("_", " ")}</Badge>
        </div>

        {moment.status === "detected" && (
          <div className="flex gap-2">
            {canEdit && (
              <button
                onClick={() => doDraft.mutate()}
                className="rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground hover:bg-secondary"
              >
                Generate draft
              </button>
            )}
            {canEdit && moment.suppressed_reason && (
              <button
                onClick={() => doDraftForce.mutate()}
                className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted"
              >
                Draft anyway
              </button>
            )}
          </div>
        )}

        {moment.status !== "detected" && (
          <>
            <textarea
              className={`${field} font-sans`}
              rows={7}
              value={draft}
              disabled={!canEdit || moment.status === "sent_manually" || moment.status === "dismissed"}
              onChange={(e) => setDraft(e.target.value)}
            />
            {canEdit && moment.status === "draft_ready" && (
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  onClick={() => saveDraft.mutate()}
                  className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted"
                >
                  Save edits
                </button>
                <button
                  onClick={() => doApprove.mutate()}
                  className="rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-accent-foreground hover:opacity-90"
                >
                  Approve
                </button>
                <button
                  onClick={() => doDismiss.mutate()}
                  className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted"
                >
                  Dismiss
                </button>
              </div>
            )}
            {canEdit && moment.status === "approved" && (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className="text-xs text-muted-foreground">
                  Approved. Send it by hand from the mailbox, then record it:
                </span>
                <input
                  className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                  placeholder="outcome (optional)"
                  value={outcome}
                  onChange={(e) => setOutcome(e.target.value)}
                />
                <button
                  onClick={() => doSent.mutate()}
                  className="rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground hover:bg-secondary"
                >
                  Mark sent
                </button>
              </div>
            )}
          </>
        )}
      </div>

      <Link
        to={`/relationships/${moment.relationship_id}`}
        className="inline-block text-sm text-secondary hover:underline"
      >
        Open relationship →
      </Link>
    </div>
  );
}
