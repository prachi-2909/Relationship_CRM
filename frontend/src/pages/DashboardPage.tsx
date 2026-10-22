import { type FormEvent, type ReactNode, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button, Card, inputClass, PageHeader, SectionLabel } from "../components/ui";
import { CakeIcon, MailIcon } from "../components/sectionUi";
import { api, ApiError } from "../lib/api";
import type { AskResponse, DashboardOverview, NameValue } from "../types";

/* Validated categorical palette (dataviz skill, light surface #fcfcfb — all checks pass;
 * the one CVD warn sits in the legal 6–8 floor band, covered by the legends and direct
 * labels every chart below carries). Hues assigned in FIXED order, never cycled. */
const SERIES = ["#2563EB", "#16A34A", "#D97706", "#DB2777", "#7C3AED", "#0891B2", "#B45309"];

/* CSP tiers read better with semantic hues (gold = amber, silver = slate, bronze = brown)
 * than with an arbitrary categorical slot. */
function tierColor(name: string): string {
  const n = name.toLowerCase();
  if (n.includes("gold")) return "#D97706";
  if (n.includes("silver")) return "#64748B";
  if (n.includes("bronze")) return "#B45309";
  if (n.includes("diamond")) return "#0891B2";
  if (n.includes("basic")) return "#2563EB";
  return "#94A3B8"; // uncategorised
}

const AXIS = "hsl(215 16% 47%)"; // muted-foreground, recessive
const GRID = "hsl(214 20% 90%)";

