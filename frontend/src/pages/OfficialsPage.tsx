import { useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { VerificationBadge } from "../components/Badge";
import { useAuth } from "../auth/AuthProvider";
import { api, ApiError } from "../lib/api";
import type {
  OfficialDetail,
  OfficialListResponse,
  OfficialSummary,
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

const AVATAR_PALETTE = [
  "bg-primary/15 text-secondary",
  "bg-accent/15 text-accent",
  "bg-[hsl(36_78%_46%)]/15 text-[hsl(36_70%_36%)]",
  "bg-destructive/10 text-destructive",
  "bg-muted text-muted-foreground",
];

function avatarClass(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

interface UnitGroup {
  key: string;
  unitName: string;
  unitType: string | null;
  items: OfficialSummary[];
}

export function OfficialsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canEdit = user?.role === "admin" || user?.role === "relationship_manager";

  const [q, setQ] = useState("");
  const [unitId, setUnitId] = useState("");
  const [verification, setVerification] = useState<VerificationStatus | "">("");
  const [offset, setOffset] = useState(0);
  const [showForm, setShowForm] = useState(false);

  const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  if (q) params.set("q", q);
  if (unitId) params.set("unit_id", unitId);
  if (verification) params.set("verification_status", verification);

  const listQuery = useQuery({
    queryKey: ["officials", q, unitId, verification, offset],
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
    "rounded-lg border border-input bg-surface px-3 py-1.5 text-sm outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/25";

  const groups = useMemo<UnitGroup[]>(() => {
    const map = new Map<string, UnitGroup>();
    for (const o of data?.items ?? []) {
      const key = o.organization_unit_name ?? "__unassigned__";
      if (!map.has(key)) {
        map.set(key, {
          key,
          unitName: o.organization_unit_name ?? "Unassigned",
          unitType: o.organization_unit_type,
          items: [],
        });
      }
      map.get(key)!.items.push(o);
    }
    return Array.from(map.values()).sort((a, b) => {
      if (a.key === "__unassigned__") return 1;
      if (b.key === "__unassigned__") return -1;
      return a.unitName.localeCompare(b.unitName);
    });
  }, [data]);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-heading text-xl font-bold text-foreground">Officials</h1>
          <p className="mt-1 text-sm text-muted-foreground">Grouped by organisation unit.</p>
        </div>
        {canEdit && (
          <button
            onClick={() => setShowForm((v) => !v)}
            className={
              showForm
                ? "rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-semibold text-muted-foreground transition-colors hover:bg-muted"
                : "rounded-lg bg-gradient-to-br from-saffron to-[hsl(36_78%_46%)] px-3 py-1.5 text-sm font-semibold text-secondary-foreground shadow-glow-gold transition-transform hover:-translate-y-0.5"
            }
          >
            {showForm ? "Cancel" : "+ Add official"}
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
        <select
          className={input}
          value={unitId}
          onChange={(e) => {
            setUnitId(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">Any unit</option>
          {(unitsQuery.data ?? []).map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </select>
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

      <div className="mt-4 space-y-4">
        {listQuery.isPending && (
          <div className="rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground shadow-sm">
            Loading…
          </div>
        )}
        {data && data.items.length === 0 && (
          <div className="rounded-xl border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground shadow-sm">
            No officials match.
          </div>
        )}
        {groups.map((group) => (
          <div
            key={group.key}
            className="overflow-hidden rounded-xl border border-border bg-card shadow-sm"
          >
            <div className="flex items-center justify-between gap-2 border-b border-border bg-muted px-4 py-2">
              <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
                {group.unitName}
                {group.unitType && (
                  <span className="rounded-full bg-card px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                    {group.unitType}
                  </span>
                )}
              </span>
              <span className="text-xs text-muted-foreground">
                {group.items.length} official{group.items.length === 1 ? "" : "s"}
              </span>
            </div>
            <div className="divide-y divide-border">
              {group.items.map((o) => (
                <Link
                  key={o.id}
                  to={`/officials/${o.id}`}
                  className="flex items-center gap-3 px-4 py-2.5 text-sm transition-colors hover:bg-muted/50"
                >
                  <span
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${avatarClass(o.name)}`}
                  >
                    {initials(o.name)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-secondary">{o.name}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {o.designation ?? "No designation on file"}
                      {o.level ? ` · ${o.level}` : ""}
                    </span>
                  </span>
                  <span className="hidden shrink-0 text-xs text-muted-foreground sm:block">
                    {o.location ?? "—"}
                  </span>
                  <VerificationBadge status={o.verification_status} />
                </Link>
              ))}
            </div>
          </div>
        ))}
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
              className="rounded-lg border border-border px-2.5 py-1 transition-colors hover:bg-muted disabled:opacity-40"
            >
              Prev
            </button>
            <button
              disabled={offset + PAGE >= data.total}
              onClick={() => setOffset(offset + PAGE)}
              className="rounded-lg border border-border px-2.5 py-1 transition-colors hover:bg-muted disabled:opacity-40"
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
  const [designation, setDesignation] = useState("");
  const [level, setLevel] = useState("");
  const [department, setDepartment] = useState("");
  const [location, setLocation] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [unitId, setUnitId] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit({
      name,
      designation: designation || null,
      level: level || null,
      department: department || null,
      location: location || null,
      email: email || null,
      phone: phone || null,
      organization_unit_id: unitId ? Number(unitId) : null,
    });
  };

  const input =
    "w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <form
      onSubmit={submit}
      className="fade-in-up mt-4 grid gap-3 rounded-xl border border-border bg-card shadow-sm p-4 sm:grid-cols-3"
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
        <span className="mb-1 block font-medium text-foreground">Designation</span>
        <input
          className={input}
          value={designation}
          onChange={(e) => setDesignation(e.target.value)}
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
        <span className="mb-1 block font-medium text-foreground">Department</span>
        <input
          className={input}
          value={department}
          onChange={(e) => setDepartment(e.target.value)}
        />
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Location</span>
        <input
          className={input}
          value={location}
          onChange={(e) => setLocation(e.target.value)}
        />
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Email</span>
        <input
          className={input}
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Phone</span>
        <input
          className={input}
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
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
        <p className="mb-2 text-xs text-muted-foreground">
          Fields you fill in are recorded with a “Manual entry” source. As an
          admin they’re marked verified straight away.
        </p>
        <button
          type="submit"
          disabled={pending}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-secondary disabled:opacity-60"
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
