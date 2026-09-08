import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { Badge, VerificationBadge } from "../components/Badge";
import { useAuth } from "../auth/AuthProvider";
import { api, ApiError } from "../lib/api";
import {
  DATE_KIND_LABELS,
  FIELD_LABELS,
  PROVENANCED_FIELDS,
  type DateKind,
  type OfficialDate,
  type OfficialDetail,
  type OrgUnit,
  type ProvenancedField,
  type TimelineEntry,
} from "../types";

export function OfficialProfilePage() {
  const { id } = useParams<{ id: string }>();
  const officialId = Number(id);
  const { user } = useAuth();
  const canEdit = user?.role === "admin" || user?.role === "relationship_manager";
  const isAdmin = user?.role === "admin";
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<ProvenancedField | null>(null);

  const officialQuery = useQuery({
    queryKey: ["official", officialId],
    queryFn: () => api<OfficialDetail>(`/officials/${officialId}`),
  });
  const unitsQuery = useQuery({
    queryKey: ["units", "flat"],
    queryFn: () => api<OrgUnit[]>("/organization/units"),
  });
  const timelineQuery = useQuery({
    queryKey: ["official", officialId, "timeline"],
    queryFn: () => api<TimelineEntry[]>(`/officials/${officialId}/timeline`),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["official", officialId] });
    queryClient.invalidateQueries({ queryKey: ["officials"] });
  };

  const setField = useMutation({
    mutationFn: (vars: { field: string; body: Record<string, unknown> }) =>
      api<OfficialDetail>(`/officials/${officialId}/fields/${vars.field}`, {
        method: "PUT",
        body: JSON.stringify(vars.body),
      }),
    onSuccess: () => {
      invalidate();
      setEditing(null);
    },
  });

  const verifyField = useMutation({
    mutationFn: (field: string) =>
      api<OfficialDetail>(`/officials/${officialId}/fields/${field}/verify`, {
        method: "POST",
      }),
    onSuccess: invalidate,
  });

  if (officialQuery.isPending) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (officialQuery.error) {
    return (
      <p className="text-sm text-destructive">
        {officialQuery.error instanceof ApiError
          ? officialQuery.error.message
          : "Could not load this official."}
      </p>
    );
  }

  const official = officialQuery.data!;
  const unitName = (unitId: number | null) =>
    unitsQuery.data?.find((u) => u.id === unitId)?.name ?? (unitId ? `#${unitId}` : "—");

  const displayValue = (field: ProvenancedField): string => {
    if (field === "organization_unit_id")
      return unitName(official.organization_unit_id);
    return (official[field] as string | null) ?? "—";
  };

  return (
    <div>
      <Link
        to="/officials"
        className="text-sm text-muted-foreground hover:underline"
      >
        ← All officials
      </Link>

      <div className="mt-2 flex items-center gap-3">
        <h1 className="font-heading text-xl font-bold text-foreground">
          {official.name}
        </h1>
        <VerificationBadge status={official.verification_status} />
        {official.status === "archived" && <Badge tone="warn">archived</Badge>}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <div className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
          <div className="border-b border-border px-4 py-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Identity fields
          </div>
          {PROVENANCED_FIELDS.map((field) => {
            const prov = official.fields[field];
            return (
              <div key={field} className="border-b border-border px-4 py-3 last:border-b-0">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-xs text-muted-foreground">
                      {FIELD_LABELS[field]}
                    </div>
                    <div className="text-sm font-medium text-foreground">
                      {displayValue(field)}
                    </div>
                    {prov && (
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <span>source: {prov.source}</span>
                        {prov.confidence != null && (
                          <span>· {prov.confidence}% confidence</span>
                        )}
                        <VerificationBadge status={prov.verification_status} />
                      </div>
                    )}
                    {!prov && (
                      <div className="mt-1 text-xs text-muted-foreground">
                        no source recorded
                      </div>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    {canEdit && (
                      <button
                        onClick={() =>
                          setEditing(editing === field ? null : field)
                        }
                        className="rounded border border-border px-2 py-1 text-xs hover:bg-muted"
                      >
                        {editing === field ? "Close" : prov ? "Edit" : "Add source"}
                      </button>
                    )}
                    {isAdmin &&
                      prov &&
                      prov.verification_status === "unverified" && (
                        <button
                          onClick={() => verifyField.mutate(field)}
                          disabled={verifyField.isPending}
                          className="rounded bg-accent px-2 py-1 text-xs font-medium text-accent-foreground hover:opacity-90 disabled:opacity-60"
                        >
                          Verify
                        </button>
                      )}
                  </div>
                </div>

                {editing === field && (
                  <FieldEditor
                    field={field}
                    units={unitsQuery.data ?? []}
                    current={
                      field === "organization_unit_id"
                        ? official.organization_unit_id?.toString() ?? ""
                        : ((official[field] as string | null) ?? "")
                    }
                    currentSource={prov?.source ?? ""}
                    pending={setField.isPending}
                    error={setField.error}
                    onSubmit={(body) => setField.mutate({ field, body })}
                  />
                )}
              </div>
            );
          })}
        </div>

        <div className="space-y-6">
          <DatedFacts officialId={officialId} canEdit={canEdit} isAdmin={isAdmin} />

          <div className="rounded-lg border border-border bg-card shadow-sm p-4">
            <div className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Timeline
            </div>
            {timelineQuery.data && timelineQuery.data.length === 0 && (
              <p className="text-sm text-muted-foreground">Nothing yet.</p>
            )}
            <ol className="space-y-3">
              {timelineQuery.data?.map((entry, i) => (
                <li key={i} className="text-sm">
                  <div className="font-medium text-foreground">
                    {describeAction(entry)}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {new Date(entry.at).toLocaleString()}
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
}

function DatedFacts({
  officialId,
  canEdit,
  isAdmin,
}: {
  officialId: number;
  canEdit: boolean;
  isAdmin: boolean;
}) {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<DateKind>("birthday");
  const [value, setValue] = useState("");
  const [source, setSource] = useState("");

  const datesQuery = useQuery({
    queryKey: ["official", officialId, "dates"],
    queryFn: () => api<OfficialDate[]>(`/officials/${officialId}/dates`),
  });
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["official", officialId, "dates"] });

  const setDate = useMutation({
    mutationFn: () =>
      api(`/officials/${officialId}/dates/${kind}`, {
        method: "PUT",
        body: JSON.stringify({ value, source }),
      }),
    onSuccess: () => {
      setValue("");
      setSource("");
      invalidate();
    },
  });
  const verify = useMutation({
    mutationFn: (dateId: number) =>
      api(`/officials/${officialId}/dates/${dateId}/verify`, { method: "POST" }),
    onSuccess: invalidate,
  });

  const field =
    "rounded-md border border-input bg-background px-2 py-1 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <div className="rounded-lg border border-border bg-card shadow-sm p-4">
      <div className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Dated facts
      </div>
      {datesQuery.data?.length === 0 && (
        <p className="text-sm text-muted-foreground">None recorded.</p>
      )}
      <div className="space-y-2">
        {datesQuery.data?.map((d) => (
          <div key={d.id} className="flex items-center justify-between gap-2 text-sm">
            <div>
              <span className="text-muted-foreground">{DATE_KIND_LABELS[d.kind]}: </span>
              <span className="font-medium text-foreground">
                {new Date(d.value).toLocaleDateString()}
              </span>
              <span className="ml-1 text-xs text-muted-foreground">· {d.source}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <VerificationBadge
                status={
                  d.verification_status === "verified"
                    ? "verified"
                    : "unverified"
                }
              />
              {isAdmin && d.verification_status === "unverified" && (
                <button
                  onClick={() => verify.mutate(d.id)}
                  className="rounded bg-accent px-2 py-0.5 text-xs font-medium text-accent-foreground hover:opacity-90"
                >
                  Verify
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {canEdit && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setDate.mutate();
          }}
          className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3"
        >
          <select
            className={field}
            value={kind}
            onChange={(e) => setKind(e.target.value as DateKind)}
          >
            {(Object.keys(DATE_KIND_LABELS) as DateKind[]).map((k) => (
              <option key={k} value={k}>
                {DATE_KIND_LABELS[k]}
              </option>
            ))}
          </select>
          <input
            type="date"
            required
            className={field}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          <input
            required
            placeholder="source"
            className={`${field} w-28`}
            value={source}
            onChange={(e) => setSource(e.target.value)}
          />
          <button
            type="submit"
            disabled={setDate.isPending}
            className="rounded-md bg-primary px-3 py-1 text-sm font-semibold text-primary-foreground hover:bg-secondary disabled:opacity-60"
          >
            Save
          </button>
        </form>
      )}
      <p className="mt-2 text-[11px] text-muted-foreground">
        Only verified dates trigger engagement moments.
      </p>
    </div>
  );
}

function describeAction(entry: TimelineEntry): string {
  switch (entry.action) {
    case "official.create":
      return "Official created";
    case "official.update":
      return "Details updated";
    case "official_field.set":
      return `Field set · source "${String(entry.after?.["source"] ?? "")}"`;
    case "official_field.verify":
      return "Field verified";
    default:
      return entry.action;
  }
}

function FieldEditor({
  field,
  units,
  current,
  currentSource,
  pending,
  error,
  onSubmit,
}: {
  field: ProvenancedField;
  units: OrgUnit[];
  current: string;
  currentSource: string;
  pending: boolean;
  error: unknown;
  onSubmit: (body: Record<string, unknown>) => void;
}) {
  const [value, setValue] = useState(current);
  const [source, setSource] = useState(currentSource);
  const [confidence, setConfidence] = useState("");

  const input =
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          value: value === "" ? null : value,
          source,
          confidence: confidence === "" ? null : Number(confidence),
        });
      }}
      className="mt-3 grid gap-2 rounded-md border border-border bg-background/60 p-3 sm:grid-cols-2"
    >
      <label className="text-xs">
        <span className="mb-1 block font-medium text-foreground">Value</span>
        {field === "organization_unit_id" ? (
          <select
            className={input}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          >
            <option value="">— none —</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        ) : (
          <input
            className={input}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        )}
      </label>
      <label className="text-xs">
        <span className="mb-1 block font-medium text-foreground">Source</span>
        <input
          className={input}
          required
          value={source}
          placeholder="e.g. Excel import, email thread, manual"
          onChange={(e) => setSource(e.target.value)}
        />
      </label>
      <label className="text-xs">
        <span className="mb-1 block font-medium text-foreground">
          Confidence (optional)
        </span>
        <input
          className={input}
          type="number"
          min={0}
          max={100}
          value={confidence}
          onChange={(e) => setConfidence(e.target.value)}
        />
      </label>
      <div className="flex items-end sm:col-span-2">
        {error instanceof ApiError && (
          <p className="mr-3 text-xs text-destructive">{error.message}</p>
        )}
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground hover:bg-secondary disabled:opacity-60"
        >
          {pending ? "Saving…" : "Save (resets verification)"}
        </button>
      </div>
    </form>
  );
}
