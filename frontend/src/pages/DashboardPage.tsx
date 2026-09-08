import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Card, PageHeader, SectionLabel, Spinner } from "../components/ui";
import { api } from "../lib/api";

interface Summary {
  officials: number;
  units: number;
  relationships: number;
  average_health: number;
  at_risk: number;
  overdue_followups: number;
  my_overdue_followups: number;
  drafts_pending: number;
  moments_open: number;
  health_bands: Record<string, number>;
  moments_enabled: boolean;
}

const BAND_COLOR: Record<string, string> = {
  Strong: "hsl(155 53% 32%)",
  Healthy: "hsl(155 45% 46%)",
  "Attention required": "hsl(38 80% 46%)",
  "At risk": "hsl(0 70% 52%)",
};

export function DashboardPage() {
  const { data, isPending, error } = useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: () => api<Summary>("/dashboard/summary"),
  });

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description={
          <>
            A roll-up across the account.
            {data && !data.moments_enabled && (
              <span className="ml-2 rounded bg-saffron/20 px-1.5 py-0.5 text-xs text-[hsl(38_80%_30%)]">
                moment detection is OFF
              </span>
            )}
          </>
        }
      />

      {isPending && <Spinner />}
      {error && (
        <p className="text-sm text-destructive">Could not load the summary.</p>
      )}

      {data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Tile value={data.officials} label="Officials tracked" />
            <Tile value={data.relationships} label="Relationships" />
            <Tile value={data.average_health} label="Average health" hint="0–100" />
            <Tile
              value={data.at_risk}
              label="Relationships at risk"
              hint="score below 40"
              tone={data.at_risk > 0 ? "warn" : undefined}
            />
            <Tile
              value={data.overdue_followups}
              label="Overdue follow-ups"
              hint={`${data.my_overdue_followups} assigned to you`}
              to="/follow-ups"
              tone={data.overdue_followups > 0 ? "warn" : undefined}
            />
            <Tile
              value={data.drafts_pending}
              label="Drafts awaiting approval"
              to="/moments"
            />
            <Tile value={data.moments_open} label="Open moments" to="/moments" />
            <Tile value={data.units} label="Organisational units" />
          </div>

          <Card className="mt-8 max-w-xl p-4">
            <SectionLabel>Relationship health</SectionLabel>
            {(() => {
              const total =
                Object.values(data.health_bands).reduce((a, b) => a + b, 0) || 1;
              return (
                <div className="mt-3 space-y-2.5">
                  {Object.entries(data.health_bands).map(([band, count]) => (
                    <div key={band} className="text-sm">
                      <div className="flex justify-between text-muted-foreground">
                        <span>{band}</span>
                        <span className="tabular-nums">{count}</span>
                      </div>
                      <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${(count / total) * 100}%`,
                            background: BAND_COLOR[band] ?? "hsl(210 10% 50%)",
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              );
            })()}
          </Card>
        </>
      )}
    </div>
  );
}

function Tile({
  value,
  label,
  hint,
  to,
  tone,
}: {
  value: number | string;
  label: string;
  hint?: string;
  to?: string;
  tone?: "warn";
}) {
  const body = (
    <>
      <div
        className={`text-3xl font-bold tabular-nums ${
          tone === "warn" ? "text-[hsl(0_70%_45%)]" : "text-foreground"
        }`}
      >
        {value}
      </div>
      <div className="mt-1 text-sm text-foreground">{label}</div>
      {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
    </>
  );
  const cls = "rounded-lg border border-border bg-card p-4 shadow-sm";
  return to ? (
    <Link
      to={to}
      className={`${cls} block transition-colors hover:border-primary/40 hover:bg-primary/[0.03]`}
    >
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}
