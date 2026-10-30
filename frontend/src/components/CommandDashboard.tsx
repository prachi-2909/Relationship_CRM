import { type ReactNode, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api, ApiError } from "../lib/api";
import type { CommandDashboard } from "../types";
import { Button, Card, inputClass } from "./ui";

const RM_COLOR = "#2563EB";
const DC_COLOR = "#7C3AED";
const AXIS = "hsl(215 16% 47%)";

function ago(days: number | null): string {
  if (days === null) return "never";
  return days === 0 ? "today" : days === 1 ? "1 day ago" : `${days} days ago`;
}

function Tile({ label, value, warn, hint }: { label: string; value: ReactNode; warn?: boolean; hint?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-3.5 shadow-sm" title={hint}>
      <div className={`text-2xl font-bold tabular-nums ${warn ? "text-destructive" : "text-foreground"}`}>{value}</div>
      <div className="mt-0.5 text-xs font-medium text-muted-foreground">{label}</div>
    </div>
  );
}

function Panel({ title, hint, children, className = "" }: { title: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <Card className={`p-4 ${className}`}>
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h3 className="font-heading text-sm font-semibold text-foreground">{title}</h3>
        {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
      </div>
      {children}
    </Card>
  );
}

const th = "px-2 py-1.5 text-left text-xs font-medium text-muted-foreground";
const td = "px-2 py-1.5 text-sm tabular-nums";

/** The dashboard for whoever is signed in: the admin sees everyone (and can narrow to one RM or DC), an RM sees
 * their own CSPs and calls with a Call button, a DC sees their own SBI officials. Scoping is done by the server. */
export function CommandDashboardView() {
  const [rmId, setRmId] = useState("");
  const [dcId, setDcId] = useState("");
  const query = new URLSearchParams();
  if (rmId) query.set("rm_id", rmId);
  if (dcId) query.set("dc_id", dcId);
  const qs = query.toString();

  const { data, isPending, error } = useQuery({
    queryKey: ["dashboard", "command", qs],
    queryFn: () => api<CommandDashboard>(`/dashboard/command${qs ? `?${qs}` : ""}`),
    placeholderData: (prev) => prev,
  });

  const call = useMutation({
    // Register the call in the CRM first (so the recording can be matched to it), then hand over to the dialer.
    mutationFn: async (phone: string) => {
      await api("/calls/outgoing", { method: "POST", body: JSON.stringify({ phone }) });
      return phone;
    },
    onSuccess: (phone) => {
      window.location.href = `tel:${phone}`;
    },
  });

  if (isPending) return <div className="h-32 animate-pulse rounded-xl border border-border bg-muted/40" />;
  if (error || !data) return <p className="text-sm text-destructive">Could not load the dashboard.</p>;

  const { scope, filters, csp, officials, calls, work, rms, dcs } = data;
  const title =
    scope.role === "admin" || scope.role === "viewer"
      ? scope.can_filter && (rmId || dcId) ? "Filtered view" : "Everything, everyone"
      : scope.role === "relationship_manager" ? "My CSPs and calls" : "My SBI officials and calls";

  return (
    <div className="mb-8 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-heading text-base font-semibold text-foreground">{title}</h2>
        {filters && (
          <div className="flex flex-wrap items-center gap-2">
            <select className={`${inputClass} w-auto`} value={rmId} onChange={(e) => setRmId(e.target.value)} aria-label="Relationship Manager">
              <option value="">All RMs</option>
              {filters.rms.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
            <select className={`${inputClass} w-auto`} value={dcId} onChange={(e) => setDcId(e.target.value)} aria-label="District Coordinator">
              <option value="">All DCs</option>
              {filters.dcs.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
            {(rmId || dcId) && <Button variant="ghost" size="sm" onClick={() => { setRmId(""); setDcId(""); }}>Clear</Button>}
          </div>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
        {csp && <Tile label="Active CSPs" value={csp.active} />}
        {csp && <Tile label="CSPs not called in 30 days" value={csp.not_called_30d} warn={csp.not_called_30d > 0} hint={`${csp.never_called} never called`} />}
        {officials && <Tile label="SBI officials" value={officials.total} hint={`${officials.with_relationship} with a relationship`} />}
        {officials && <Tile label="Avg official relationship" value={officials.avg_score ?? "—"} />}
        <Tile label="Calls (7 days)" value={calls.last_7d} hint={`${calls.last_30d} in 30 days, ${calls.total} in all`} />
        <Tile label="Calls to review" value={calls.awaiting_review} warn={calls.awaiting_review > 0} />
        <Tile label="Overdue commitments" value={work.csp_commitments_overdue + work.official_commitments_overdue} warn={work.csp_commitments_overdue + work.official_commitments_overdue > 0} />
        <Tile label="Overdue follow-ups" value={work.followups_overdue} warn={work.followups_overdue > 0} />
      </div>

      {rms && rms.length > 0 && (
        <Panel title="Relationship Managers" hint="Calls count once reported back; connect rate is over the last 30 days">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px]">
              <thead><tr>
                <th className={th}>RM</th><th className={th}>CSPs</th><th className={th}>Calls 7d</th><th className={th}>Calls 30d</th>
                <th className={th}>Connect rate</th><th className={th}>Last call</th><th className={th}>CSPs not called</th><th className={th}>Overdue</th>
              </tr></thead>
              <tbody className="divide-y divide-border">
                {rms.map((r) => (
                  <tr key={r.id}>
                    <td className="px-2 py-1.5 text-sm font-medium">{r.name}</td>
                    <td className={td}>{r.csps}</td><td className={td}>{r.calls_7d}</td><td className={td}>{r.calls_30d}</td>
                    <td className={td}>{r.connect_rate_30d === null ? "—" : `${r.connect_rate_30d}%`}</td>
                    <td className={`${td} text-muted-foreground`}>{ago(r.days_since_last_call)}</td>
                    <td className={`${td} ${r.csps_not_called_30d > 0 ? "text-destructive" : ""}`}>{r.csps_not_called_30d}</td>
                    <td className={`${td} ${r.commitments_overdue > 0 ? "text-destructive" : ""}`}>{r.commitments_overdue}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {dcs && dcs.length > 0 && (
        <Panel title="District Coordinators" hint="SBI officials each DC looks after">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px]">
              <thead><tr>
                <th className={th}>DC</th><th className={th}>Officials</th><th className={th}>Avg score</th><th className={th}>At risk</th>
                <th className={th}>Not contacted 30d</th><th className={th}>Calls 30d</th><th className={th}>Last call</th><th className={th}>Overdue</th>
              </tr></thead>
              <tbody className="divide-y divide-border">
                {dcs.map((d) => (
                  <tr key={d.id}>
                    <td className="px-2 py-1.5 text-sm font-medium">{d.name}</td>
                    <td className={td}>{d.officials}</td><td className={td}>{d.avg_relationship ?? "—"}</td>
                    <td className={`${td} ${d.at_risk > 0 ? "text-destructive" : ""}`}>{d.at_risk}</td>
                    <td className={td}>{d.not_contacted_30d}</td><td className={td}>{d.calls_30d}</td>
                    <td className={`${td} text-muted-foreground`}>{ago(d.days_since_last_call)}</td>
                    <td className={`${td} ${d.followups_overdue > 0 ? "text-destructive" : ""}`}>{d.followups_overdue}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {csp && (
          <Panel title="CSPs to call" hint="Not called in 30 days, longest wait first">
            {csp.to_call.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">Every active CSP was called in the last 30 days.</p>
            ) : (
              <ul className="divide-y divide-border">
                {csp.to_call.map((c) => (
                  <li key={c.id} className="flex items-center gap-3 py-2">
                    <div className="min-w-0 flex-1">
                      <Link to={`/kiosk-operators/${c.id}`} className="block truncate text-sm font-medium text-foreground hover:underline">{c.name}</Link>
                      <div className="truncate text-xs text-muted-foreground">
                        {c.csp_id} · RM {c.rm_name ?? "—"} · {c.last_call_at ? `last call ${ago(c.days_since_last_call)}` : "never called"}
                        {c.overdue_commitments > 0 && ` · ${c.overdue_commitments} overdue`}
                      </div>
                    </div>
                    <Link to={`/kiosk-operators/${c.id}`} className="text-xs text-secondary hover:underline">Brief</Link>
                    {c.mobile && (
                      <Button size="sm" disabled={call.isPending} onClick={() => call.mutate(c.mobile as string)}>Call</Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {call.error instanceof ApiError && <p className="mt-2 text-sm text-destructive">{call.error.message}</p>}
          </Panel>
        )}

        {officials && (
          <Panel title="SBI officials needing attention" hint="Lowest relationship scores first">
            {officials.needs_attention.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">No relationships yet.</p>
            ) : (
              <ul className="divide-y divide-border">
                {officials.needs_attention.map((o) => (
                  <li key={o.relationship_id}>
                    <Link to={`/relationships/${o.relationship_id}`} className="-mx-2 flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-muted">
                      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-muted text-xs font-bold tabular-nums">{o.score}</span>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-foreground">{o.name}</div>
                        <div className="truncate text-xs text-muted-foreground">
                          {o.band}{o.level ? ` · ${o.level}` : ""} · DC {o.dc ?? "—"} · contact {o.days_since_contact === null ? "never" : ago(o.days_since_contact)}
                        </div>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Calls, last 14 days" hint="RM calls and DC calls" className="lg:col-span-2">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={calls.timeline} margin={{ top: 4, right: 8, bottom: 4, left: -20 }}>
              <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} tick={{ fill: AXIS, fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
              <YAxis allowDecimals={false} tick={{ fill: AXIS, fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip cursor={{ fill: "hsl(214 20% 94%)" }} />
              <Bar dataKey="rm" name="RM calls" stackId="a" fill={RM_COLOR} />
              <Bar dataKey="dc" name="DC calls" stackId="a" fill={DC_COLOR} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <div className="mt-1 flex gap-4 text-xs text-muted-foreground">
            <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm" style={{ background: RM_COLOR }} />RM calls</span>
            <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm" style={{ background: DC_COLOR }} />DC calls</span>
          </div>
        </Panel>

        <Panel title="Recent calls">
          {calls.recent.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">No calls yet.</p>
          ) : (
            <ul className="divide-y divide-border">
              {calls.recent.slice(0, 6).map((c) => (
                <li key={c.id}>
                  <Link to="/calls" className="-mx-2 block rounded-lg px-2 py-1.5 hover:bg-muted">
                    <div className="truncate text-sm font-medium text-foreground">{c.with ?? "Unidentified number"}</div>
                    <div className="truncate text-xs text-muted-foreground">
                      {c.by} · {c.when ? new Date(c.when).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "—"}
                      {c.seconds ? ` · ${c.seconds}s` : ""}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
