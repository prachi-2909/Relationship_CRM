import { SCORE_BANDS, type RiskLevel } from "../types";

const RISK_COLOR: Record<RiskLevel, string> = {
  low: "hsl(155 53% 32%)",
  medium: "hsl(38 80% 45%)",
  high: "hsl(0 70% 52%)",
};

export function bandFor(score: number) {
  return SCORE_BANDS.find((b) => score >= b.min) ?? SCORE_BANDS[SCORE_BANDS.length - 1];
}

export function ScoreDial({ score }: { score: number }) {
  const band = bandFor(score);
  const color = RISK_COLOR[band.risk];
  const r = 34;
  const circ = 2 * Math.PI * r;
  const filled = (score / 100) * circ;

  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 80 80" className="h-20 w-20 -rotate-90">
        <circle cx="40" cy="40" r={r} fill="none" stroke="hsl(30 20% 88%)" strokeWidth="8" />
        <circle
          cx="40"
          cy="40"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circ}`}
        />
      </svg>
      <div>
        <div className="text-2xl font-bold text-foreground">{score}</div>
        <div className="text-sm font-medium" style={{ color }}>
          {band.label}
        </div>
      </div>
    </div>
  );
}

export function ComponentBars({
  components,
}: {
  components: Record<string, unknown> | null;
}) {
  if (!components) return null;
  const weights = (components["_weights"] as Record<string, number>) ?? {};
  const rows = Object.keys(weights).map((key) => ({
    key,
    value: Number(components[key] ?? 0),
    weight: weights[key],
  }));
  if (rows.length === 0) return null;

  return (
    <div className="space-y-2">
      {rows.map((row) => (
        <div key={row.key} className="text-xs">
          <div className="flex justify-between text-muted-foreground">
            <span className="capitalize">
              {row.key} <span className="text-muted-foreground/60">· {row.weight}%</span>
            </span>
            <span className="tabular-nums">{row.value.toFixed(0)}</span>
          </div>
          <div className="mt-0.5 h-1.5 overflow-hidden rounded bg-muted">
            <div
              className="h-full rounded bg-primary"
              style={{ width: `${Math.max(0, Math.min(100, row.value))}%` }}
            />
          </div>
        </div>
      ))}
      <p className="pt-1 text-[11px] text-muted-foreground">
        weights {String(components["_version"] ?? "")}
      </p>
    </div>
  );
}
