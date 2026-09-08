import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { VerificationBadge } from "../components/Badge";
import { useAuth } from "../auth/AuthProvider";
import { api, ApiError } from "../lib/api";
import type {
  OfficialDetail,
  OfficialListResponse,
  OrgUnit,
  VerificationStatus,
} from "../types";

const PAGE = 25;
const VERIF_OPTIONS: (VerificationStatus | "")[] = [
  "",
  "unverified",
  "partially_verified",
  "verified",
];

export function OfficialsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canEdit = user?.role === "admin" || user?.role === "relationship_manager";

  const [q, setQ] = useState("");
  const [level, setLevel] = useState("");
  const [verification, setVerification] = useState<VerificationStatus | "">("");
  const [offset, setOffset] = useState(0);
  const [showForm, setShowForm] = useState(false);

  const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  if (q) params.set("q", q);
  if (level) params.set("level", level);
  if (verification) params.set("verification_status", verification);

  const listQuery = useQuery({
    queryKey: ["officials", q, level, verification, offset],
    queryFn: () => api<OfficialListResponse>(`/officials?${params.toString()}`),
  });
  const unitsQuery = useQuery({
    queryKey: ["units", "flat"],
    queryFn: () => api<OrgUnit[]>("/organization/units"),
  });

  const createOfficial = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<OfficialDetail>("/officials", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["officials"] });
      setShowForm(false);
    },
  });

  const data = listQuery.data;
  const input =
    "rounded-md border border-input bg-background px-3 py-1.5 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-xl font-bold text-foreground">Officials</h1>
        {canEdit && (
          <button
            onClick={() => setShowForm((v) => !v)}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground hover:bg-secondary"
          >
            {showForm ? "Cancel" : "Add official"}
          </button>
        )}
      </div>

      {showForm && (
        <NewOfficialForm
          units={unitsQuery.data ?? []}
          pending={createOfficial.isPending}
          error={createOfficial.error}
          onSubmit={(body) => createOfficial.mutate(body)}
        />
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <input
          className={input}
          placeholder="Search by name…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
        />
        <input
          className={input}
          placeholder="Level"
          value={level}
          onChange={(e) => {
            setLevel(e.target.value);
            setOffset(0);
          }}
        />
        <select
          className={input}
          value={verification}
          onChange={(e) => {
            setVerification(e.target.value as VerificationStatus | "");
            setOffset(0);
          }}
        >
          {VERIF_OPTIONS.map((v) => (
            <option key={v} value={v}>
              {v === "" ? "Any verification" : v.replace("_", " ")}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card shadow-sm">
        {listQuery.isPending && (
          <div className="p-4 text-sm text-muted-foreground">Loading…</div>
        )}
        {data && data.items.length === 0 && (
          <div className="p-6 text-sm text-muted-foreground">No officials match.</div>
        )}
        {data && data.items.length > 0 && (
          <table className="w-full text-sm">
            <thead className="bg-muted text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Designation</th>
                <th className="px-4 py-2 font-medium">Level</th>
                <th className="px-4 py-2 font-medium">Location</th>
                <th className="px-4 py-2 font-medium">Verification</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((o) => (
                <tr key={o.id} className="border-t border-border hover:bg-muted/50">
                  <td className="px-4 py-2">
                    <Link
                      to={`/officials/${o.id}`}
                      className="font-medium text-secondary hover:underline"
                    >
                      {o.name}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {o.designation ?? "—"}
                  </td>
                  <td className="px-4 py-2">{o.level ?? "—"}</td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {o.location ?? "—"}
                  </td>
                  <td className="px-4 py-2">
                    <VerificationBadge status={o.verification_status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {data && (
        <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {data.total === 0
              ? "0"
              : `${offset + 1}–${Math.min(offset + PAGE, data.total)} of ${data.total}`}
          </span>
          <div className="flex gap-2">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE))}
              className="rounded border border-border px-2 py-1 disabled:opacity-40"
            >
              Prev
            </button>
            <button
              disabled={offset + PAGE >= data.total}
              onClick={() => setOffset(offset + PAGE)}
              className="rounded border border-border px-2 py-1 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function NewOfficialForm({
  units,
  pending,
  error,
  onSubmit,
}: {
  units: OrgUnit[];
  pending: boolean;
  error: unknown;
  onSubmit: (body: Record<string, unknown>) => void;
}) {
  const [name, setName] = useState("");
  const [level, setLevel] = useState("");
  const [unitId, setUnitId] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit({
      name,
      level: level || null,
      organization_unit_id: unitId ? Number(unitId) : null,
    });
  };

  const input =
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <form
      onSubmit={submit}
      className="mt-4 grid gap-3 rounded-lg border border-border bg-card shadow-sm p-4 sm:grid-cols-3"
    >
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Name</span>
        <input
          className={input}
          value={name}
          required
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Level</span>
        <input
          className={input}
          value={level}
          onChange={(e) => setLevel(e.target.value)}
        />
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Unit</span>
        <select
          className={input}
          value={unitId}
          onChange={(e) => setUnitId(e.target.value)}
        >
          <option value="">— none —</option>
          {units.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </select>
      </label>
      <div className="sm:col-span-3">
        {error instanceof ApiError && (
          <p className="mb-2 text-sm text-destructive">{error.message}</p>
        )}
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-secondary disabled:opacity-60"
        >
          {pending ? "Saving…" : "Create official"}
        </button>
        <span className="ml-3 text-xs text-muted-foreground">
          Add sources and verify individual fields on the profile.
        </span>
      </div>
    </form>
  );
}
