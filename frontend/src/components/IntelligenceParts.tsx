import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import type { Commitment, SuggestionItem } from "../types";

/** Where a briefing lives. The CSP and SBI-official briefings share one behaviour, so the same
 * components serve both; only the route prefix and subject id differ. */
export interface IntelligenceScope {
  /** "/csps" or "/officials" */
  base: string;
  subjectId: number;
  /** The query key of the briefing, refreshed after every change. */
  queryKey: readonly unknown[];
  /** False for read-only roles: the buttons are simply not shown (the server would refuse them too). */
  canAct: boolean;
}

export function useIntelligenceActions(scope: IntelligenceScope) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: [...scope.queryKey] });

  const setStatus = useMutation({
    mutationFn: (v: { id: number; status: "open" | "done" | "cancelled"; outcome?: "fulfilled" | "not_fulfilled" }) =>
      api(`${scope.base}/commitments/${v.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status: v.status, outcome: v.outcome ?? null }),
      }),
    onSuccess: refresh,
  });
  const review = useMutation({
    mutationFn: (v: { id: number; decision: "merge" | "separate" }) =>
      api(`${scope.base}/commitments/${v.id}/duplicate`, {
        method: "POST",
        body: JSON.stringify({ decision: v.decision }),
      }),
    onSuccess: refresh,
  });
  const rate = useMutation({
    mutationFn: (v: { item: SuggestionItem; verdict: string }) =>
      api(`${scope.base}/${scope.subjectId}/feedback`, {
        method: "POST",
        body: JSON.stringify({ target_type: v.item.type, key: v.item.key, verdict: v.verdict }),
      }),
    onSuccess: refresh,
  });

  const busy = setStatus.isPending || review.isPending || rate.isPending;
  const err = [setStatus.error, review.error, rate.error].find((e) => e instanceof ApiError) as ApiError | undefined;
  return { setStatus, review, rate, busy, error: err?.message ?? null };
}

export type IntelligenceActions = ReturnType<typeof useIntelligenceActions>;

const chip =
  "rounded-md border px-2 py-0.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50";
const chipIdle = "border-border text-muted-foreground hover:bg-muted";
const chipOn = "border-primary/50 bg-primary/10 text-primary";

/** A list of generated suggestions, each rateable ("Useful / Not useful" or "Relevant / Not relevant"). */
export function SuggestionList({
  items,
  scope,
  actions,
  bullet = "→",
}: {
  items: SuggestionItem[];
  scope: IntelligenceScope;
  actions: IntelligenceActions;
  bullet?: string;
}) {
  return (
    <ul className="space-y-1.5">
      {items.map((it) => {
        const [yes, no] = it.type === "followup" ? ["relevant", "not_relevant"] : ["useful", "not_useful"];
        const [yesLabel, noLabel] = it.type === "followup" ? ["Relevant", "Not relevant"] : ["Useful", "Not useful"];
        return (
          <li key={`${it.type}-${it.key}`} className="flex flex-wrap items-start gap-x-2 gap-y-1 text-sm">
            <span className="mt-0.5 text-saffron">{bullet}</span>
            <span className="min-w-0 flex-1 text-foreground">{it.text}</span>
            {scope.canAct && (
              <span className="flex shrink-0 gap-1">
                <button
                  disabled={actions.busy}
                  onClick={() => actions.rate.mutate({ item: it, verdict: yes })}
                  className={`${chip} ${it.my_verdict === yes ? chipOn : chipIdle}`}
                >
                  {yesLabel}
                </button>
                <button
                  disabled={actions.busy}
                  onClick={() => actions.rate.mutate({ item: it, verdict: no })}
                  className={`${chip} ${it.my_verdict === no ? chipOn : chipIdle}`}
                >
                  {noLabel}
                </button>
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function partyLabel(c: Commitment): string {
  return c.party === "theirs" ? "they" : c.party === "ours" ? "you" : "both";
}

function shortDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** AI-proposed commitments awaiting a person. A possible duplicate is shown beside what it resembles and
 * is only ever resolved by a click: "Same - merge" or "Different - keep both". */
export function ProposalRows({
  items,
  scope,
  actions,
}: {
  items: Commitment[];
  scope: IntelligenceScope;
  actions: IntelligenceActions;
}) {
  return (
    <ul className="space-y-3">
      {items.map((c) => (
        <li key={c.id} className="text-sm">
          <div className="flex flex-wrap items-start gap-2">
            <span className="min-w-0 flex-1 text-foreground">
              {c.text}
              <span className="ml-1.5 text-xs text-muted-foreground">({partyLabel(c)})</span>
              {c.due_date && (
                <span className="ml-1.5 text-xs text-muted-foreground">by {shortDate(c.due_date)}</span>
              )}
            </span>
            {scope.canAct && (
              <span className="flex shrink-0 gap-1.5">
                <button
                  disabled={actions.busy}
                  onClick={() => actions.setStatus.mutate({ id: c.id, status: "open" })}
                  className="rounded-md bg-primary px-2.5 py-1 text-xs font-semibold text-primary-foreground hover:bg-secondary disabled:opacity-50"
                >
                  Accept
                </button>
                <button
                  disabled={actions.busy}
                  onClick={() => actions.setStatus.mutate({ id: c.id, status: "cancelled" })}
                  className="rounded-md border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground hover:bg-muted disabled:opacity-50"
                >
                  Dismiss
                </button>
              </span>
            )}
          </div>
          {c.possible_duplicate && (
            <div className="mt-1.5 rounded-md border border-saffron/40 bg-saffron/10 p-2 text-xs text-foreground">
              <div className="font-medium text-[hsl(38_80%_28%)]">Looks like an earlier commitment</div>
              <div className="mt-0.5">
                &ldquo;{c.possible_duplicate.text}&rdquo;
                <span className="ml-1 text-muted-foreground">
                  ({c.possible_duplicate.status}
                  {c.possible_duplicate.due_date ? `, by ${shortDate(c.possible_duplicate.due_date)}` : ""})
                </span>
              </div>
              {scope.canAct && (
                <div className="mt-1.5 flex gap-1.5">
                  <button
                    disabled={actions.busy}
                    onClick={() => actions.review.mutate({ id: c.id, decision: "merge" })}
                    className={`${chip} ${chipIdle}`}
                  >
                    Same &mdash; merge
                  </button>
                  <button
                    disabled={actions.busy}
                    onClick={() => actions.review.mutate({ id: c.id, decision: "separate" })}
                    className={`${chip} ${chipIdle}`}
                  >
                    Different &mdash; keep both
                  </button>
                </div>
              )}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Open commitments. "Done" means it was actually fulfilled; "Not done" closes it as not fulfilled. */
export function OpenCommitmentRows({
  title,
  items,
  scope,
  actions,
}: {
  title: string;
  items: Commitment[];
  scope: IntelligenceScope;
  actions: IntelligenceActions;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</div>
      {items.length === 0 ? (
        <p className="text-xs text-muted-foreground">None open.</p>
      ) : (
        <ul className="space-y-2.5">
          {items.map((c) => (
            <li key={c.id} className="text-sm">
              <div className="flex flex-wrap items-start gap-2">
                <span className="min-w-0 flex-1 text-foreground">
                  {c.text}
                  {c.due_date && (
                    <span className="ml-1.5 text-xs text-muted-foreground">(by {shortDate(c.due_date)})</span>
                  )}
                </span>
                {scope.canAct && (
                  <span className="flex shrink-0 gap-1">
                    <button
                      disabled={actions.busy}
                      onClick={() => actions.setStatus.mutate({ id: c.id, status: "done", outcome: "fulfilled" })}
                      className={`${chip} ${chipIdle}`}
                    >
                      Done
                    </button>
                    <button
                      disabled={actions.busy}
                      onClick={() => actions.setStatus.mutate({ id: c.id, status: "cancelled", outcome: "not_fulfilled" })}
                      className={`${chip} ${chipIdle}`}
                    >
                      Not done
                    </button>
                  </span>
                )}
              </div>
              {c.also_mentioned && c.also_mentioned.length > 0 && (
                <div className="mt-0.5 text-xs text-muted-foreground">
                  Also mentioned on {c.also_mentioned.length} other call{c.also_mentioned.length === 1 ? "" : "s"}
                  {c.also_mentioned.some((m) => m.due_date)
                    ? ` (due ${c.also_mentioned.filter((m) => m.due_date).map((m) => shortDate(m.due_date!)).join(", ")})`
                    : ""}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Subhead({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{children}</div>
  );
}

/** A small "how many were hidden" note, so nothing a person marked unhelpful disappears silently. */
export function HiddenNote({ count }: { count: number }) {
  if (count === 0) return null;
  return (
    <p className="mt-1.5 text-xs text-muted-foreground">
      {count} suggestion{count === 1 ? "" : "s"} you marked not useful {count === 1 ? "is" : "are"} hidden for a while.
    </p>
  );
}
