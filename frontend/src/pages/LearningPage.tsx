import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../components/Badge";
import { Card, EmptyState, PageHeader, Spinner } from "../components/ui";
import { api, ApiError } from "../lib/api";
import {
  AGENT_REC_TYPE_LABELS,
  EXPERIMENT_STATUS_TONE,
  OUTCOME_STATUS_TONE,
  STRATEGY_STATUS_TONE,
  STRATEGY_VERSION_STATUS_TONE,
  type EvaluationSummary,
  type ExperimentOut,
  type RecommendationListResponse,
  type RecommendationOutcome,
  type StrategyOut,
} from "../types";

const TABS = ["strategies", "experiments", "outcomes", "evaluation", "corrections"] as const;
type Tab = (typeof TABS)[number];

const TAB_LABELS: Record<Tab, string> = {
  strategies: "Strategy Registry",
  experiments: "Experiments",
  outcomes: "Outcomes",
  evaluation: "Evaluation",
  corrections: "Human Corrections",
};

export function LearningPage() {
  const [tab, setTab] = useState<Tab>("strategies");

  return (
    <div>
      <PageHeader
        title="Learning Dashboard"
        description="Evidence-backed strategies, controlled experiments, and what actually happened after the agent's recommendations were approved. Nothing here is applied automatically — promotion is always an explicit, sample-size-gated admin action."
      />

      <div className="inline-flex rounded-lg border border-border bg-card p-0.5 text-xs shadow-sm">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
              tab === t ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-muted"
            }`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {tab === "strategies" && <StrategiesTab />}
        {tab === "experiments" && <ExperimentsTab />}
        {tab === "outcomes" && <OutcomesTab />}
        {tab === "evaluation" && <EvaluationTab />}
        {tab === "corrections" && <CorrectionsTab />}
      </div>
    </div>
  );
}

function StrategiesTab() {
  const queryClient = useQueryClient();
  const strategiesQuery = useQuery({
    queryKey: ["strategies"],
    queryFn: () => api<StrategyOut[]>("/strategies"),
  });

  const promote = useMutation({
    mutationFn: (versionId: number) => api(`/strategies/versions/${versionId}/promote`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["strategies"] }),
  });
  const reject = useMutation({
    mutationFn: (versionId: number) => api(`/strategies/versions/${versionId}/reject`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["strategies"] }),
  });

  if (strategiesQuery.isPending) return <Spinner />;
  const strategies = strategiesQuery.data ?? [];
  if (strategies.length === 0) {
    return (
      <Card>
        <EmptyState
          title="No strategies registered yet"
          hint="Strategies are created via the API today (POST /strategies) — this view lets you review, test, and promote them."
        />
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {strategies.map((s) => (
        <Card key={s.id} className="p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div>
              <div className="font-heading text-sm font-semibold text-foreground">{s.name}</div>
              <div className="text-xs text-muted-foreground">
                {s.strategy_id} · {s.category}
              </div>
            </div>
            <Badge tone={STRATEGY_STATUS_TONE[s.status]}>{s.status}</Badge>
          </div>
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="py-1 font-medium">Version</th>
                <th className="py-1 font-medium">Status</th>
                <th className="py-1 font-medium">Config</th>
                <th className="py-1 font-medium">Evaluation</th>
                <th className="py-1 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {s.versions.map((v) => (
                <tr key={v.id} className="border-t border-border align-top">
                  <td className="py-1.5 tabular-nums">
                    v{v.version}
                    {s.current_version_id === v.id && (
                      <span className="ml-1 text-xs text-accent">(active)</span>
                    )}
                  </td>
                  <td className="py-1.5">
                    <Badge tone={STRATEGY_VERSION_STATUS_TONE[v.status]}>{v.status}</Badge>
                  </td>
                  <td className="py-1.5 font-mono text-xs text-muted-foreground">
                    {JSON.stringify(v.config)}
                  </td>
                  <td className="py-1.5 font-mono text-xs text-muted-foreground">
                    {v.evaluation_metrics ? JSON.stringify(v.evaluation_metrics) : "—"}
                  </td>
                  <td className="py-1.5">
                    {v.status === "testing" && (
                      <div className="flex gap-1.5">
                        <button
                          onClick={() => promote.mutate(v.id)}
                          disabled={promote.isPending}
                          className="rounded-md bg-gradient-to-br from-saffron to-[hsl(36_78%_46%)] px-2 py-1 text-xs font-semibold text-secondary-foreground shadow-glow-gold disabled:opacity-60"
                        >
                          Promote
                        </button>
                        <button
                          onClick={() => reject.mutate(v.id)}
                          disabled={reject.isPending}
                          className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-muted disabled:opacity-60"
                        >
                          Reject
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(promote.error instanceof ApiError || reject.error instanceof ApiError) && (
            <p className="mt-2 text-xs text-destructive">
              {(promote.error as ApiError)?.message ?? (reject.error as ApiError)?.message}
            </p>
          )}
        </Card>
      ))}
    </div>
  );
}

function ExperimentsTab() {
  const experimentsQuery = useQuery({
    queryKey: ["strategies", "experiments"],
    queryFn: () => api<ExperimentOut[]>("/strategies/experiments"),
  });

  if (experimentsQuery.isPending) return <Spinner />;
  const experiments = experimentsQuery.data ?? [];
  if (experiments.length === 0) {
    return (
      <Card>
        <EmptyState title="No experiments yet" hint="Assign relationships to a control/treatment version to start one." />
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-muted text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-4 py-2 font-medium">Experiment</th>
            <th className="px-4 py-2 font-medium">Control v.</th>
            <th className="px-4 py-2 font-medium">Treatment v.</th>
            <th className="px-4 py-2 font-medium">Sample</th>
            <th className="px-4 py-2 font-medium">Min. required</th>
            <th className="px-4 py-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {experiments.map((e) => {
            const control = e.assignments.filter((a) => a.arm === "control").length;
            const treatment = e.assignments.filter((a) => a.arm === "treatment").length;
            return (
              <tr key={e.id} className="border-t border-border">
                <td className="px-4 py-2">#{e.id}</td>
                <td className="px-4 py-2 tabular-nums">v{e.control_version_id} ({control})</td>
                <td className="px-4 py-2 tabular-nums">v{e.treatment_version_id} ({treatment})</td>
                <td className="px-4 py-2 tabular-nums">{e.assignments.length}</td>
                <td className="px-4 py-2 tabular-nums text-muted-foreground">{e.minimum_sample_size}/arm</td>
                <td className="px-4 py-2">
                  <Badge tone={EXPERIMENT_STATUS_TONE[e.status]}>{e.status}</Badge>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

function OutcomesTab() {
  const outcomesQuery = useQuery({
    queryKey: ["agent", "outcomes"],
    queryFn: () => api<RecommendationOutcome[]>("/agent/outcomes?limit=100"),
  });

  if (outcomesQuery.isPending) return <Spinner />;
  const outcomes = outcomesQuery.data ?? [];
  if (outcomes.length === 0) {
    return (
      <Card>
        <EmptyState
          title="No outcomes tracked yet"
          hint="Outcomes are backfilled and reconciled by the nightly job once recommendations are approved."
        />
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-muted text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-4 py-2 font-medium">Recommendation</th>
            <th className="px-4 py-2 font-medium">Tracked object</th>
            <th className="px-4 py-2 font-medium">Status</th>
            <th className="px-4 py-2 font-medium">Checked</th>
            <th className="px-4 py-2 font-medium">Resolved</th>
          </tr>
        </thead>
        <tbody>
          {outcomes.map((o) => (
            <tr key={o.id} className="border-t border-border">
              <td className="px-4 py-2">#{o.recommendation_id}</td>
              <td className="px-4 py-2 text-muted-foreground">
                {o.tracked_object_type} #{o.tracked_object_id}
              </td>
              <td className="px-4 py-2">
                <Badge tone={OUTCOME_STATUS_TONE[o.status]}>{o.status}</Badge>
                {o.detail?.proxy_signal ? (
                  <span className="ml-1.5 text-xs text-muted-foreground">(proxy signal)</span>
                ) : null}
              </td>
              <td className="px-4 py-2 text-xs text-muted-foreground">
                {new Date(o.checked_at).toLocaleString()}
              </td>
              <td className="px-4 py-2 text-xs text-muted-foreground">
                {o.resolved_at ? new Date(o.resolved_at).toLocaleString() : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function EvaluationTab() {
  const evalQuery = useQuery({
    queryKey: ["agent", "evaluation"],
    queryFn: () => api<EvaluationSummary>("/agent/evaluation"),
  });

  if (evalQuery.isPending) return <Spinner />;
  const m = evalQuery.data;
  if (!m || m.total_decided === 0) {
    return (
      <Card>
        <EmptyState title="No decided recommendations yet" hint="Approve or reject some agent recommendations to see metrics here." />
      </Card>
    );
  }

  const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(0)}%`);

  const tiles: { label: string; value: string }[] = [
    { label: "Recommendations decided", value: String(m.total_decided) },
    { label: "Approval rate", value: pct(m.approval_rate) },
    { label: "Outcomes resolved", value: String(m.resolved_outcomes) },
    { label: "Positive outcome rate", value: pct(m.positive_outcome_rate) },
    {
      label: "Median days to resolution",
      value: m.median_days_to_resolution === null ? "—" : m.median_days_to_resolution.toFixed(1),
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {tiles.map((t) => (
        <Card key={t.label} className="p-3.5">
          <div className="text-2xl font-bold tabular-nums text-foreground">{t.value}</div>
          <div className="mt-0.5 text-xs text-muted-foreground">{t.label}</div>
        </Card>
      ))}
    </div>
  );
}

