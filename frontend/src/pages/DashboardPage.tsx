import { type FormEvent, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Button, Card, inputClass, PageHeader, SectionLabel, Spinner } from "../components/ui";
import { api, ApiError } from "../lib/api";
import type { AskResponse } from "../types";

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

      <AskCard />

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
    <Card className="mb-6 p-4">
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
