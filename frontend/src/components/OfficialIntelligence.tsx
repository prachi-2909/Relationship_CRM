import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../auth/AuthProvider";
import { api, ApiError } from "../lib/api";
import type { OfficialIntelligence } from "../types";
import { Badge } from "./Badge";
import {
  HiddenNote,
  OpenCommitmentRows,
  ProposalRows,
  Subhead,
  SuggestionList,
  useIntelligenceActions,
  type IntelligenceScope,
} from "./IntelligenceParts";
import { Card } from "./ui";

const SENTIMENT_TONE: Record<string, "good" | "warn" | "danger" | "neutral"> = {
  positive: "good",
  neutral: "neutral",
  negative: "danger",
  mixed: "warn",
};

/** The SBI-official briefing: interaction history, relationship memory, who committed what, pending
 * follow-ups and suggested discussion points - read from the existing CRM records, not a separate store.
 * A DC sees it only for officials in their own territory (the server enforces that). */
export function OfficialIntelligenceCard({ officialId }: { officialId: number }) {
  const { user } = useAuth();
  const [showMemory, setShowMemory] = useState(false);
  const queryKey = ["official", officialId, "intelligence"] as const;
  const q = useQuery({
    queryKey,
    queryFn: () => api<OfficialIntelligence>(`/officials/${officialId}/intelligence`),
  });
  const scope: IntelligenceScope = {
    base: "/officials",
    subjectId: officialId,
    queryKey,
    canAct: user?.role === "admin" || user?.role === "dc",
  };
  const actions = useIntelligenceActions(scope);

  if (q.isPending) return null;
  if (q.error instanceof ApiError) {
    return (
      <Card className="mt-4 p-4">
        <p className="text-sm text-muted-foreground">The relationship briefing is not available: {q.error.message}</p>
      </Card>
    );
  }
  const d = q.data;
  if (!d) return null;

  const rel = d.relationship;
  const c = d.commitments;
  const nothing =
    d.interactions.length === 0 && d.memory.length === 0 && c.total === 0 && d.followups.length === 0 &&
    d.talking_point_items.length === 0 && d.followup_suggestion_items.length === 0 &&
    d.proposed_commitments.length === 0;

  return (
    <Card className="mt-4 border-primary/30 bg-primary/[0.03] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-heading text-sm font-semibold text-foreground">Relationship briefing</h2>
        <div className="flex flex-wrap items-center gap-1.5">
          {rel && (
            <>
              <Badge tone="neutral">{rel.status.replace(/_/g, " ")}</Badge>
              <Badge tone="neutral">{rel.importance}</Badge>
              <Badge tone="primary">
                health {rel.score} &middot; {rel.band}
              </Badge>
              {rel.days_since_contact !== null && (
                <Badge tone={rel.days_since_contact >= 35 ? "warn" : "neutral"}>
                  last contact {rel.days_since_contact}d ago
                </Badge>
              )}
            </>
          )}
        </div>
      </div>

      {nothing && (
        <p className="text-sm text-muted-foreground">
          Nothing logged for this official yet &mdash; the briefing fills in as calls are logged.
        </p>
      )}
      {actions.error && <p className="mb-2 text-xs text-destructive">{actions.error}</p>}

      {(d.talking_point_items.length > 0 || d.followup_suggestion_items.length > 0) && (
        <div className="mb-3 rounded-lg border border-saffron/40 bg-saffron/10 p-3">
          {d.talking_point_items.length > 0 && (
            <>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-[hsl(38_80%_28%)]">
                Discussion points
              </div>
              <SuggestionList items={d.talking_point_items} scope={scope} actions={actions} />
            </>
          )}
          {d.followup_suggestion_items.length > 0 && (
            <div className={d.talking_point_items.length > 0 ? "mt-3" : ""}>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-[hsl(38_80%_28%)]">
                Suggested follow-ups
              </div>
              <SuggestionList items={d.followup_suggestion_items} scope={scope} actions={actions} bullet={"→"} />
            </div>
          )}
          <HiddenNote count={d.suppressed_count} />
        </div>
      )}

      {d.proposed_commitments.length > 0 && (
        <div className="mb-3 rounded-lg border border-dashed border-primary/40 bg-card p-3">
          <div className="mb-0.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Awaiting approval
          </div>
          <ProposalRows items={d.proposed_commitments} scope={scope} actions={actions} />
        </div>
      )}

      {c.total > 0 && (
        <div className="mb-3 grid gap-3 sm:grid-cols-2">
          <OpenCommitmentRows title="You (DC) committed" items={[...c.ours, ...c.mutual]} scope={scope} actions={actions} />
          <OpenCommitmentRows title="The official committed" items={c.theirs} scope={scope} actions={actions} />
        </div>
      )}

      {d.followups.length > 0 && (
        <div className="mb-3 rounded-lg border border-border bg-card p-3">
          <Subhead>Pending follow-ups</Subhead>
          <ul className="space-y-1">
            {d.followups.map((f) => (
              <li key={f.id} className="flex flex-wrap items-center gap-2 text-sm text-foreground">
                <span>{f.title}</span>
                {f.due_at && (
                  <span className="text-xs text-muted-foreground">due {new Date(f.due_at).toLocaleDateString()}</span>
                )}
                {f.overdue && <Badge tone="danger">overdue</Badge>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {d.upcoming_dates.length > 0 && (
        <p className="mb-3 text-sm text-foreground">
          {d.upcoming_dates
            .map((u) => `${u.label} ${u.in_days === 0 ? "today" : `in ${u.in_days} day${u.in_days === 1 ? "" : "s"}`}`)
            .join(" · ")}
        </p>
      )}

      {d.interactions.length > 0 && (
        <div className="mb-3 rounded-lg border border-border bg-card p-3">
          <Subhead>Interaction history</Subhead>
          <ul className="divide-y divide-border">
            {d.interactions.map((i) => (
              <li key={i.id} className="py-1.5 text-sm">
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span>{new Date(i.occurred_at).toLocaleDateString()}</span>
                  <span className="capitalize">
                    {i.type} &middot; {i.direction}
                  </span>
                  <Badge tone={SENTIMENT_TONE[i.sentiment] ?? "neutral"}>{i.sentiment}</Badge>
                </div>
                <p className="text-foreground">{i.summary || "No summary."}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {d.memory.length > 0 && (
        <div>
          <button onClick={() => setShowMemory((v) => !v)} className="text-xs font-medium text-secondary hover:underline">
            {showMemory ? "Hide" : "Show"} relationship memory ({d.memory.length})
          </button>
          {showMemory && (
            <ul className="mt-2 space-y-1">
              {d.memory.map((m, i) => (
                <li key={i} className="flex flex-wrap gap-1.5 text-xs text-muted-foreground">
                  <span className="mt-0.5">&bull;</span>
                  <span>{m.fact}</span>
                  {m.state && <span className="text-[10px] uppercase">({m.state.replace(/_/g, " ")})</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}
