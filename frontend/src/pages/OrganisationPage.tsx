import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Badge } from "../components/Badge";
import { Card, EmptyState, PageHeader, Spinner } from "../components/ui";
import { useAuth } from "../auth/AuthProvider";
import { api, ApiError } from "../lib/api";
import type {
  OfficialListResponse,
  OrgUnit,
  OrgUnitNode,
  UnitStats,
  UnitSummary,
  UnitType,
} from "../types";

interface Crumb {
  id: number;
  name: string;
  type_code: string;
}

// Purely structural depth cues (never tied to a specific unit-type name) -
// the hierarchy is configurable data, not something the UI should hard-code.
const DEPTH_DOT = ["bg-primary", "bg-secondary", "bg-accent", "bg-saffron", "bg-muted-foreground"];

function flatten(nodes: OrgUnitNode[], depth = 0): { node: OrgUnitNode; depth: number }[] {
  return nodes.flatMap((node) => [{ node, depth }, ...flatten(node.children, depth + 1)]);
}

export function OrganisationPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const queryClient = useQueryClient();

  const [breadcrumb, setBreadcrumb] = useState<Crumb[]>([]);
  const [autoDrilled, setAutoDrilled] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingUnit, setEditingUnit] = useState(false);

  const currentId = breadcrumb.length > 0 ? breadcrumb[breadcrumb.length - 1].id : null;
  const currentCrumb = breadcrumb[breadcrumb.length - 1] ?? null;
  const showingRoots = breadcrumb.length === 0;

  const typesQuery = useQuery({
    queryKey: ["unit-types"],
    queryFn: () => api<UnitType[]>("/organization/unit-types"),
  });

  const rootsQuery = useQuery({
    queryKey: ["units", "roots"],
    queryFn: () => api<UnitSummary[]>("/organization/units?roots_only=true&status=active"),
    enabled: showingRoots,
  });

  // Land on the sole Corporate Centre's own overview + its RBOs, not a
  // trivial single-tile screen the admin has to click through first.
  useEffect(() => {
    if (!autoDrilled && showingRoots && rootsQuery.data?.length === 1) {
      const root = rootsQuery.data[0];
      setBreadcrumb([{ id: root.id, name: root.name, type_code: root.type_code }]);
      setAutoDrilled(true);
    }
  }, [autoDrilled, showingRoots, rootsQuery.data]);

  const childrenQuery = useQuery({
    queryKey: ["units", "children", currentId],
    queryFn: () => api<UnitSummary[]>(`/organization/units?parent_id=${currentId}&status=active`),
    enabled: currentId !== null,
  });

  const statsQuery = useQuery({
    queryKey: ["units", "stats", currentId],
    queryFn: () => api<UnitStats>(`/organization/units/${currentId}/stats`),
    enabled: currentId !== null,
  });

  const isLeaf = currentId !== null && childrenQuery.data?.length === 0;

  const officialsQuery = useQuery({
    queryKey: ["officials", "by-unit", currentId],
    queryFn: () => api<OfficialListResponse>(`/officials?unit_id=${currentId}&limit=200`),
    enabled: isLeaf,
  });

  // Full flat unit list, only loaded when an admin actually opens a form
  // that needs a global parent picker - the drill-down browsing above never
  // pays for fetching all 400+ units at once.
  const treeQuery = useQuery({
    queryKey: ["units", "tree"],
    queryFn: () => api<OrgUnitNode[]>("/organization/units/tree"),
    enabled: showAddForm || editingUnit,
  });
  const flatUnits = useMemo(
    () => (treeQuery.data ? flatten(treeQuery.data).map((r) => r.node) : []),
    [treeQuery.data],
  );

  const invalidateUnits = () => {
    queryClient.invalidateQueries({ queryKey: ["units"] });
  };

  const createUnit = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<OrgUnit>("/organization/units", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      invalidateUnits();
      setShowAddForm(false);
    },
  });

  const updateUnit = useMutation({
    mutationFn: (vars: { id: number; body: Record<string, unknown> }) =>
      api<OrgUnit>(`/organization/units/${vars.id}`, { method: "PATCH", body: JSON.stringify(vars.body) }),
    onSuccess: () => {
      invalidateUnits();
      setEditingUnit(false);
    },
  });

  const drillInto = (unit: UnitSummary) => {
    setBreadcrumb((prev) => [...prev, { id: unit.id, name: unit.name, type_code: unit.type_code }]);
    setShowAddForm(false);
    setEditingUnit(false);
  };

  const jumpTo = (index: number) => {
    setBreadcrumb((prev) => (index < 0 ? [] : prev.slice(0, index + 1)));
    setShowAddForm(false);
    setEditingUnit(false);
  };

  const toggleArchive = (unit: OrgUnit) =>
    updateUnit.mutate({
      id: unit.id,
      body: { status: unit.status === "archived" ? "active" : "archived" },
    });

  const typeLabel = (code: string) => typesQuery.data?.find((t) => t.code === code)?.label ?? code;

  const btnPrimary =
    "rounded-lg bg-gradient-to-br from-saffron to-[hsl(36_78%_46%)] px-3 py-1.5 text-sm font-semibold text-secondary-foreground shadow-glow-gold transition-transform hover:-translate-y-0.5";
  const btnGhost =
    "rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-semibold text-muted-foreground transition-colors hover:bg-muted";

  return (
    <div>
      <PageHeader
        title="Organisation"
        description="Drill into the hierarchy — Corporate Centre, its RBOs, and each RBO's branches — instead of one long flat list."
      />

      <div className="mt-4 flex flex-wrap items-center gap-1 text-sm">
        <button
          onClick={() => jumpTo(-1)}
          className={`rounded-md px-2 py-1 font-medium transition-colors ${
            showingRoots ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted"
          }`}
        >
          All units
        </button>
        {breadcrumb.map((crumb, i) => (
          <span key={crumb.id} className="flex items-center gap-1">
            <span className="text-muted-foreground/40">/</span>
            <button
              onClick={() => jumpTo(i)}
              className={`rounded-md px-2 py-1 font-medium transition-colors ${
                i === breadcrumb.length - 1
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted"
              }`}
            >
              {crumb.name}
            </button>
          </span>
        ))}
      </div>

      {currentCrumb && (
        <Card className="mt-3 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-heading text-lg font-bold text-foreground">{currentCrumb.name}</h2>
                <Badge tone="neutral">{typeLabel(currentCrumb.type_code)}</Badge>
              </div>
              {statsQuery.data && (
                <p className="mt-1 text-sm text-muted-foreground">
                  {statsQuery.data.total_units} unit{statsQuery.data.total_units === 1 ? "" : "s"} below
                  {" · "}
                  {statsQuery.data.total_officials} official{statsQuery.data.total_officials === 1 ? "" : "s"} in
                  total
                  {statsQuery.data.direct_officials > 0 &&
                    ` (${statsQuery.data.direct_officials} directly here)`}
                </p>
              )}
            </div>
            {isAdmin && (
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => {
                    setEditingUnit(false);
                    setShowAddForm((v) => !v);
                  }}
                  className={showAddForm ? btnGhost : btnPrimary}
                >
                  {showAddForm ? "Cancel" : "+ Add unit here"}
                </button>
                <button
                  onClick={() => {
                    setShowAddForm(false);
                    setEditingUnit((v) => !v);
                  }}
                  className={btnGhost}
                >
                  {editingUnit ? "Cancel" : "Edit / move"}
                </button>
              </div>
            )}
          </div>
        </Card>
      )}

      {showingRoots && isAdmin && (
        <div className="mt-3">
          <button
            onClick={() => {
              setEditingUnit(false);
              setShowAddForm((v) => !v);
            }}
            className={showAddForm ? btnGhost : btnPrimary}
          >
            {showAddForm ? "Cancel" : "+ Add a top-level unit"}
          </button>
        </div>
      )}

      {showAddForm && typesQuery.data && (
        <UnitForm
          types={typesQuery.data}
          units={flatUnits}
          initialParentId={currentId}
          pending={createUnit.isPending}
          error={createUnit.error}
          loadingUnits={treeQuery.isPending}
          onSubmit={(body) => createUnit.mutate(body)}
        />
      )}

      {editingUnit && currentCrumb && typesQuery.data && childrenQuery.data && (
        <UnitEditForm
          key={currentCrumb.id}
          unit={
            // the header card only has {id,name,type_code} - the full record
            // (location/department/status) is in the parent's children list,
            // or in the flat tree once it loads for this same admin action
            flatUnits.find((u) => u.id === currentCrumb.id) ??
            childrenQuery.data.find((u) => u.id === currentCrumb.id) ?? {
              id: currentCrumb.id,
              name: currentCrumb.name,
              type_code: currentCrumb.type_code,
              parent_id: breadcrumb.length > 1 ? breadcrumb[breadcrumb.length - 2].id : null,
              location: null,
              department: null,
              status: "active",
              metadata: null,
            }
          }
          types={typesQuery.data}
          units={flatUnits.filter((u) => u.id !== currentCrumb.id)}
          pending={updateUnit.isPending}
          error={updateUnit.error}
          loadingUnits={treeQuery.isPending}
          onSubmit={(body) => updateUnit.mutate({ id: currentCrumb.id, body })}
          onCancel={() => setEditingUnit(false)}
        />
      )}

      <div className="mt-4">
        {(showingRoots ? rootsQuery.isPending : childrenQuery.isPending) && <Spinner />}

        {showingRoots && rootsQuery.data && rootsQuery.data.length === 0 && (
          <Card>
            <EmptyState
              title="No units yet"
              hint={isAdmin ? "Add the first one above." : "Ask an admin to set up the hierarchy."}
            />
          </Card>
        )}

        {showingRoots && rootsQuery.data && rootsQuery.data.length > 0 && (
          <UnitGrid units={rootsQuery.data} typeLabel={typeLabel} isAdmin={isAdmin} onSelect={drillInto} onToggleArchive={toggleArchive} />
        )}

        {!showingRoots && childrenQuery.data && childrenQuery.data.length > 0 && (
          <UnitGrid units={childrenQuery.data} typeLabel={typeLabel} isAdmin={isAdmin} onSelect={drillInto} onToggleArchive={toggleArchive} />
        )}

        {isLeaf && (
          <Card className="p-4">
            <div className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Officials at {currentCrumb?.name}
            </div>
            {officialsQuery.isPending && <Spinner />}
            {officialsQuery.data && officialsQuery.data.items.length === 0 && (
              <EmptyState title="No officials here" hint="Nothing is directly attached to this unit yet." />
            )}
            {officialsQuery.data && officialsQuery.data.items.length > 0 && (
              <ul className="divide-y divide-border">
                {officialsQuery.data.items.map((o) => (
                  <li key={o.id} className="py-2">
                    <Link to={`/officials/${o.id}`} className="flex items-center justify-between gap-2 text-sm hover:underline">
                      <span className="font-medium text-foreground">{o.name}</span>
                      <span className="text-xs text-muted-foreground">{o.designation ?? "—"}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}

function UnitGrid({
  units,
  typeLabel,
  isAdmin,
  onSelect,
  onToggleArchive,
}: {
  units: UnitSummary[];
  typeLabel: (code: string) => string;
  isAdmin: boolean;
  onSelect: (unit: UnitSummary) => void;
  onToggleArchive: (unit: OrgUnit) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {units.map((unit, i) => (
        <button
          key={unit.id}
          onClick={() => onSelect(unit)}
          className="group flex flex-col items-start gap-1.5 rounded-xl border border-border bg-card p-3.5 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
        >
          <div className="flex w-full items-center justify-between gap-2">
            <span className="flex min-w-0 items-center gap-1.5">
              <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${DEPTH_DOT[i % DEPTH_DOT.length]}`} />
              <span className="truncate font-medium text-foreground">{unit.name}</span>
            </span>
            {isAdmin && (
              <span
                role="button"
                title={unit.status === "archived" ? "Reactivate" : "Archive"}
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleArchive(unit);
                }}
                className="hidden shrink-0 rounded-md px-1.5 py-0.5 text-xs text-muted-foreground opacity-0 hover:bg-muted hover:text-destructive group-hover:opacity-100 sm:inline-block"
              >
                {unit.status === "archived" ? "↺" : "✕"}
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone="neutral">{typeLabel(unit.type_code)}</Badge>
            {unit.status === "archived" && <Badge tone="warn">archived</Badge>}
          </div>
          <p className="text-xs text-muted-foreground">
            {unit.child_count > 0
              ? `${unit.child_count} unit${unit.child_count === 1 ? "" : "s"} below`
              : unit.official_count > 0
                ? `${unit.official_count} official${unit.official_count === 1 ? "" : "s"}`
                : "Empty"}
            {unit.location ? ` · ${unit.location}` : ""}
          </p>
        </button>
      ))}
    </div>
  );
}

function UnitEditForm({
  unit,
  types,
  units,
  pending,
  error,
  loadingUnits,
  onSubmit,
  onCancel,
}: {
  unit: OrgUnit;
  types: UnitType[];
  units: OrgUnit[];
  pending: boolean;
  error: unknown;
  loadingUnits: boolean;
  onSubmit: (body: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(unit.name);
  const [typeCode, setTypeCode] = useState(unit.type_code);
  const [parentId, setParentId] = useState<string>(
    unit.parent_id != null ? String(unit.parent_id) : "",
  );
  const [location, setLocation] = useState(unit.location ?? "");
  const [department, setDepartment] = useState(unit.department ?? "");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit({
      name,
      type_code: typeCode,
      parent_id: parentId ? Number(parentId) : null,
      location: location || null,
      department: department || null,
    });
  };

  const input =
    "w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <Card className="mt-3 p-4">
      <form onSubmit={submit} className="space-y-3 text-sm">
        <label className="block">
          <span className="mb-1 block font-medium text-foreground">Name</span>
          <input className={input} required value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="block">
          <span className="mb-1 block font-medium text-foreground">Type</span>
          <select className={input} value={typeCode} onChange={(e) => setTypeCode(e.target.value)}>
            {types.map((t) => (
              <option key={t.code} value={t.code}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block font-medium text-foreground">
            Parent unit {loadingUnits && "(loading full list…)"}
          </span>
          <select className={input} value={parentId} onChange={(e) => setParentId(e.target.value)}>
            <option value="">— top level —</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block font-medium text-foreground">Location</span>
          <input className={input} value={location} onChange={(e) => setLocation(e.target.value)} />
        </label>
        <label className="block">
          <span className="mb-1 block font-medium text-foreground">Department</span>
          <input className={input} value={department} onChange={(e) => setDepartment(e.target.value)} />
        </label>
        {error instanceof ApiError && <p className="text-sm text-destructive">{error.message}</p>}
        <div className="flex gap-2">
          <button
            type="submit"
            disabled={pending}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-secondary disabled:opacity-60"
          >
            {pending ? "Saving…" : "Save changes"}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted"
          >
            Cancel
          </button>
        </div>
      </form>
    </Card>
  );
}

function UnitForm({
  types,
  units,
  initialParentId,
  pending,
  error,
  loadingUnits,
  onSubmit,
}: {
  types: UnitType[];
  units: OrgUnit[];
  initialParentId: number | null;
  pending: boolean;
  error: unknown;
  loadingUnits: boolean;
  onSubmit: (body: Record<string, unknown>) => void;
}) {
  const [name, setName] = useState("");
  const [typeCode, setTypeCode] = useState(types[0]?.code ?? "");
  const [parentId, setParentId] = useState<string>(
    initialParentId != null ? String(initialParentId) : "",
  );
  const [location, setLocation] = useState("");
  const parentUnit = units.find((u) => u.id === initialParentId);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit({
      name,
      type_code: typeCode,
      parent_id: parentId ? Number(parentId) : null,
      location: location || null,
    });
  };

  const input =
    "w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <form
      onSubmit={submit}
      className="fade-in-up mt-3 grid gap-3 rounded-xl border border-border bg-card shadow-sm p-4 sm:grid-cols-2"
    >
      {initialParentId != null && (
        <p className="text-xs text-muted-foreground sm:col-span-2">
          Adding a unit under{" "}
          <span className="font-medium text-foreground">
            {parentUnit?.name ?? (loadingUnits ? "…" : `#${initialParentId}`)}
          </span>
          .
        </p>
      )}
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Name</span>
        <input className={input} value={name} required onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Type</span>
        <select className={input} value={typeCode} onChange={(e) => setTypeCode(e.target.value)}>
          {types.map((t) => (
            <option key={t.code} value={t.code}>
              {t.label}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Parent unit</span>
        <select className={input} value={parentId} onChange={(e) => setParentId(e.target.value)}>
          <option value="">— top level —</option>
          {units.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Location</span>
        <input className={input} value={location} onChange={(e) => setLocation(e.target.value)} />
      </label>
      <div className="sm:col-span-2">
        {error instanceof ApiError && <p className="mb-2 text-sm text-destructive">{error.message}</p>}
        <button
          type="submit"
          disabled={pending}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-secondary disabled:opacity-60"
        >
          {pending ? "Saving…" : "Create unit"}
        </button>
      </div>
    </form>
  );
}
