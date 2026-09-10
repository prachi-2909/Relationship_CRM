import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { Badge } from "../components/Badge";
import { ComponentBars, ScoreDial } from "../components/ScoreDial";
import { Button, inputClass } from "../components/ui";
import { AddTaskForm } from "./TasksPage";
import { useAuth } from "../auth/AuthProvider";
import { api, ApiError } from "../lib/api";
import {
  DIRECTIONS,
  INTERACTION_TYPES,
  isOverdue,
  RELATIONSHIP_STATUSES,
  SENTIMENT_TONE,
  type Direction,
  type InteractionDetail,
  type InteractionListResponse,
  type InteractionType,
  type RelationshipBrief,
  type RelationshipDetail,
  type ScoreHistoryEntry,
  type TaskListResponse,
  type TaskStatus,
} from "../types";

export function RelationshipDetailPage() {
  const { id } = useParams<{ id: string }>();
  const relId = Number(id);
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canEdit = user?.role === "admin" || user?.role === "relationship_manager";

  const relQuery = useQuery({
    queryKey: ["relationship", relId],
    queryFn: () => api<RelationshipDetail>(`/relationships/${relId}`),
  });
  const historyQuery = useQuery({
    queryKey: ["relationship", relId, "history"],
    queryFn: () => api<ScoreHistoryEntry[]>(`/relationships/${relId}/score-history`),
  });
  const interactionsQuery = useQuery({
    queryKey: ["interactions", relId],
    queryFn: () =>
      api<InteractionListResponse>(`/interactions?relationship_id=${relId}&limit=50`),
  });
  const tasksQuery = useQuery({
    queryKey: ["tasks", "rel", relId],
    queryFn: () => api<TaskListResponse>(`/tasks?relationship_id=${relId}&limit=100`),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["relationship", relId] });
    queryClient.invalidateQueries({ queryKey: ["interactions", relId] });
    queryClient.invalidateQueries({ queryKey: ["tasks"] });
    queryClient.invalidateQueries({ queryKey: ["relationships"] });
  };

  const toggleTask = useMutation({
    mutationFn: (vars: { id: number; status: TaskStatus }) =>
      api(`/tasks/${vars.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: vars.status }),
      }),
    onSuccess: invalidate,
  });

  const patchRel = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<RelationshipDetail>(`/relationships/${relId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: invalidate,
  });
  const claim = useMutation({
    mutationFn: () =>
      api<RelationshipDetail>(`/relationships/${relId}/claim`, { method: "POST" }),
    onSuccess: invalidate,
  });

  if (relQuery.isPending) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (relQuery.error) {
    return (
      <p className="text-sm text-destructive">
        {relQuery.error instanceof ApiError
          ? relQuery.error.message
          : "Could not load this relationship."}
      </p>
    );
  }

  const rel = relQuery.data!;
  const select =
    "rounded-md border border-input bg-background px-2 py-1 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <div>
      <Link to="/relationships" className="text-sm text-muted-foreground hover:underline">
        ← All relationships
      </Link>

      <div className="mt-2 flex flex-wrap items-center gap-3">
        <h1 className="font-heading text-xl font-bold text-foreground">
          <Link
            to={`/officials/${rel.official.id}`}
            className="hover:underline"
          >
            {rel.official.name}
          </Link>
        </h1>
        <Badge tone="neutral">{rel.official.level ?? "level —"}</Badge>
      </div>

      <BriefCard relId={relId} />

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_1.6fr]">
        <div className="space-y-4">
          <div className="rounded-lg border border-border bg-card shadow-sm p-4">
            <ScoreDial score={rel.score} />
            <div className="mt-4">
              <ComponentBars components={rel.score_components} />
            </div>
          </div>

          <div className="rounded-lg border border-border bg-card shadow-sm p-4 text-sm">
            <div className="mb-3 grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2">
              <span className="text-muted-foreground">Status</span>
              {canEdit ? (
                <select
                  className={select}
                  value={rel.status}
                  onChange={(e) => patchRel.mutate({ status: e.target.value })}
                >
                  {RELATIONSHIP_STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s.replace("_", " ")}
                    </option>
                  ))}
                </select>
              ) : (
                <span className="capitalize">{rel.status.replace("_", " ")}</span>
              )}

              <span className="text-muted-foreground">Importance</span>
              <span
                className="capitalize"
                title="Auto-computed from the official's level and the sentiment of recent interactions"
              >
                {rel.importance}
                <span className="ml-1.5 text-xs text-muted-foreground">· auto</span>
              </span>

              <span className="text-muted-foreground">Owner</span>
              <span>
                {rel.owner_id ? (
                  `user #${rel.owner_id}`
                ) : (
                  <span className="flex items-center gap-2">
                    unowned
                    {canEdit && (
                      <button
                        onClick={() => claim.mutate()}
                        className="rounded bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground hover:bg-secondary"
                      >
                        Claim
                      </button>
                    )}
                  </span>
                )}
              </span>

              <span className="text-muted-foreground">Last contact</span>
              <span>
                {rel.last_interaction_at
                  ? new Date(rel.last_interaction_at).toLocaleDateString()
                  : "never"}
              </span>
            </div>
          </div>

          <div className="rounded-lg border border-border bg-card shadow-sm p-4">
            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Score history
            </div>
            <ol className="space-y-1.5 text-xs">
              {historyQuery.data?.slice(0, 12).map((h, i) => (
                <li key={i} className="flex justify-between">
                  <span className="text-muted-foreground">
                    {new Date(h.computed_at).toLocaleDateString()} · {h.reason}
                  </span>
                  <span className="font-semibold tabular-nums">{h.score}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>

        <div className="space-y-6">
          <div>
            <h2 className="mb-3 font-heading text-base font-semibold text-foreground">
              Follow-ups
            </h2>
            {canEdit && (
              <div className="rounded-lg border border-border bg-card shadow-sm p-3">
                <AddTaskForm relationshipId={relId} onDone={invalidate} />
              </div>
            )}
            <div className="mt-3 space-y-1.5">
              {tasksQuery.data?.items.length === 0 && (
                <p className="text-sm text-muted-foreground">No follow-ups.</p>
              )}
              {tasksQuery.data?.items.map((t) => (
                <div
                  key={t.id}
                  className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm"
                >
                  {canEdit && (
                    <input
                      type="checkbox"
                      checked={t.status === "done"}
                      onChange={(e) =>
                        toggleTask.mutate({
                          id: t.id,
                          status: e.target.checked ? "done" : "open",
                        })
                      }
                    />
                  )}
                  <span
                    className={
                      t.status === "done"
                        ? "flex-1 text-muted-foreground line-through"
                        : "flex-1 text-foreground"
                    }
                  >
                    {t.title}
                  </span>
                  {t.due_at && (
                    <span className="text-xs text-muted-foreground">
                      {new Date(t.due_at).toLocaleDateString()}
                    </span>
                  )}
                  {isOverdue(t) && <Badge tone="danger">overdue</Badge>}
                  {t.escalated_at && <Badge tone="warn">escalated</Badge>}
                </div>
              ))}
            </div>
          </div>

          <div>
            <h2 className="mb-3 font-heading text-base font-semibold text-foreground">
              Interactions
            </h2>

            {canEdit && (
              <LogInteractionForm relationshipId={relId} onDone={invalidate} />
            )}

            <div className="mt-4 space-y-3">
              {interactionsQuery.data?.items.length === 0 && (
                <p className="text-sm text-muted-foreground">Nothing logged yet.</p>
              )}
              {interactionsQuery.data?.items.map((it) => (
                <InteractionCard
                  key={it.id}
                  interactionId={it.id}
                  relationshipId={relId}
                  summary={it}
                  canEdit={canEdit}
                  onTaskAdded={invalidate}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function BriefCard({ relId }: { relId: number }) {
  const [open, setOpen] = useState(false);
  const briefQuery = useQuery({
    queryKey: ["relationship", relId, "brief"],
    queryFn: () => api<RelationshipBrief>(`/relationships/${relId}/brief`),
    enabled: open,
    staleTime: 60_000,
  });

  const section =
    "text-[11px] font-medium uppercase tracking-wide text-muted-foreground";

  return (
    <div className="mt-5 rounded-lg border border-border bg-card shadow-sm">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2">
          <span className="font-heading text-sm font-semibold text-foreground">
            Relationship brief
          </span>
          <span className="text-xs text-muted-foreground">
            read-only · synthesised from what's on record
          </span>
        </span>
        <span className="text-xs text-muted-foreground">{open ? "Hide" : "Show"}</span>
      </button>

      {open && (
        <div className="border-t border-border px-4 py-4 text-sm">
          {briefQuery.isPending && (
            <p className="text-muted-foreground">Composing…</p>
          )}
          {briefQuery.error && (
            <p className="text-destructive">
              {briefQuery.error instanceof ApiError
                ? briefQuery.error.message
                : "Could not build the brief."}
            </p>
          )}
          {briefQuery.data && (
            <BriefBody brief={briefQuery.data} section={section} />
          )}
        </div>
      )}
    </div>
  );
}

function BriefBody({
  brief,
  section,
}: {
  brief: RelationshipBrief;
  section: string;
}) {
  const rec = brief.reconnect_opportunity;
  const sh = brief.stakeholders;
  const connections = sh?.connections ?? [];
  const mentioned = sh?.mentioned ?? [];
  return (
    <div className="space-y-4">
      <p className="leading-relaxed text-foreground">{brief.narrative}</p>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <div className={section}>What's important</div>
          <p className="mt-1 text-muted-foreground">{brief.what_is_important}</p>
        </div>

        <div>
          <div className={section}>What changed</div>
          <ul className="mt-1 space-y-0.5 text-muted-foreground">
            {brief.what_changed.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>

        <div>
          <div className={section}>Opportunity to reconnect</div>
          <p className="mt-1">
            <Badge tone={rec.yes ? "good" : "neutral"}>
              {rec.yes ? "yes" : "not now"}
            </Badge>{" "}
            <span className="text-muted-foreground">{rec.reason}</span>
          </p>
        </div>

        <div>
          <div className={section}>Next interaction</div>
          <p className="mt-1 text-muted-foreground">{brief.next_interaction}</p>
        </div>
      </div>

      <div>
        <div className={section}>Key stakeholders</div>
        {connections.length > 0 ? (
          <ul className="mt-1 space-y-0.5 text-muted-foreground">
            {connections.map((c, i) => (
              <li key={i}>
                <Link
                  to={`/officials/${c.official_id}`}
                  className="font-medium text-foreground hover:underline"
                >
                  {c.name}
                </Link>
                <span className="text-xs"> — {c.label.replace(c.name, "").trim()}</span>
                {c.note && <span className="text-xs"> · {c.note}</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-muted-foreground/70">
            No connections mapped yet.
          </p>
        )}
        {mentioned.length > 0 && (
          <p className="mt-1 text-xs text-muted-foreground">
            Mentioned, not yet linked: {mentioned.join(", ")}
          </p>
        )}
        {(sh?.suggested_count ?? 0) > 0 && (
          <p className="mt-0.5 text-xs text-muted-foreground/70">
            {sh.suggested_count} suggested connection
            {sh.suggested_count === 1 ? "" : "s"} to review on the official's page.
          </p>
        )}
      </div>

      {(brief.recent_commitments.length > 0 ||
        brief.open_followups.length > 0 ||
        brief.upcoming_dates.length > 0) && (
        <div className="grid gap-4 border-t border-border pt-3 sm:grid-cols-3">
          {brief.open_followups.length > 0 && (
            <div>
              <div className={section}>Open follow-ups</div>
              <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                {brief.open_followups.map((f, i) => (
                  <li key={i}>
                    {f.title}
                    {f.overdue && <Badge tone="danger"> overdue</Badge>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {brief.recent_commitments.length > 0 && (
            <div>
              <div className={section}>Recent commitments</div>
              <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                {brief.recent_commitments.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}
          {brief.upcoming_dates.length > 0 && (
            <div>
              <div className={section}>Upcoming dates</div>
              <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                {brief.upcoming_dates.map((d, i) => (
                  <li key={i}>
                    {d.kind} · in {d.in_days} days
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <p className="text-xs text-muted-foreground/60">
        Generated by {brief.generated_by}. Not a recommendation to send anything —
        a human decides the next step.
      </p>
    </div>
  );
}

interface ParsedEmail {
  from_name: string | null;
  from_email: string | null;
  date: string | null;
  subject: string | null;
  body: string;
  quoted_removed: boolean;
  matched_relationship_id: number | null;
}

function LogInteractionForm({
  relationshipId,
  onDone,
}: {
  relationshipId: number;
  onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"notes" | "email">("notes");
  const [type, setType] = useState<InteractionType>("meeting");
  const [direction, setDirection] = useState<Direction>("outbound");
  const [notes, setNotes] = useState("");
  const [rawEmail, setRawEmail] = useState("");
  const [parsed, setParsed] = useState<ParsedEmail | null>(null);

  const reset = () => {
    setNotes("");
    setRawEmail("");
    setParsed(null);
    setOpen(false);
  };

  const parse = useMutation({
    mutationFn: () =>
      api<ParsedEmail>("/interactions/email/parse", {
        method: "POST",
        body: JSON.stringify({ raw_email: rawEmail }),
      }),
    onSuccess: (p) => {
      setParsed(p);
      setType("email");
      setDirection("inbound");
      setNotes(
        (p.subject ? `Subject: ${p.subject}\n\n` : "") + p.body,
      );
    },
  });

  const create = useMutation({
    mutationFn: () =>
      api("/interactions", {
        method: "POST",
        body: JSON.stringify({
          relationship_id: relationshipId,
          type,
          direction,
          channel: mode === "email" ? "email" : null,
          occurred_at: parsed?.date ?? null,
          raw_notes: notes,
        }),
      }),
    onSuccess: () => {
      reset();
      onDone();
    },
  });

  const field = inputClass.replace("py-2", "py-1.5");

  if (!open) {
    return (
      <Button size="sm" onClick={() => setOpen(true)}>
        Log interaction
      </Button>
    );
  }

  return (
    <form
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        create.mutate();
      }}
      className="rounded-lg border border-border bg-card p-4 shadow-sm"
    >
      <div className="mb-3 inline-flex rounded-md border border-border p-0.5 text-xs">
        {(["notes", "email"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`rounded px-2.5 py-1 font-medium ${
              mode === m
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted"
            }`}
          >
            {m === "notes" ? "Typed notes" : "Paste email"}
          </button>
        ))}
      </div>

      {mode === "email" && (
        <div className="mb-3">
          <textarea
            className={`w-full font-mono text-xs ${field}`}
            rows={5}
            placeholder="Paste the full email (headers + body) or an .eml file's contents"
            value={rawEmail}
            onChange={(e) => setRawEmail(e.target.value)}
          />
          <div className="mt-1.5 flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={!rawEmail.trim() || parse.isPending}
              onClick={() => parse.mutate()}
            >
              {parse.isPending ? "Parsing…" : "Parse email"}
            </Button>
            {parsed && (
              <span className="text-xs text-muted-foreground">
                from {parsed.from_name ?? parsed.from_email ?? "—"}
                {parsed.date && ` · ${new Date(parsed.date).toLocaleDateString()}`}
                {parsed.quoted_removed && " · quoted history removed"}
                {parsed.matched_relationship_id &&
                  parsed.matched_relationship_id !== relationshipId &&
                  " · sender maps to a different relationship"}
              </span>
            )}
            {parse.error instanceof ApiError && (
              <span className="text-xs text-destructive">{parse.error.message}</span>
            )}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <select
          className={field}
          value={type}
          onChange={(e) => setType(e.target.value as InteractionType)}
        >
          {INTERACTION_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select
          className={field}
          value={direction}
          onChange={(e) => setDirection(e.target.value as Direction)}
        >
          {DIRECTIONS.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </div>
      <textarea
        className={`mt-2 w-full ${field}`}
        rows={mode === "email" ? 5 : 4}
        required
        placeholder="What happened? English or Hindi is fine."
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      {create.error instanceof ApiError && (
        <p className="mt-1 text-sm text-destructive">{create.error.message}</p>
      )}
      <div className="mt-2 flex gap-2">
        <Button type="submit" size="sm" disabled={create.isPending}>
          {create.isPending ? "Saving…" : "Save & extract"}
        </Button>
        <Button type="button" size="sm" variant="secondary" onClick={reset}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function InteractionCard({
  interactionId,
  relationshipId,
  summary,
  canEdit,
  onTaskAdded,
}: {
  interactionId: number;
  relationshipId: number;
  summary: { type: string; direction: string; occurred_at: string; sentiment: keyof typeof SENTIMENT_TONE; ai_summary: string | null };
  canEdit: boolean;
  onTaskAdded: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const detailQuery = useQuery({
    queryKey: ["interaction", interactionId],
    queryFn: () => api<InteractionDetail>(`/interactions/${interactionId}`),
    enabled: expanded,
  });
  const addTask = useMutation({
    mutationFn: (title: string) =>
      api("/tasks", {
        method: "POST",
        body: JSON.stringify({
          relationship_id: relationshipId,
          title,
          source_interaction_id: interactionId,
        }),
      }),
    onSuccess: onTaskAdded,
  });

  return (
    <div className="rounded-lg border border-border bg-card shadow-sm p-3 text-sm">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start justify-between gap-3 text-left"
      >
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium capitalize text-foreground">
              {summary.type} · {summary.direction}
            </span>
            <Badge tone={SENTIMENT_TONE[summary.sentiment]}>{summary.sentiment}</Badge>
          </div>
          <p className="mt-1 text-muted-foreground">{summary.ai_summary ?? "—"}</p>
        </div>
        <span className="shrink-0 text-xs text-muted-foreground">
          {new Date(summary.occurred_at).toLocaleDateString()}
        </span>
      </button>

      {expanded && detailQuery.data && (
        <div className="mt-3 grid gap-3 border-t border-border pt-3 sm:grid-cols-2">
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Raw notes
            </div>
            <p className="mt-1 whitespace-pre-wrap text-muted-foreground">
              {detailQuery.data.raw_notes}
            </p>
          </div>
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Extracted{" "}
              <span className="text-muted-foreground/60">
                ({detailQuery.data.ai_model})
              </span>
            </div>
            <StructuredList
              data={detailQuery.data.structured}
              canEdit={canEdit}
              onAddTask={(title) => addTask.mutate(title)}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function StructuredList({
  data,
  canEdit,
  onAddTask,
}: {
  data: { topics?: string[]; commitments?: string[]; requests?: string[]; people?: string[] } | null;
  canEdit: boolean;
  onAddTask: (title: string) => void;
}) {
  if (!data) return <p className="mt-1 text-muted-foreground">—</p>;
  return (
    <div className="mt-1 space-y-2 text-xs">
      {data.commitments && data.commitments.length > 0 && (
        <div>
          <div className="font-medium text-foreground">Commitments</div>
          <ul className="mt-0.5 space-y-1">
            {data.commitments.map((c, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <span className="flex-1 text-muted-foreground">{c}</span>
                {canEdit && (
                  <button
                    onClick={() => onAddTask(c.slice(0, 280))}
                    className="shrink-0 rounded border border-border px-1.5 text-[11px] text-secondary hover:bg-muted"
                  >
                    + task
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {(["requests", "topics", "people"] as const).map((key) =>
        data[key] && data[key]!.length > 0 ? (
          <div key={key}>
            <span className="font-medium capitalize text-foreground">{key}: </span>
            <span className="text-muted-foreground">{data[key]!.join("; ")}</span>
          </div>
        ) : null,
      )}
    </div>
  );
}