export function DashboardPage() {
  const navigate = useNavigate();
  const { data, isPending, error } = useQuery({
    queryKey: ["dashboard", "overview"],
    queryFn: () => api<DashboardOverview>("/dashboard/overview"),
  });

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Your CSP network at a glance — operators, the RMs who run them, call activity and whose birthday is next. Click any figure or bar to drill in."
      />

      {isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl border border-border bg-muted/40" />
          ))}
        </div>
      )}
      {error && <p className="text-sm text-destructive">Could not load the dashboard.</p>}

      {data && (
        <>
          {/* KPI row ------------------------------------------------------------- */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            <Kpi label="Active CSPs" value={data.kpis.active_csps} accent="#2563EB" to="/officials" />
            <Kpi label="Relationship Managers" value={data.kpis.relationship_managers} accent="#7C3AED" to="/relationships" />
            <Kpi label="SBI Officials" value={data.kpis.sbi_officials} accent="#0891B2" to="/officials" />
            <Kpi label="Calls logged" value={data.kpis.calls_total} accent="#16A34A" to="/calls" />
            <Kpi label="Recordings" value={data.kpis.recordings} accent="#D97706" to="/calls" />
            <Kpi
              label="Birthdays this week"
              value={data.kpis.birthdays_7d}
              accent="#DB2777"
              icon={<CakeIcon className="h-4 w-4" />}
              to="#birthdays"
            />
          </div>

          {/* Charts ------------------------------------------------------------- */}
          <div className="mt-5 grid gap-4 lg:grid-cols-3">
            {/* CSPs by RM — who carries the biggest book. */}
            <ChartCard
              className="lg:col-span-2"
              title="CSPs by Relationship Manager"
              hint="Click a bar to open that RM's operators"
            >
              <ResponsiveContainer width="100%" height={Math.max(200, data.csps_by_rm.length * 64)}>
                <BarChart
                  layout="vertical"
                  data={data.csps_by_rm}
                  margin={{ top: 4, right: 40, bottom: 4, left: 8 }}
                  barCategoryGap="22%"
                >
                  <XAxis type="number" hide />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={110}
                    tick={{ fill: AXIS, fontSize: 13 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip cursor={{ fill: "hsl(214 20% 94%)" }} content={<PlainTooltip unit="CSPs" />} />
                  <Bar
                    dataKey="value"
                    radius={[4, 4, 4, 4]}
                    cursor="pointer"
                    onClick={() => navigate("/officials")}
                    label={{ position: "right", fill: AXIS, fontSize: 12, fontWeight: 600 }}
                  >
                    {data.csps_by_rm.map((_, i) => (
                      <Cell key={i} fill={SERIES[i % SERIES.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            {/* CSP tiers — part-to-whole. */}
            <ChartCard title="CSP tiers" hint="Share of operators by category">
              <TierDonut data={data.csps_by_category} onSlice={() => navigate("/officials")} />
            </ChartCard>

            {/* Call activity — change over time, full width. */}
            <ChartCard className="lg:col-span-3" title="Call activity" hint="Logged calls over the last 14 days">
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart
                  data={data.calls_timeline}
                  margin={{ top: 8, right: 16, bottom: 4, left: -16 }}
                  onClick={() => navigate("/calls")}
                  style={{ cursor: "pointer" }}
                >
                  <defs>
                    <linearGradient id="callFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#2563EB" stopOpacity={0.28} />
                      <stop offset="100%" stopColor="#2563EB" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="date"
                    tickFormatter={shortDay}
                    tick={{ fill: AXIS, fontSize: 12 }}
                    axisLine={{ stroke: GRID }}
                    tickLine={false}
                    interval="preserveStartEnd"
                    minTickGap={24}
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fill: AXIS, fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                    width={40}
                  />
                  <Tooltip content={<TimelineTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="#2563EB"
                    strokeWidth={2}
                    fill="url(#callFill)"
                    dot={false}
                    activeDot={{ r: 4, strokeWidth: 0 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </ChartCard>

            {/* Top states — magnitude across geography. */}
            <ChartCard className="lg:col-span-2" title="Top states" hint="Where the operators are, by state">
              <ResponsiveContainer width="100%" height={Math.max(160, data.csps_by_state.length * 34)}>
                <BarChart
                  layout="vertical"
                  data={data.csps_by_state}
                  margin={{ top: 4, right: 40, bottom: 4, left: 8 }}
                  barCategoryGap="24%"
                >
                  <XAxis type="number" hide />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={96}
                    tick={{ fill: AXIS, fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip cursor={{ fill: "hsl(214 20% 94%)" }} content={<PlainTooltip unit="CSPs" />} />
                  <Bar dataKey="value" radius={[4, 4, 4, 4]} fill="#0891B2" label={{ position: "right", fill: AXIS, fontSize: 12, fontWeight: 600 }} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            {/* Upcoming birthdays — the action list the wishes feature runs on. */}
            <ChartCard title="Upcoming birthdays" hint="Next 30 days" anchor="birthdays">
              {data.upcoming_birthdays.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">No birthdays in the next 30 days.</p>
              ) : (
                <ul className="divide-y divide-border">
                  {data.upcoming_birthdays.map((b) => (
                    <li key={b.csp_id} className="flex items-center gap-3 py-2">
                      <span
                        className={`grid h-9 w-9 shrink-0 place-items-center rounded-full text-xs font-bold tabular-nums ${
                          b.in_days === 0
                            ? "bg-[#DB2777] text-white"
                            : "bg-[#DB2777]/10 text-[#DB2777]"
                        }`}
                      >
                        {b.in_days === 0 ? <CakeIcon className="h-4 w-4" /> : `${b.in_days}d`}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-foreground">{b.name}</div>
                        <div className="truncate text-xs text-muted-foreground">
                          {b.in_days === 0 ? "Today" : birthdayDate(b.date)} · RM {b.rm_name}
                        </div>
                      </div>
                      {b.email && (
                        <MailIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </ChartCard>
          </div>

          <div className="mt-6">
            <AskCard />
          </div>
        </>
      )}
    </div>
  );
}

/* ---------- pieces ---------- */

function Kpi({
  label,
  value,
  accent,
  icon,
  to,
}: {
  label: string;
  value: number;
  accent: string;
  icon?: ReactNode;
  to?: string;
}) {
  const body = (
    <>
      <div className="flex items-center justify-between">
        <span className="h-8 w-1.5 rounded-full" style={{ background: accent }} />
        {icon && <span style={{ color: accent }}>{icon}</span>}
      </div>
      <div className="mt-2 text-3xl font-bold tabular-nums text-foreground">{value.toLocaleString()}</div>
      <div className="mt-0.5 text-xs font-medium text-muted-foreground">{label}</div>
    </>
  );
  const cls =
    "block rounded-xl border border-border bg-card p-3.5 shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md";
  if (to?.startsWith("#")) {
    return (
      <a href={to} className={cls}>
        {body}
      </a>
    );
  }
  return to ? (
    <Link to={to} className={cls}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

function ChartCard({
  title,
  hint,
  children,
  className = "",
  anchor,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
  className?: string;
  anchor?: string;
}) {
  return (
    <Card id={anchor} className={`p-4 ${className}`}>
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h3 className="font-heading text-sm font-semibold text-foreground">{title}</h3>
        {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
      </div>
      {children}
    </Card>
  );
}

function TierDonut({ data, onSlice }: { data: NameValue[]; onSlice: () => void }) {
  const total = data.reduce((a, b) => a + b.value, 0) || 1;
  return (
    <div>
      <div className="relative mx-auto h-[150px] w-[150px]">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              innerRadius={46}
              outerRadius={70}
              paddingAngle={2}
              stroke="hsl(60 20% 99%)"
              strokeWidth={2}
              cursor="pointer"
              onClick={onSlice}
            >
              {data.map((d, i) => (
                <Cell key={i} fill={tierColor(d.name)} />
              ))}
            </Pie>
            <Tooltip content={<PlainTooltip unit="CSPs" />} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-bold tabular-nums text-foreground">{total}</span>
          <span className="text-[10px] uppercase tracking-wide text-muted-foreground">CSPs</span>
        </div>
      </div>
      <ul className="mt-3 space-y-1.5">
        {data.map((d) => (
          <li key={d.name} className="flex items-center gap-2 text-xs">
            <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: tierColor(d.name) }} />
            <span className="flex-1 truncate text-muted-foreground">{d.name}</span>
            <span className="font-semibold tabular-nums text-foreground">{d.value}</span>
            <span className="w-9 text-right tabular-nums text-muted-foreground">
              {Math.round((d.value / total) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

interface TooltipProps {
  active?: boolean;
  payload?: { name: string; value: number; payload: { name?: string; date?: string } }[];
  unit?: string;
}

function PlainTooltip({ active, payload, unit }: TooltipProps) {
  if (!active || !payload?.length) return null;
  const p = payload[0];
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-1.5 text-xs shadow-md">
      <span className="font-medium text-foreground">{p.payload.name}</span>
      <span className="ml-2 font-semibold tabular-nums text-foreground">
        {p.value} {unit}
      </span>
    </div>
  );
}

function TimelineTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload?.length) return null;
  const p = payload[0];
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-1.5 text-xs shadow-md">
      <div className="text-muted-foreground">{p.payload.date && longDay(p.payload.date)}</div>
      <div className="font-semibold tabular-nums text-foreground">
        {p.value} {p.value === 1 ? "call" : "calls"}
      </div>
    </div>
  );
}

function shortDay(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
function longDay(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}
function birthdayDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/* ---------- Ask (unchanged feature, kept below the dashboard) ---------- */

interface Turn {
  question: string;
  response: AskResponse;
}

function AskCard() {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const conversationId = turns.at(-1)?.response.conversation_id;

  const ask = useMutation({
    mutationFn: (q: string) =>
      api<AskResponse>("/ask", {
        method: "POST",
        body: JSON.stringify({ question: q, conversation_id: conversationId ?? null }),
      }),
    onSuccess: (response, q) => {
      setTurns((t) => [...t, { question: q, response }]);
      setQuestion("");
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (question.trim().length >= 3) ask.mutate(question.trim());
  };

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <SectionLabel>Ask</SectionLabel>
        {turns.length > 0 && (
          <button
            type="button"
            onClick={() => setTurns([])}
            className="text-xs text-muted-foreground hover:underline"
          >
            New conversation
          </button>
        )}
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        A question across your relationships — read-only, nothing is sent.
        {turns.length > 0 && " Ask a follow-up and it remembers what you just discussed."}
      </p>

      {turns.length > 0 && (
        <div className="mt-3 space-y-4 border-b border-border pb-4">
          {turns.map((t, i) => (
            <div key={i} className="space-y-1.5 text-sm">
              <p className="font-medium text-foreground">{t.question}</p>
              <p className="leading-relaxed text-muted-foreground">{t.response.answer}</p>
              {t.response.considered.length > 0 && (
                <p className="text-xs text-muted-foreground/80">
                  Considered:{" "}
                  {t.response.considered.map((c, j) => (
                    <span key={c.relationship_id}>
                      {j > 0 && ", "}
                      <Link
                        to={`/relationships/${c.relationship_id}`}
                        className="text-secondary hover:underline"
                      >
                        {c.official_name}
                      </Link>
                    </span>
                  ))}
                </p>
              )}
              <p className="text-xs text-muted-foreground/60">
                Generated by {t.response.generated_by}.
              </p>
            </div>
          ))}
        </div>
      )}

      <form onSubmit={submit} className="mt-3 flex flex-wrap gap-2">
        <input
          className={`${inputClass} flex-1 min-w-[240px]`}
          placeholder={
            turns.length > 0
              ? "Ask a follow-up… e.g. what about his stakeholders?"
              : "e.g. What should I focus on this week? Or: What's going on with Adarsh?"
          }
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <Button type="submit" disabled={question.trim().length < 3 || ask.isPending}>
          {ask.isPending ? "Thinking…" : turns.length > 0 ? "Ask follow-up" : "Ask"}
        </Button>
      </form>

      {ask.error instanceof ApiError && (
        <p className="mt-2 text-sm text-destructive">{ask.error.message}</p>
      )}
    </Card>
  );
}
