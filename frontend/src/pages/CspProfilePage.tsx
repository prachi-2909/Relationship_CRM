import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { Badge } from "../components/Badge";
import {
  HiddenNote,
  OpenCommitmentRows,
  ProposalRows,
  Subhead,
  SuggestionList,
  useIntelligenceActions,
  type IntelligenceScope,
} from "../components/IntelligenceParts";
import { CakeIcon, MailIcon, PhoneIcon } from "../components/sectionUi";
import { Card, Spinner } from "../components/ui";
import { useAuth } from "../auth/AuthProvider";
import { api, ApiError } from "../lib/api";
import {
  CALL_PROCESSING_STATUS_TONE,
  type CallSessionDetail,
  type CspProfileResponse,
  type PreCallResponse,
} from "../types";

function formatDuration(seconds: number | null, source: string | null): string | null {
  if (seconds === null) return null;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  const base = m > 0 ? `${m}m ${s}s` : `${s}s`;
  return source === "device_estimated" ? `${base} (approx.)` : base;
}

function formatDob(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** A Kiosk Operator's relationship profile: who they are, plus the full history of calls
 * had with them - the "ye baat hui" record. Read-only; calls are shown as they were
 * captured (RM CSP recordings are retained). */
export function CspProfilePage() {
  const { id } = useParams();
  const query = useQuery({
    queryKey: ["csp", "profile", id],
    queryFn: () => api<CspProfileResponse>(`/csps/${id}/profile`),
    enabled: !!id,
  });
  const preCall = useQuery({
    queryKey: ["csp", "pre-call", id],
    queryFn: () => api<PreCallResponse>(`/csps/${id}/pre-call`),
    enabled: !!id,
  });

  if (query.isPending) return <Spinner />;
  if (query.error instanceof ApiError)
    return (
      <div>
        <BackLink />
        <p className="mt-4 text-sm text-destructive">{query.error.message}</p>
      </div>
    );
  if (!query.data) return null;

  const { csp, calls, calls_total } = query.data;
  const dob = formatDob(csp.date_of_birth);
  const line = [csp.branch_name, csp.district, csp.state].filter(Boolean).join(" · ");

  return (
    <div className="space-y-4">
      <BackLink />

      {/* Who ----------------------------------------------------------------- */}
      <Card className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                {csp.csp_id}
              </span>
              <h1 className="font-heading text-xl font-bold text-foreground">{csp.name}</h1>
              {csp.category && <Badge tone="neutral">{csp.category}</Badge>}
              <Badge tone="good">Kiosk Operator</Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{line || "—"}</p>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
              <span>RM: {csp.rm_name}</span>
              {dob && (
                <span className="inline-flex items-center gap-1">
                  <CakeIcon className="h-4 w-4" /> {dob}
                </span>
              )}
              {csp.email && (
                <span className="inline-flex min-w-0 items-center gap-1">
                  <MailIcon className="h-4 w-4 shrink-0" />
                  <span className="truncate">{csp.email}</span>
                </span>
              )}
            </div>
            {(csp.address || csp.pincode) && (
              <p className="mt-1 text-xs text-muted-foreground">
                {[csp.address, csp.pincode].filter(Boolean).join(", ")}
              </p>
            )}
          </div>
          <div className="shrink-0 text-right">
            {csp.mobile ? (
              <a
                href={`tel:${csp.mobile}`}
                className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline"
              >
                <PhoneIcon className="h-4 w-4" /> {csp.mobile}
              </a>
            ) : (
              <span className="text-muted-foreground">no number</span>
            )}
            {csp.alternate_mobile && (
              <div className="text-xs text-muted-foreground">alt: {csp.alternate_mobile}</div>
            )}
          </div>
        </div>
      </Card>

      {/* Pre-Call Intelligence ---------------------------------------------- */}
      {preCall.data && <PreCallCard data={preCall.data} cspId={id!} />}

      {/* Calls --------------------------------------------------------------- */}
      <div>
        <h2 className="mb-2 flex items-center gap-2 font-heading text-sm font-semibold text-foreground">
          Calls with {csp.name}
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            {calls_total}
          </span>
        </h2>
        {calls.length === 0 ? (
          <Card className="p-6 text-center text-sm text-muted-foreground">
            No calls recorded with this operator yet.
          </Card>
        ) : (
          <div className="space-y-2.5">
            {calls.map((c) => (
              <CallRow key={c.id} call={c} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function BackLink() {
  return (
    <Link
      to="/officials"
      className="inline-block rounded-md px-2 py-1 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted"
    >
      &larr; Kiosk Operators
    </Link>
  );
}

/** Pre-Call Intelligence: what the RM told the CSP last time, the commitments both sides made, the AI's
 * suggestions to review, relationship memory and talking points - everything to know before dialling. */
function PreCallCard({ data, cspId }: { data: PreCallResponse; cspId: string }) {
  const { user } = useAuth();
  const [showMemory, setShowMemory] = useState(false);
  const scope: IntelligenceScope = {
    base: "/csps",
    subjectId: Number(cspId),
    queryKey: ["csp", "pre-call", cspId],
    canAct: user?.role === "admin" || user?.role === "relationship_manager",
  };
  const actions = useIntelligenceActions(scope);
  const oc = data.open_commitments;
  const perf = data.performance;
  const nothing =
    oc.total === 0 &&
    data.proposed_commitments.length === 0 &&
    data.talking_point_items.length === 0 &&
    !perf &&
    !data.last_call &&
    data.memory.length === 0;

  return (
    <Card className="border-primary/30 bg-primary/[0.03] p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-heading text-sm font-semibold text-foreground">Before you call</h2>
        <Badge tone="primary">Pre-call intelligence</Badge>
      </div>

      {nothing && (
        <p className="text-sm text-muted-foreground">
          No prior calls or open items yet &mdash; this will fill in after your first recorded call.
        </p>
      )}
      {actions.error && <p className="mb-2 text-xs text-destructive">{actions.error}</p>}

      {data.talking_point_items.length > 0 && (
        <div className="mb-3 rounded-lg border border-saffron/40 bg-saffron/10 p-3">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-[hsl(38_80%_28%)]">
            Talking points
          </div>
          <SuggestionList items={data.talking_point_items} scope={scope} actions={actions} />
          <HiddenNote count={data.suppressed_count} />
        </div>
      )}

      {perf && (
        <div className="mb-3 rounded-lg border border-border bg-card p-3">
          <div className="mb-0.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            What you told them last time
          </div>
          <p className="mb-2 text-xs text-muted-foreground">
            Your own review from the call on {new Date(perf.from).toLocaleDateString()} &mdash; the CSP does not
            report these figures, you do.
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            {(
              [
                ["Where they stand", perf.what],
                ["Why", perf.why],
                ["What it should be", perf.should_be],
              ] as const
            ).map(([label, lines]) => (
              <div key={label}>
                <Subhead>{label}</Subhead>
                {lines.length === 0 ? (
                  <p className="text-xs text-muted-foreground">&mdash;</p>
                ) : (
                  <ul className="space-y-0.5">
                    {lines.map((l, i) => (
                      <li key={i} className="text-sm text-foreground">
                        {l}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {data.proposed_commitments.length > 0 && (
        <div className="mb-3 rounded-lg border border-dashed border-primary/40 bg-card p-3">
          <div className="mb-0.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Suggested from your calls
          </div>
          <p className="mb-2 text-xs text-muted-foreground">
            The AI picked these out of your call briefs. Accept what was really agreed; dismiss the rest. Where one
            looks like an earlier commitment you decide whether it is the same &mdash; nothing is merged for you.
          </p>
          <ProposalRows items={data.proposed_commitments} scope={scope} actions={actions} />
        </div>
      )}

      {oc.total > 0 && (
        <div className="mb-3 grid gap-3 sm:grid-cols-2">
          <OpenCommitmentRows title="You committed" items={[...oc.ours, ...oc.mutual]} scope={scope} actions={actions} />
          <OpenCommitmentRows title="They committed" items={oc.theirs} scope={scope} actions={actions} />
        </div>
      )}

      {data.slab_status.length > 0 && (
        <div className="mb-3">
          <Subhead>Current slab status</Subhead>
          <div className="flex flex-wrap gap-1.5">
            {data.slab_status.map((s, i) => (
              <span key={i} className="rounded-full bg-muted px-2.5 py-0.5 text-xs text-foreground">
                {s}
              </span>
            ))}
          </div>
        </div>
      )}

      {data.last_call && (
        <div className="mb-3 rounded-lg border border-border bg-card p-3">
          <Subhead>Last call &middot; {new Date(data.last_call.when).toLocaleDateString()}</Subhead>
          <p className="text-sm text-foreground">{data.last_call.summary || "No summary."}</p>
        </div>
      )}

      {data.memory.length > 0 && (
        <div>
          <button onClick={() => setShowMemory((v) => !v)} className="text-xs font-medium text-secondary hover:underline">
            {showMemory ? "Hide" : "Show"} relationship memory ({data.memory.length})
          </button>
          {showMemory && (
            <ul className="mt-2 space-y-1">
              {data.memory.map((m, i) => (
                <li key={i} className="flex gap-1.5 text-xs text-muted-foreground">
                  <span className="mt-0.5">&bull;</span>
                  <span>{m.fact}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}

function CallRow({ call }: { call: CallSessionDetail }) {
  const [open, setOpen] = useState(false);
  const duration = formatDuration(call.duration_seconds, call.duration_source);
  const highlights = call.brief?.highlights ?? [];
  const hasDetail = !!call.transcript_text || highlights.length > 0 || !!call.brief?.summary;

  return (
    <Card className="p-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="font-medium capitalize text-foreground">{call.direction}</span>
            <span>{new Date(call.started_at).toLocaleString()}</span>
            {duration && <span>· {duration}</span>}
            <Badge tone={CALL_PROCESSING_STATUS_TONE[call.processing_status]}>
              {call.processing_status.replace(/_/g, " ")}
            </Badge>
          </div>

          {call.brief?.summary && (
            <p className="mt-1.5 text-sm text-foreground">{call.brief.summary}</p>
          )}

          {highlights.length > 0 && (
            <ul className="mt-1.5 space-y-0.5">
              {highlights.map((h, i) => (
                <li key={i} className="flex gap-1.5 text-xs text-muted-foreground">
                  <span className="mt-0.5 text-primary">•</span>
                  <span>{h}</span>
                </li>
              ))}
            </ul>
          )}

          {hasDetail && (
            <button
              onClick={() => setOpen((v) => !v)}
              className="mt-2 text-xs font-medium text-secondary hover:underline"
            >
              {open ? "Hide transcript" : "Show transcript"}
            </button>
          )}

          {open && call.transcript_text && (
            <p className="mt-2 whitespace-pre-wrap rounded-lg bg-muted/50 p-2.5 text-xs text-foreground">
              {call.transcript_text}
            </p>
          )}
        </div>
      </div>

      {call.has_voice_note && (
        <audio
          controls
          preload="none"
          className="mt-2.5 h-9 w-full"
          src={`/api/v1/calls/${call.id}/voice-note/audio`}
        >
          Your browser can’t play this recording.
        </audio>
      )}
    </Card>
  );
}
