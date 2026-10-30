import { useState } from "react";

import type { CspScore, TaraPanel } from "../types";
import { Badge } from "./Badge";
import { Subhead } from "./IntelligenceParts";
import { ScoreDial } from "./ScoreDial";
import { Card } from "./ui";

type Tone = "neutral" | "primary" | "good" | "warn" | "danger";

const inr = (n: number | null | undefined): string =>
  typeof n === "number" ? `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}` : "—";

const num = (n: number | null | undefined): string => (typeof n === "number" ? n.toLocaleString("en-IN") : "—");

function asOf(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

const BAND_TONE: Record<string, Tone> = {
  Strong: "good",
  Healthy: "good",
  "Attention required": "warn",
  "At risk": "danger",
};

function Bar({ label, value, missing }: { label: string; value: number | null; missing?: string }) {
  return (
    <div>
      <div className="mb-0.5 flex items-baseline justify-between text-xs">
        <span className="font-medium text-foreground">{label}</span>
        <span className="text-muted-foreground">{value === null ? missing ?? "—" : value}</span>
      </div>
      <div className="h-1.5 rounded-full bg-muted">
        {value !== null && (
          <div
            className={`h-1.5 rounded-full ${value >= 60 ? "bg-accent" : value >= 40 ? "bg-saffron" : "bg-destructive"}`}
            style={{ width: `${Math.max(2, Math.min(100, value))}%` }}
          />
        )}
      </div>
    </div>
  );
}

/** How this CSP's relationship stands: the relationship, the business (from TARA) and both together, each from plain
 * arithmetic on records, with the reasons in words, weakest first. */
export function CspScoreCard({ score }: { score: CspScore }) {
  if (score.overall === null) return null;
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-heading text-sm font-semibold text-foreground">Relationship score</h2>
        {score.band && <Badge tone={BAND_TONE[score.band] ?? "neutral"}>{score.band}</Badge>}
      </div>
      <div className="grid gap-4 sm:grid-cols-[auto_1fr]">
        <ScoreDial score={score.overall} />
        <div className="space-y-2.5">
          <Bar label="Relationship (contact, follow-through, picks up)" value={score.relationship} />
          <Bar
            label="Business (from TARA)"
            value={score.business}
            missing={score.tara_included ? undefined : "TARA figures not included"}
          />
        </div>
      </div>
      {score.reasons.length > 0 && (
        <div className="mt-3">
          <Subhead>Why</Subhead>
          <ul className="space-y-1">
            {score.reasons.map((r, i) => (
              <li key={i} className="flex gap-1.5 text-xs text-foreground">
                <span className="mt-0.5 text-muted-foreground">&bull;</span>
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-3 text-[11px] text-muted-foreground">
        Calculated from the CRM&apos;s call and commitment records{score.tara_included ? " and TARA’s figures" : ""}. Scoring
        version {score.version}.
      </p>
    </Card>
  );
}

const STATUS_TONE: Record<string, Tone> = { grow: "good", stable: "neutral", degrow: "danger" };

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/60 py-1 text-xs last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium text-foreground">{children}</span>
    </div>
  );
}

/** What TARA holds for this CSP right now, laid out for a call. Every number is TARA's own, with the month and the
 * as-of it belongs to; a target SBI has not set shows as "not set", never as 0. */
export function TaraPanelCard({ panel }: { panel: TaraPanel }) {
  const [notes, setNotes] = useState(false);

  if (!panel.available) {
    return (
      <Card className="p-4">
        <h2 className="mb-1 font-heading text-sm font-semibold text-foreground">TARA</h2>
        <p className="text-sm text-muted-foreground">
          TARA&apos;s figures are not available right now. The score above uses the CRM&apos;s own records only.
        </p>
      </Card>
    );
  }

  const next = panel.slab?.next ?? null;
  return (
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-heading text-sm font-semibold text-foreground">TARA says</h2>
        <div className="flex items-center gap-1.5">
          {panel.month && <Badge tone="neutral">{panel.month}</Badge>}
          {asOf(panel.as_of) && <Badge tone="primary">as of {asOf(panel.as_of)}</Badge>}
        </div>
      </div>

      {panel.slab && (
        <div className="mb-3 rounded-lg border border-border bg-card p-3">
          <Subhead>DFS slab</Subhead>
          <div className="mb-1 text-sm text-foreground">
            Reached: <b>{panel.slab.reached ?? panel.slab.reached_in_calling_sheet ?? "none"}</b>
            {panel.slab.target_in_calling_sheet && panel.slab.target_in_calling_sheet !== "—" && (
              <> &middot; aiming for <b>{panel.slab.target_in_calling_sheet}</b></>
            )}
          </div>
          {next && (
            <>
              <div className="mb-1 text-xs text-muted-foreground">
                Next: {next.name}
                {next.incentive_inr !== null && <> ({inr(next.incentive_inr)})</>}. {panel.slab.rule}
              </div>
              <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
                {next.schemes.map((s) => (
                  <div key={s.scheme} className="rounded border border-border px-2 py-1 text-center text-xs">
                    <div className="font-semibold text-foreground">{s.scheme}</div>
                    <div className="text-muted-foreground">
                      {num(s.have)} of {num(s.threshold)}
                    </div>
                    <div className={s.more ? "font-medium text-destructive" : "font-medium text-accent"}>
                      {s.more ? `${num(s.more)} more` : "done"}
                    </div>
                  </div>
                ))}
              </div>
              {next.closest_three.length > 0 && (
                <p className="mt-1.5 text-xs text-muted-foreground">
                  Closest three: {next.closest_three.join(", ")}
                  {next.extra_total !== null && <> &middot; {num(next.extra_total)} more in all</>}
                </p>
              )}
            </>
          )}
          <p className="mt-1 text-[11px] text-muted-foreground">Counted from {panel.slab.basis}.</p>
        </div>
      )}

      <div className="mb-3">
        <Subhead>The four schemes this month</Subhead>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="py-1 pr-2 font-medium">Scheme</th>
                <th className="py-1 pr-2 font-medium">Done</th>
                <th className="py-1 pr-2 font-medium">SBI target</th>
                <th className="py-1 pr-2 font-medium">TARA goal</th>
                <th className="py-1 font-medium">Pace</th>
              </tr>
            </thead>
            <tbody>
              {panel.products.map((p) => (
                <tr key={p.code} className="border-t border-border/60">
                  <td className="py-1 pr-2 font-semibold text-foreground">{p.name}</td>
                  <td className="py-1 pr-2">{num(p.achieved)}</td>
                  <td className="py-1 pr-2">{p.sbi_target === null ? <span className="text-muted-foreground">not set</span> : num(p.sbi_target)}</td>
                  <td className="py-1 pr-2">
                    {p.tara_goal === null ? (
                      <span className="text-muted-foreground">not set</span>
                    ) : (
                      <>
                        {num(p.progress)} of {num(p.tara_goal)}
                        {p.agent_target !== null && <span className="text-muted-foreground"> (stretch {num(p.agent_target)})</span>}
                      </>
                    )}
                  </td>
                  <td className="py-1">{p.pace_status ? p.pace_status.replace(/_/g, " ") : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {panel.transactions && (
          <div>
            <Subhead>Transactions this month</Subhead>
            <Row label="Count">{num(panel.transactions.count)}</Row>
            <Row label="Value">{inr(panel.transactions.gtv_inr)}</Row>
            <Row label="Days with data">{num(panel.transactions.days_with_data)}</Row>
            <Row label="Last day with data">{panel.transactions.last_day_with_data ?? "—"}</Row>
          </div>
        )}
        {panel.earnings && (
          <div>
            <Subhead>Earnings{panel.earnings.month ? ` (${panel.earnings.month})` : ""}</Subhead>
            <Row label="Earned">{inr(panel.earnings.value_inr)}</Row>
            <Row label="Usual">{inr(panel.earnings.usual_inr)}</Row>
            <Row label="Change">
              {panel.earnings.growth_pct === null ? "—" : `${panel.earnings.growth_pct > 0 ? "+" : ""}${panel.earnings.growth_pct.toFixed(0)}%`}{" "}
              {panel.earnings.status && <Badge tone={STATUS_TONE[panel.earnings.status] ?? "neutral"}>{panel.earnings.status}</Badge>}
            </Row>
            {panel.earnings.rank_in_district !== null && (
              <Row label="Rank in district">
                {panel.earnings.rank_in_district} of {num(panel.earnings.of_in_district)}
              </Row>
            )}
            {panel.earnings.latest_posted_commission && (
              <Row label={`Posted ${panel.earnings.latest_posted_commission.label ?? ""}`}>
                {inr(panel.earnings.latest_posted_commission.inr)}
              </Row>
            )}
          </div>
        )}
        {panel.activity && (
          <div>
            <Subhead>Activity and kit</Subhead>
            <Row label="Last login">{panel.activity.last_login_date ?? "—"}</Row>
            <Row label="Days without activity">{num(panel.activity.days_without_activity)}</Row>
            <Row label="Login days this month">{num(panel.activity.login_days_this_month)}</Row>
            <Row label="Terminal">
              {panel.activity.terminal_status ? (
                <Badge tone={panel.activity.terminal_status.toLowerCase() === "inactive" ? "warn" : "good"}>
                  {panel.activity.terminal_status}
                </Badge>
              ) : (
                "—"
              )}
            </Row>
            <Row label="mATM / passbook printer / GPS">
              {[panel.activity.matm_status, panel.activity.passbook_printer_status, panel.activity.gps_dongle_status]
                .map((v) => v ?? "—")
                .join(" / ")}
            </Row>
          </div>
        )}
        {panel.call_priority && (
          <div>
            <Subhead>On the RM call list</Subhead>
            <Row label="Priority">{panel.call_priority.priority ?? "—"}</Row>
            <Row label="Rank today">{num(panel.call_priority.rank)}</Row>
            <Row label="Daily target">
              {num(panel.call_priority.daily_target_txns)} transactions / {inr(panel.call_priority.daily_target_inr)}
            </Row>
          </div>
        )}
      </div>

      {panel.opportunities.length > 0 && (
        <div className="mt-3">
          <Subhead>Where more earnings can come from</Subhead>
          <ul className="space-y-0.5">
            {panel.opportunities.map((o, i) => (
              <li key={i} className="text-xs text-foreground">
                <b>{(o.lever ?? "").replace(/_/g, " ").toUpperCase()}</b> &middot; about {inr(o.monthly_inr)} a month
              </li>
            ))}
          </ul>
        </div>
      )}
      {panel.balance && panel.balance.deposit_for_higher_slab_inr !== null && (
        <p className="mt-2 text-xs text-muted-foreground">
          Deposits needed for the next slab: {inr(panel.balance.deposit_for_higher_slab_inr)} across{" "}
          {num(panel.balance.total_accounts)} accounts.
        </p>
      )}

      {panel.caveats.length > 0 && (
        <div className="mt-3">
          <button onClick={() => setNotes((v) => !v)} className="text-xs font-medium text-secondary hover:underline">
            {notes ? "Hide" : "Show"} notes from TARA ({panel.caveats.length})
          </button>
          {notes && (
            <ul className="mt-1.5 space-y-1">
              {panel.caveats.map((c, i) => (
                <li key={i} className="flex gap-1.5 text-[11px] text-muted-foreground">
                  <span>&bull;</span>
                  <span>{c}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}
