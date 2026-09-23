import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { Badge } from "../components/Badge";
import { Card, EmptyState, PageHeader, Spinner } from "../components/ui";
import { api, ApiError } from "../lib/api";
import {
  CALL_IDENTITY_STATUS_TONE,
  CALL_PROCESSING_STATUS_TONE,
  type CallSessionDetail,
  type CallSessionListResponse,
  type DcOption,
  type OfficialListResponse,
} from "../types";

export function CallIntelligencePage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [view, setView] = useState<"pending" | "history">("pending");
  const [selected, setSelected] = useState<number | null>(null);
  const [dcFilter, setDcFilter] = useState<string>("");

  const dcOptionsQuery = useQuery({
    queryKey: ["calls", "dc-options"],
    queryFn: () => api<DcOption[]>("/calls/dc-options"),
    enabled: user?.role !== "dc",
  });
  const listQuery = useQuery({
    queryKey: ["calls", view, dcFilter],
    queryFn: () =>
      api<CallSessionListResponse>(
        `/calls/${view}?limit=100${dcFilter ? `&dc_user_id=${dcFilter}` : ""}`,
      ),
  });
  const detailQuery = useQuery({
    queryKey: ["calls", "detail", selected],
    queryFn: () => api<CallSessionDetail>(`/calls/${selected}`),
    enabled: selected !== null,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["calls"] });
  };

  return (
    <div>
      <PageHeader
        title="Call Intelligence"
        description="Calls placed or received through Knowlarity, converted into a reviewable brief — confirm before anything is logged to the CRM."
        actions={<NewCallControl onStarted={invalidate} />}
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-lg border border-border bg-card p-0.5 text-xs shadow-sm">
          {(["pending", "history"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`rounded-md px-3 py-1.5 font-medium capitalize transition-colors ${
                view === v ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-muted"
              }`}
            >
              {v}
            </button>
          ))}
        </div>
        {user?.role !== "dc" && dcOptionsQuery.data && dcOptionsQuery.data.length > 0 && (
          <select
            className="rounded-lg border border-input bg-surface px-2.5 py-1.5 text-xs outline-none focus:border-ring focus:ring-2 focus:ring-ring/25"
            value={dcFilter}
            onChange={(e) => setDcFilter(e.target.value)}
          >
            <option value="">All DCs</option>
            {dcOptionsQuery.data.map((dc) => (
              <option key={dc.id} value={dc.id}>
                {dc.name}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="mt-4 grid gap-6 lg:grid-cols-[1fr_1.4fr]">
        <div className="space-y-2.5">
          {listQuery.isPending && <Spinner />}
          {listQuery.data && listQuery.data.items.length === 0 && (
            <Card>
              <EmptyState
                title={view === "pending" ? "No pending calls" : "No call history yet"}
                hint="Use 'Call an official' above, or wait for an incoming call routed through Knowlarity."
              />
            </Card>
          )}
          {listQuery.data?.items.map((c) => (
            <button
              key={c.id}
              onClick={() => setSelected(c.id)}
              className={`flex w-full items-start justify-between gap-3 rounded-xl border border-border bg-card p-3.5 text-left text-sm shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md ${
                selected === c.id ? "ring-2 ring-ring/30" : ""
              }`}
            >
              <span className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-2">
                  <span className="font-medium text-foreground">
                    {c.official_name ?? "Unregistered caller"}
                  </span>
                  <Badge tone={CALL_PROCESSING_STATUS_TONE[c.processing_status]}>
                    {c.processing_status.replace(/_/g, " ")}
                  </Badge>
                </span>
                <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span className="capitalize">{c.direction}</span>
                  <span>{c.phone_ref}</span>
                  {user?.role !== "dc" && <span>by {c.dc_user_name}</span>}
                  <Badge tone={CALL_IDENTITY_STATUS_TONE[c.identity_status]}>
                    {c.identity_status.replace(/_/g, " ")}
                  </Badge>
                </span>
                <span className="mt-1 block text-xs text-muted-foreground/80">
                  {new Date(c.started_at).toLocaleString()}
                </span>
              </span>
            </button>
          ))}
        </div>

        <div>
          {!detailQuery.data && (
            <div className="flex h-full min-h-[12rem] items-center justify-center rounded-xl border border-dashed border-border text-sm text-muted-foreground">
              Select a call to review it.
            </div>
          )}
          {detailQuery.data && (
            <CallReviewPanel key={detailQuery.data.id} call={detailQuery.data} onChanged={invalidate} />
          )}
        </div>
      </div>
    </div>
  );
}

function NewCallControl({ onStarted }: { onStarted: () => void }) {
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<{ id: number; name: string } | null>(null);

  const searchQuery = useQuery({
    queryKey: ["officials", "call-picker", query],
    queryFn: () => api<OfficialListResponse>(`/officials?limit=6&q=${encodeURIComponent(query)}`),
    enabled: query.trim().length >= 2 && !picked,
  });

  const trigger = useMutation({
    mutationFn: (officialId: number) =>
      api("/calls/outgoing", { method: "POST", body: JSON.stringify({ official_id: officialId }) }),
    onSuccess: () => {
      setPicked(null);
      setQuery("");
      onStarted();
    },
  });

  return (
    <div className="flex items-center gap-2">
      <div className="relative">
        {picked ? (
          <span className="flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm">
            {picked.name}
            <button onClick={() => setPicked(null)} className="text-xs text-muted-foreground hover:underline">
              change
            </button>
          </span>
        ) : (
          <input
            className="w-56 rounded-lg border border-input bg-surface px-3 py-1.5 text-sm outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/25"
            placeholder="Search an official to call…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        )}
        {!picked && searchQuery.data && searchQuery.data.items.length > 0 && (
          <ul className="absolute z-10 mt-1 w-56 overflow-hidden rounded-lg border border-border bg-card shadow-md">
            {searchQuery.data.items.map((o) => (
              <li key={o.id}>
                <button
                  onClick={() => {
                    setPicked({ id: o.id, name: o.name });
                    setQuery("");
                  }}
                  className="block w-full px-2.5 py-1.5 text-left text-sm hover:bg-muted"
                >
                  {o.name}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <button
        disabled={!picked || trigger.isPending}
        onClick={() => picked && trigger.mutate(picked.id)}
        className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-saffron to-[hsl(36_78%_46%)] px-3.5 py-1.5 text-sm font-semibold text-secondary-foreground shadow-glow-gold transition-transform hover:-translate-y-0.5 disabled:pointer-events-none disabled:opacity-50 disabled:shadow-none"
      >
        {trigger.isPending ? "Starting…" : "Call"}
      </button>
      {trigger.error instanceof ApiError && (
        <span className="text-xs text-destructive">{trigger.error.message}</span>
      )}
    </div>
  );
}

const BRIEF_FIELD_LABELS: Record<string, string> = {
  summary: "Summary",
  key_points: "Key points",
  decisions: "Decisions",
  commitments: "Commitments",
  action_items: "Action items",
  opportunities: "Opportunities",
  relationship_signals: "Relationship signals",
  suggested_next_interaction: "Suggested next interaction",
};

function CallReviewPanel({ call, onChanged }: { call: CallSessionDetail; onChanged: () => void }) {
  const { user } = useAuth();
  const [manualText, setManualText] = useState("");
  const [brief, setBrief] = useState<Record<string, unknown>>((call.brief as Record<string, unknown>) ?? {});
  const [linkOfficialId, setLinkOfficialId] = useState("");
  const [newOfficialName, setNewOfficialName] = useState("");

  const manualTextMutation = useMutation({
    mutationFn: () =>
      api(`/calls/${call.id}/manual-text`, { method: "POST", body: JSON.stringify({ text: manualText }) }),
    onSuccess: onChanged,
  });
  const linkMutation = useMutation({
    mutationFn: (officialId: number) =>
      api(`/calls/${call.id}/identity/link`, {
        method: "POST",
        body: JSON.stringify({ official_id: officialId, update_phone: false }),
      }),
    onSuccess: onChanged,
  });
  const createMutation = useMutation({
    mutationFn: () =>
      api(`/calls/${call.id}/identity/create`, {
        method: "POST",
        body: JSON.stringify({ name: newOfficialName, phone: call.phone_ref }),
      }),
    onSuccess: onChanged,
  });
  const dismissMutation = useMutation({
    mutationFn: () => api(`/calls/${call.id}/identity/dismiss`, { method: "POST" }),
    onSuccess: onChanged,
  });
  const confirmMutation = useMutation({
    mutationFn: () =>
      api(`/calls/${call.id}/confirm`, {
        method: "POST",
        body: JSON.stringify({ brief, identity_action: "link" }),
      }),
    onSuccess: onChanged,
  });
  const remindMutation = useMutation({
    mutationFn: () => api(`/calls/${call.id}/remind-later`, { method: "POST", body: JSON.stringify({}) }),
    onSuccess: onChanged,
  });

  const needsIdentity = call.relationship_id === null;
  const needsSource = !call.transcript_text;
  const canConfirm = !needsIdentity && !needsSource && call.processing_status !== "crm_logged";
  const anyError = [manualTextMutation, linkMutation, createMutation, dismissMutation, confirmMutation, remindMutation]
    .map((m) => m.error)
    .find((e) => e instanceof ApiError) as ApiError | undefined;

  return (
    <div className="fade-in-up space-y-4">
      <Card className="p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="font-heading text-sm font-semibold text-foreground">
            {call.official_name ?? "Unregistered caller"} — {call.phone_ref}
          </span>
          {call.official_id && (
            <Link to={`/relationships/${call.relationship_id}`} className="text-xs text-secondary hover:underline">
              Open relationship →
            </Link>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {call.direction} · {call.duration_seconds ? `${call.duration_seconds}s` : "duration unknown"} ·{" "}
          {new Date(call.started_at).toLocaleString()}
          {user?.role !== "dc" && <> · by {call.dc_user_name}</>}
        </p>
      </Card>

      {needsSource && (
        <Card className="p-4">
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Recording not available yet — log this call another way
          </div>
          <textarea
            className="w-full rounded-md border border-input bg-surface px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/25"
            rows={4}
            placeholder="Type what was discussed…"
            value={manualText}
            onChange={(e) => setManualText(e.target.value)}
          />
          <button
            onClick={() => manualTextMutation.mutate()}
            disabled={!manualText.trim() || manualTextMutation.isPending}
            className="mt-2 rounded-lg border border-border px-3 py-1.5 text-sm text-foreground hover:bg-muted disabled:opacity-50"
          >
            {manualTextMutation.isPending ? "Saving…" : "Save text"}
          </button>
        </Card>
      )}

      {!needsSource && (
        <Card className="p-4">
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Transcript ({call.transcript_source})
          </div>
          <p className="whitespace-pre-wrap text-sm text-foreground">{call.transcript_text}</p>
        </Card>
      )}

      {!needsSource && (
        <Card className="p-4">
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            AI brief — review and edit before confirming
          </div>
          <div className="space-y-2.5 text-sm">
            {Object.entries(BRIEF_FIELD_LABELS).map(([key, label]) => (
              <div key={key}>
                <label className="mb-0.5 block text-xs text-muted-foreground">{label}</label>
                <input
                  className="w-full rounded-md border border-input bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/25"
                  value={
                    Array.isArray(brief[key]) ? (brief[key] as string[]).join(", ") : String(brief[key] ?? "")
                  }
                  onChange={(e) =>
                    setBrief((b) => ({
                      ...b,
                      [key]: Array.isArray(call.brief?.[key as keyof typeof call.brief])
                        ? e.target.value.split(",").map((s) => s.trim()).filter(Boolean)
                        : e.target.value,
                    }))
                  }
                />
              </div>
            ))}
          </div>
        </Card>
      )}

      {needsIdentity && (
        <Card className="p-4">
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {call.official_id !== null
              ? `No relationship on file for ${call.official_name ?? "this official"} yet — resolve before confirming`
              : "Who was this? Unregistered caller — resolve before confirming"}
          </div>
          <div className="space-y-2">
            {call.official_id !== null && (
              <button
                onClick={() => linkMutation.mutate(call.official_id!)}
                disabled={linkMutation.isPending}
                className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
              >
                {linkMutation.isPending
                  ? "Creating relationship…"
                  : `Create relationship with ${call.official_name ?? "this official"}`}
              </button>
            )}
            <div className="flex gap-2">
              <input
                className="flex-1 rounded-md border border-input bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/25"
                placeholder="Existing official id"
                value={linkOfficialId}
                onChange={(e) => setLinkOfficialId(e.target.value)}
              />
              <button
                onClick={() => linkMutation.mutate(Number(linkOfficialId))}
                disabled={!linkOfficialId || linkMutation.isPending}
                className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
              >
                Link existing
              </button>
            </div>
            <div className="flex gap-2">
              <input
                className="flex-1 rounded-md border border-input bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/25"
                placeholder="New official's name"
                value={newOfficialName}
                onChange={(e) => setNewOfficialName(e.target.value)}
              />
              <button
                onClick={() => createMutation.mutate()}
                disabled={!newOfficialName.trim() || createMutation.isPending}
                className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
              >
                Create new
              </button>
            </div>
            <button
              onClick={() => dismissMutation.mutate()}
              disabled={dismissMutation.isPending}
              className="text-xs text-muted-foreground hover:underline"
            >
              Keep unidentified
            </button>
          </div>
        </Card>
      )}

      <Card className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Decision</span>
          <Badge tone={CALL_PROCESSING_STATUS_TONE[call.processing_status]}>
            {call.processing_status.replace(/_/g, " ")}
          </Badge>
        </div>
        {call.processing_status !== "crm_logged" && (
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => confirmMutation.mutate()}
              disabled={!canConfirm || confirmMutation.isPending}
              className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-saffron to-[hsl(36_78%_46%)] px-4 py-1.5 text-sm font-semibold text-secondary-foreground shadow-glow-gold transition-transform hover:-translate-y-0.5 disabled:pointer-events-none disabled:opacity-60 disabled:shadow-none"
            >
              {confirmMutation.isPending ? "Logging…" : "Confirm & Log"}
            </button>
            <button
              onClick={() => remindMutation.mutate()}
              disabled={remindMutation.isPending}
              className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted-foreground hover:bg-muted disabled:opacity-60"
            >
              Remind me later
            </button>
          </div>
        )}
        {anyError && <p className="mt-2 text-xs text-destructive">{anyError.message}</p>}
      </Card>
    </div>
  );
}