function CorrectionsTab() {
  const rejectedQuery = useQuery({
    queryKey: ["agent", "recommendations", "rejected-for-corrections"],
    queryFn: () => api<RecommendationListResponse>("/agent/recommendations?status=rejected&limit=100"),
  });

  if (rejectedQuery.isPending) return <Spinner />;
  const rejected = rejectedQuery.data?.items ?? [];
  if (rejected.length === 0) {
    return (
      <Card>
        <EmptyState
          title="No corrections recorded"
          hint="A correction is a recommendation a human rejected — the agent proposed something the reviewer decided against."
        />
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-muted text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-4 py-2 font-medium">Official</th>
            <th className="px-4 py-2 font-medium">Agent proposed</th>
            <th className="px-4 py-2 font-medium">Reasoning</th>
            <th className="px-4 py-2 font-medium">Risk</th>
          </tr>
        </thead>
        <tbody>
          {rejected.map((r) => (
            <tr key={r.id} className="border-t border-border align-top">
              <td className="px-4 py-2">{r.official_name}</td>
              <td className="px-4 py-2">{AGENT_REC_TYPE_LABELS[r.type]}</td>
              <td className="px-4 py-2 text-muted-foreground">{r.reasoning}</td>
              <td className="px-4 py-2 capitalize text-muted-foreground">{r.risk_tier}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
