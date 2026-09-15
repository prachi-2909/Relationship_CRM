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

export function OrganisationPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isAdmin = user?.role === "admin";
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
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

  const createUnit = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<OrgUnit>("/organization/units", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["units"] });
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
      queryClient.invalidateQueries({ queryKey: ["units"] });
      setEditing(false);
    },
  });

  const selectUnit = (id: number) => {
    setSelectedId(id);
    setEditing(false);
  };

  const typeLabel = (code: string) =>
    typesQuery.data?.find((t) => t.code === code)?.label ?? code;

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-xl font-bold text-foreground">
          Organisation
        </h1>
        {isAdmin && (
          <button
            onClick={() => setShowForm((v) => !v)}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground hover:bg-secondary"
          >
            {showForm ? "Cancel" : "Add unit"}
          </button>
        )}
      </div>

      {showForm && typesQuery.data && (
        <UnitForm
          types={typesQuery.data}
          units={rows.map((r) => r.node)}
          pending={createUnit.isPending}
          error={createUnit.error}
          onSubmit={(body) => createUnit.mutate(body)}
        />
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
          {treeQuery.isPending && (
            <div className="p-4 text-sm text-muted-foreground">Loading…</div>
          )}
          {treeQuery.data && rows.length === 0 && (
            <div className="p-6 text-sm text-muted-foreground">
              No units yet.{isAdmin ? " Add the first one above." : ""}
            </div>
          )}
          {rows.map(({ node, depth }) => (
            <button
              key={node.id}
              onClick={() => selectUnit(node.id)}
              className={`flex w-full items-center gap-2 border-b border-border px-4 py-2 text-left text-sm last:border-b-0 hover:bg-muted ${
                selectedId === node.id ? "bg-primary/10" : ""
              }`}
              style={{ paddingLeft: `${16 + depth * 20}px` }}
            >
              <span className="font-medium text-foreground">{node.name}</span>
              <Badge tone="neutral">{typeLabel(node.type_code)}</Badge>
              {node.status === "archived" && <Badge tone="warn">archived</Badge>}
            </button>
          ))}
        </div>

        <div className="rounded-lg border border-border bg-card shadow-sm p-4">
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
                <div className="mt-4 flex gap-2 border-t border-border pt-3">
                  <button
                    onClick={() => setEditing(true)}
                    className="rounded border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() =>
                      updateUnit.mutate({
                        id: selected.id,
                        body: {
                          status: selected.status === "archived" ? "active" : "archived",
                        },
                      })
                    }
                    className="rounded border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted"
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
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

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
          className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-secondary disabled:opacity-60"
        >
          {pending ? "Saving…" : "Save changes"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted"
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
  pending,
  error,
  onSubmit,
}: {
  types: UnitType[];
  units: OrgUnit[];
  pending: boolean;
  error: unknown;
  onSubmit: (body: Record<string, unknown>) => void;
}) {
  const [name, setName] = useState("");
  const [typeCode, setTypeCode] = useState(types[0]?.code ?? "");
  const [parentId, setParentId] = useState<string>("");
  const [location, setLocation] = useState("");

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
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <form
      onSubmit={submit}
      className="mt-4 grid gap-3 rounded-lg border border-border bg-card shadow-sm p-4 sm:grid-cols-2"
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
          className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-secondary disabled:opacity-60"
        >
          {pending ? "Saving…" : "Create unit"}
        </button>
      </div>
    </form>
  );
}
