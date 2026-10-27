import { useQuery } from "@tanstack/react-query";

import { Card, PageHeader, Spinner } from "../components/ui";
import { api, ApiError } from "../lib/api";
import type { QualityMetrics, RateStat } from "../types";

const KIND_LABEL: Record<string, string> = {
  close_commitment: "Close your commitment",
  check_theirs: "Check if they did",
  pending_from_last_call: "Pending from last call",
  steady_relationship: "Steady a tense relationship",
  stale_opportunity: "Stale opportunity",
  overdue_followup: "Overdue follow-up",
  open_followup: "Open follow-up",
  upcoming_date: "Upcoming birthday / anniversary",
  stale_contact: "No recent contact",
};

function pct(rate: number | null): string {
  return rate === null ? "—" : `${Math.round(rate * 100)}%`;
}

/** One headline figure. Below the minimum sample it says so instead of printing a misleading percentage. */
function Stat({ title, stat, min, detail }: { title: string; stat: RateStat; min: number; detail: string }) {
  return (
    <Card className="p-4">
      <div className="text-xs font-medium text-muted-foreground">{title}</div>
      {stat.enough_data ? (
        <div className="mt-1 text-3xl font-bold tabular-nums text-foreground">{pct(stat.rate)}</div>
      ) : (
        <div className="mt-1 text-lg font-semibold text-muted-foreground">Not enough data yet</div>
      )}
      <div className="mt-1 text-xs text-muted-foreground">
        {stat.enough_data ? detail : `${stat.n} of ${min} decisions needed before a rate is shown. ${detail}`}
      </div>
    </Card>
  );
}

function KindTable({ title, rows, min }: { title: string; rows: Record<string, RateStat>; min: number }) {
  const entries = Object.entries(rows);
  return (
    <Card className="p-4">
      <h3 className="mb-2 font-heading text-sm font-semibold text-foreground">{title}</h3>
      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">No ratings yet.</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="py-1 font-medium">Kind</th>
              <th className="py-1 text-right font-medium">Rated</th>
              <th className="py-1 text-right font-medium">Positive</th>
              <th className="py-1 text-right font-medium">Rate</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([kind, s]) => (
              <tr key={kind} className="border-t border-border">
                <td className="py-1.5">{KIND_LABEL[kind] ?? kind.replace(/_/g, " ")}</td>
                <td className="py-1.5 text-right tabular-nums">{s.n}</td>
                <td className="py-1.5 text-right tabular-nums">{s.positive}</td>
                <td className="py-1.5 text-right tabular-nums">
                  {s.enough_data ? pct(s.rate) : <span className="text-xs text-muted-foreground">needs {min}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

/** How good the relationship intelligence actually is - measured from explicit human decisions only. */
export function IntelligenceQualityPage() {
  const q = useQuery({
    queryKey: ["intelligence", "quality"],
    queryFn: () => api<QualityMetrics>("/intelligence/quality"),
  });
  if (q.isPending) return <Spinner />;
  if (q.error instanceof ApiError) return <p className="text-sm text-destructive">{q.error.message}</p>;
  const m = q.data;
  if (!m) return null;

  return (
    <div>
      <PageHeader
        title="Intelligence quality"
        description="Is the briefing helping? Every number comes from something a person explicitly did - rating a suggestion, accepting or dismissing a commitment, closing one, or ruling on a duplicate. A call happening or a brief being confirmed is never counted as the AI being right."
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          title="Suggestions accepted"
          stat={m.proposals}
          min={m.min_sample}
          detail={`${m.proposals.accepted} accepted, ${m.proposals.dismissed} dismissed.`}
        />
        <Stat
          title="Commitments fulfilled"
          stat={m.fulfilment}
          min={m.min_sample}
          detail={`${m.fulfilment.done} done, ${m.fulfilment.closed_without_doing} closed without doing.`}
        />
        <Stat
          title="Duplicate flags that were right"
          stat={m.duplicate_flags}
          min={m.min_sample}
          detail={`${m.duplicate_flags.confirmed_duplicate} merged, ${m.duplicate_flags.different_after_all} kept separate.`}
        />
        <Stat
          title="Talking points rated useful"
          stat={m.talking_points.overall}
          min={m.min_sample}
          detail={`${m.talking_points.overall.positive} of ${m.talking_points.overall.n} ratings.`}
        />
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <KindTable title="Talking points by kind" rows={m.talking_points.by_kind} min={m.min_sample} />
        <KindTable title="Suggested follow-ups by kind" rows={m.followups.by_kind} min={m.min_sample} />
      </div>

      <p className="mt-4 text-xs text-muted-foreground">
        A rate is only shown once at least {m.min_sample} decisions stand behind it. Once a kind of suggestion has
        that many ratings, the ones people find more useful are listed first &mdash; nothing is removed for anyone
        else. Generated {new Date(m.generated_at).toLocaleString()}.
      </p>
    </div>
  );
}
