import { useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../components/Badge";
import { useAuth } from "../auth/AuthProvider";
import { api, ApiError } from "../lib/api";
import type { OrgUnit, OrgUnitNode, UnitType } from "../types";

function flatten(nodes: OrgUnitNode[], depth = 0): { node: OrgUnitNode; depth: number }[] {
  return nodes.flatMap((node) => [
    { node, depth },
    ...flatten(node.children, depth + 1),
  ]);
}

// Purely structural depth cues (never tied to a specific unit-type name) -
// the hierarchy is configurable data, not something the UI should hard-code.
const DEPTH_DOT = ["bg-primary", "bg-secondary", "bg-accent", "bg-saffron", "bg-muted-foreground"];

export function OrganisationPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isAdmin = user?.role === "admin";
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [presetParentId, setPresetParentId] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);

  const typesQuery = useQuery({
    queryKey: ["unit-types"],
    queryFn: () => api<UnitType[]>("/organization/unit-types"),
  });
  const treeQuery = useQuery({
    queryKey: ["units", "tree"],
    queryFn: () => api<OrgUnitNode[]>("/organization/units/tree"),
  });

  const rows = useMemo(
    () => (treeQuery.data ? flatten(treeQuery.data) : []),
    [treeQuery.data],
  );
  const selected = rows.find((r) => r.node.id === selectedId)?.node ?? null;

  const invalidateUnits = () => queryClient.invalidateQueries({ queryKey: ["units"] });

  const createUnit = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<OrgUnit>("/organization/units", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      invalidateUnits();
      setShowForm(false);
    },
  });

  const updateUnit = useMutation({
    mutationFn: (vars: { id: number; body: Record<string, unknown> }) =>
      api<OrgUnit>(`/organization/units/${vars.id}`, {
        method: "PATCH",
        body: JSON.stringify(vars.body),
      }),
    onSuccess: () => {
      invalidateUnits();
      setEditing(false);
    },
  });

  const selectUnit = (id: number) => {
    setSelectedId(id);
    setEditing(false);
  };

  const openAddForm = (parentId: number | null) => {
    setPresetParentId(parentId);
    setShowForm(true);
  };

  const toggleArchive = (unit: OrgUnit) =>
    updateUnit.mutate({
      id: unit.id,
      body: { status: unit.status === "archived" ? "active" : "archived" },
    });

  const typeLabel = (code: string) =>
    typesQuery.data?.find((t) => t.code === code)?.label ?? code;

  const orderedTypes = typesQuery.data ?? [];

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-heading text-xl font-bold text-foreground">Organisation</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Build the hierarchy in whatever order you need — add a unit under any
            existing one, move it, or archive it, at any time.
          </p>
        </div>
        {isAdmin && (
          <button
            onClick={() => (showForm ? setShowForm(false) : openAddForm(null))}
            className={
              showForm
                ? "rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-semibold text-muted-foreground transition-colors hover:bg-muted"
                : "rounded-lg bg-gradient-to-br from-saffron to-[hsl(36_78%_46%)] px-3 py-1.5 text-sm font-semibold text-secondary-foreground shadow-glow-gold transition-transform hover:-translate-y-0.5"
            }
          >
            {showForm ? "Cancel" : "+ Add unit"}
          </button>
        )}
      </div>

      {orderedTypes.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-1.5 rounded-xl border border-border bg-card px-4 py-3 shadow-sm">
          <span className="mr-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Levels
          </span>
          {orderedTypes.map((t, i) => (
            <span key={t.code} className="flex items-center gap-1.5">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                  t.active
                    ? "bg-muted text-foreground"
                    : "bg-muted/50 text-muted-foreground/60 line-through"
                }`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${DEPTH_DOT[i % DEPTH_DOT.length]}`} />
                {t.label}
              </span>
              {i < orderedTypes.length - 1 && (
                <span className="text-muted-foreground/40">→</span>
              )}
            </span>
          ))}
        </div>
      )}

      {showForm && typesQuery.data && (
        <UnitForm
          types={typesQuery.data}
          units={rows.map((r) => r.node)}
          initialParentId={presetParentId}
          pending={createUnit.isPending}
          error={createUnit.error}
          onSubmit={(body) => createUnit.mutate(body)}
        />
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="rounded-xl border border-border bg-card p-2 shadow-sm">
          {treeQuery.isPending && (
            <div className="p-4 text-sm text-muted-foreground">Loading…</div>
          )}
          {treeQuery.data && rows.length === 0 && (
            <div className="p-6 text-sm text-muted-foreground">
              No units yet.{isAdmin ? " Add the first one above." : ""}
            </div>
          )}
          {treeQuery.data?.map((node) => (
            <TreeNode
              key={node.id}
              node={node}
              depth={0}
              selectedId={selectedId}
              typeLabel={typeLabel}
              canEdit={isAdmin}
              onSelect={selectUnit}
              onAddChild={openAddForm}
              onToggleArchive={toggleArchive}
            />
          ))}
        </div>

        <div className="rounded-xl border border-border bg-card shadow-sm p-4">
          {!selected && (
            <p className="text-sm text-muted-foreground">
              Select a unit to see its details.
            </p>
          )}
          {selected && !editing && (
            <div>
              <dl className="space-y-3 text-sm">
                <Detail label="Name" value={selected.name} />
                <Detail label="Type" value={typeLabel(selected.type_code)} />
                <Detail label="Location" value={selected.location ?? "—"} />
                <Detail label="Department" value={selected.department ?? "—"} />
                <Detail label="Status" value={selected.status} />
                <Detail
                  label="Parent"
                  value={
                    rows.find((r) => r.node.id === selected.parent_id)?.node.name ??
                    "— (top level)"
                  }
                />
              </dl>
              {isAdmin && (
                <div className="mt-4 flex flex-wrap gap-2 border-t border-border pt-3">
                  <button
                    onClick={() => openAddForm(selected.id)}
                    className="rounded-lg border border-border px-2.5 py-1 text-xs text-secondary hover:bg-muted"
                  >
                    + Add child unit
                  </button>
                  <button
                    onClick={() => setEditing(true)}
                    className="rounded-lg border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => toggleArchive(selected)}
                    className="rounded-lg border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted"
                  >
                    {selected.status === "archived" ? "Reactivate" : "Archive"}
                  </button>
                  {updateUnit.error instanceof ApiError && (
                    <span className="self-center text-xs text-destructive">
                      {updateUnit.error.message}
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
          {selected && editing && typesQuery.data && (
            <UnitEditForm
              key={selected.id}
              unit={selected}
              types={typesQuery.data}
              units={rows.map((r) => r.node).filter((u) => u.id !== selected.id)}
              pending={updateUnit.isPending}
              error={updateUnit.error}
              onSubmit={(body) => updateUnit.mutate({ id: selected.id, body })}
              onCancel={() => setEditing(false)}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function TreeNode({
  node,
  depth,
  selectedId,
  typeLabel,
  canEdit,
  onSelect,
  onAddChild,
  onToggleArchive,
}: {
  node: OrgUnitNode;
  depth: number;
  selectedId: number | null;
  typeLabel: (code: string) => string;
  canEdit: boolean;
  onSelect: (id: number) => void;
  onAddChild: (parentId: number) => void;
  onToggleArchive: (unit: OrgUnit) => void;
}) {
  const isSelected = selectedId === node.id;
  return (
    <div>
      <div
        className={`group flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm transition-colors ${
          isSelected ? "bg-primary/10" : "hover:bg-muted"
        }`}
      >
        <button
          onClick={() => onSelect(node.id)}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <span
            className={`h-1.5 w-1.5 shrink-0 rounded-full ${DEPTH_DOT[depth % DEPTH_DOT.length]}`}
          />
          <span className="truncate font-medium text-foreground">{node.name}</span>
          <Badge tone="neutral">{typeLabel(node.type_code)}</Badge>
          {node.status === "archived" && <Badge tone="warn">archived</Badge>}
        </button>
        {canEdit && (
          <span className="hidden shrink-0 items-center gap-0.5 group-hover:flex">
            <button
              title="Add child unit"
              onClick={() => onAddChild(node.id)}
              className="rounded-md px-1.5 py-0.5 text-xs font-semibold text-secondary hover:bg-card"
            >
              +
            </button>
            <button
              title={node.status === "archived" ? "Reactivate" : "Archive"}
              onClick={() => onToggleArchive(node)}
              className="rounded-md px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-card hover:text-destructive"
            >
              {node.status === "archived" ? "↺" : "✕"}
            </button>
          </span>
        )}
      </div>
      {node.children.length > 0 && (
        <div className="ml-2.5 border-l border-border pl-2.5">
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              typeLabel={typeLabel}
              canEdit={canEdit}
              onSelect={onSelect}
              onAddChild={onAddChild}
              onToggleArchive={onToggleArchive}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function UnitEditForm({
  unit,
  types,
  units,
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  unit: OrgUnit;
  types: UnitType[];
  units: OrgUnit[];
  pending: boolean;
  error: unknown;
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
      <label className="block">
        <span className="mb-1 block font-medium text-foreground">Location</span>
        <input className={input} value={location} onChange={(e) => setLocation(e.target.value)} />
      </label>
      <label className="block">
        <span className="mb-1 block font-medium text-foreground">Department</span>
        <input
          className={input}
          value={department}
          onChange={(e) => setDepartment(e.target.value)}
        />
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
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium text-foreground">{value}</dd>
    </div>
  );
}

function UnitForm({
  types,
  units,
  initialParentId,
  pending,
  error,
  onSubmit,
}: {
  types: UnitType[];
  units: OrgUnit[];
  initialParentId: number | null;
  pending: boolean;
  error: unknown;
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
      className="fade-in-up mt-4 grid gap-3 rounded-xl border border-border bg-card shadow-sm p-4 sm:grid-cols-2"
    >
      {parentUnit && (
        <p className="text-xs text-muted-foreground sm:col-span-2">
          Adding a unit under <span className="font-medium text-foreground">{parentUnit.name}</span>.
        </p>
      )}
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
        <span className="mb-1 block font-medium text-foreground">Type</span>
        <select
          className={input}
          value={typeCode}
          onChange={(e) => setTypeCode(e.target.value)}
        >
          {types.map((t) => (
            <option key={t.code} value={t.code}>
              {t.label}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Parent unit</span>
        <select
          className={input}
          value={parentId}
          onChange={(e) => setParentId(e.target.value)}
        >
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
        <input
          className={input}
          value={location}
          onChange={(e) => setLocation(e.target.value)}
        />
      </label>
      <div className="sm:col-span-2">
        {error instanceof ApiError && (
          <p className="mb-2 text-sm text-destructive">{error.message}</p>
        )}
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
