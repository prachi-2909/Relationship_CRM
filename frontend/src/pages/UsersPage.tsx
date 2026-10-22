import { Fragment, type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../components/Badge";
import { Button, Card, inputClass, PageHeader } from "../components/ui";
import { api, ApiError } from "../lib/api";
import {
  type PresenceStatus,
  ROLE_LABELS,
  type Role,
  type TerritoryOut,
  type UnitSummary,
  type User,
  type UserStatus,
} from "../types";

const ROLES: Role[] = ["admin", "relationship_manager", "approver_viewer", "dc"];

export function UsersPage() {
  const queryClient = useQueryClient();
  const [addingOpen, setAddingOpen] = useState(false);
  const [resettingId, setResettingId] = useState<number | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [territoryId, setTerritoryId] = useState<number | null>(null);

  const { data, isPending, error } = useQuery({
    queryKey: ["users"],
    queryFn: () => api<User[]>("/users"),
  });

  // Refetched every 10s so "who's active" stays close to live without a manual reload.
  const presenceQuery = useQuery({
    queryKey: ["presence-status"],
    queryFn: () => api<PresenceStatus[]>("/presence/status"),
    refetchInterval: 10_000,
  });
  const presenceByUserId = new Map((presenceQuery.data ?? []).map((p) => [p.user_id, p]));

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["users"] });

  const createUser = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<User>("/users", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      invalidate();
      setAddingOpen(false);
    },
  });

  const updateUser = useMutation({
    mutationFn: (vars: { id: number; body: Record<string, unknown> }) =>
      api<User>(`/users/${vars.id}`, { method: "PATCH", body: JSON.stringify(vars.body) }),
    onSuccess: invalidate,
  });

  const resetPassword = useMutation({
    mutationFn: (vars: { id: number; new_password: string }) =>
      api(`/users/${vars.id}/reset-password`, {
        method: "POST",
        body: JSON.stringify({ new_password: vars.new_password }),
      }),
    onSuccess: () => {
      setResettingId(null);
      setNewPassword("");
    },
  });

  const openReset = (id: number) => {
    setResettingId(id);
    setNewPassword("");
    resetPassword.reset();
  };

  return (
    <div>
      <PageHeader
        title="Users"
        description="Accounts and roles. Admin only."
        actions={
          <Button
            size="sm"
            variant={addingOpen ? "secondary" : "gold"}
            onClick={() => setAddingOpen((v) => !v)}
          >
            {addingOpen ? "Cancel" : "Add user"}
          </Button>
        }
      />

      {addingOpen && (
        <NewUserForm
          pending={createUser.isPending}
          error={createUser.error}
          onSubmit={(body) => createUser.mutate(body)}
        />
      )}

      <Card className="mt-6 overflow-hidden">
        {isPending && <div className="p-4 text-sm text-muted-foreground">Loading…</div>}
        {error && <div className="p-4 text-sm text-destructive">Could not load users.</div>}
        {data && (
          <table className="w-full text-sm">
            <thead className="bg-muted text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Email</th>
                <th className="px-4 py-2 font-medium">Role</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Activity</th>
                <th className="px-4 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.map((user) => (
                <Fragment key={user.id}>
                  <tr className="border-t border-border align-top">
                    <td className="px-4 py-2">{user.name}</td>
                    <td className="px-4 py-2 text-muted-foreground">{user.email}</td>
                    <td className="px-4 py-2">
                      <select
                        className="rounded-md border border-input bg-surface px-2 py-1 text-xs"
                        value={user.role}
                        onChange={(e) =>
                          updateUser.mutate({ id: user.id, body: { role: e.target.value } })
                        }
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {ROLE_LABELS[r]}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-2">
                      <Badge tone={user.status === "active" ? "good" : "neutral"}>
                        {user.status}
                      </Badge>
                    </td>
                    <td className="px-4 py-2">
                      <ActivityBadge presence={presenceByUserId.get(user.id)} />
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex flex-wrap gap-2">
                        <button
                          onClick={() =>
                            updateUser.mutate({
                              id: user.id,
                              body: {
                                status: (
                                  user.status === "active" ? "disabled" : "active"
                                ) satisfies UserStatus,
                              },
                            })
                          }
                          className="rounded border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                        >
                          {user.status === "active" ? "Deactivate" : "Activate"}
                        </button>
                        <button
                          onClick={() =>
                            resettingId === user.id ? setResettingId(null) : openReset(user.id)
                          }
                          className="rounded border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                        >
                          Reset password
                        </button>
                        {user.role === "dc" && (
                          <button
                            onClick={() =>
                              setTerritoryId(territoryId === user.id ? null : user.id)
                            }
                            className="rounded border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                          >
                            Territory
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {territoryId === user.id && (
                    <tr className="border-t border-border bg-muted/40">
                      <td colSpan={6} className="px-4 py-3">
                        <TerritoryManager dcUserId={user.id} dcName={user.name} />
                      </td>
                    </tr>
                  )}
                  {resettingId === user.id && (
                    <tr className="border-t border-border bg-muted/40">
                      <td colSpan={6} className="px-4 py-3">
                        <form
                          onSubmit={(e: FormEvent) => {
                            e.preventDefault();
                            if (newPassword.length >= 8) {
                              resetPassword.mutate({ id: user.id, new_password: newPassword });
                            }
                          }}
                          className="flex flex-wrap items-center gap-2"
                        >
                          <span className="text-xs text-muted-foreground">
                            New password for {user.email}:
                          </span>
                          <input
                            type="password"
                            autoFocus
                            minLength={8}
                            required
                            className={`${inputClass} w-56`}
                            placeholder="at least 8 characters"
                            value={newPassword}
                            onChange={(e) => setNewPassword(e.target.value)}
                          />
                          <Button type="submit" size="sm" disabled={resetPassword.isPending}>
                            {resetPassword.isPending ? "Setting…" : "Set password"}
                          </Button>
                          <button
                            type="button"
                            onClick={() => setResettingId(null)}
                            className="text-xs text-muted-foreground hover:underline"
                          >
                            Cancel
                          </button>
                          {resetPassword.error instanceof ApiError && (
                            <span className="text-xs text-destructive">
                              {resetPassword.error.message}
                            </span>
                          )}
                        </form>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

function ActivityBadge({ presence }: { presence: PresenceStatus | undefined }) {
  if (!presence || !presence.is_logged_in) {
    return <Badge tone="neutral">Not logged in</Badge>;
  }
  if (presence.is_online) {
    return <Badge tone="good">● Active now</Badge>;
  }
  return <Badge tone="warn">Logged in, not active</Badge>;
}

function NewUserForm({
  pending,
  error,
  onSubmit,
}: {
  pending: boolean;
  error: unknown;
  onSubmit: (body: Record<string, unknown>) => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("relationship_manager");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit({ name, email, password, role });
  };

  return (
    <form
      onSubmit={submit}
      className="mt-4 grid gap-3 rounded-lg border border-border bg-card p-4 shadow-sm sm:grid-cols-4"
    >
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Name</span>
        <input className={inputClass} required value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Email</span>
        <input
          type="email"
          className={inputClass}
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Password</span>
        <input
          type="password"
          minLength={8}
          className={inputClass}
          required
          placeholder="at least 8 characters"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium text-foreground">Role</span>
        <select
          className={inputClass}
          value={role}
          onChange={(e) => setRole(e.target.value as Role)}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABELS[r]}
            </option>
          ))}
        </select>
      </label>
      <div className="flex items-end gap-3 sm:col-span-4">
        <Button type="submit" size="sm" disabled={pending}>
          {pending ? "Creating…" : "Create user"}
        </Button>
        {error instanceof ApiError && (
          <span className="text-sm text-destructive">{error.message}</span>
        )}
      </div>
    </form>
  );
}

function TerritoryManager({ dcUserId, dcName }: { dcUserId: number; dcName: string }) {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");

  const territoryQuery = useQuery({
    queryKey: ["dc-territories", dcUserId],
    queryFn: () => api<TerritoryOut[]>(`/dc-territories?dc_user_id=${dcUserId}`),
  });
  const searchQuery = useQuery({
    queryKey: ["units", "picker", query],
    queryFn: () => api<UnitSummary[]>(`/organization/units?q=${encodeURIComponent(query)}&status=active`),
    enabled: query.trim().length >= 2,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["dc-territories", dcUserId] });

  const assign = useMutation({
    mutationFn: (organization_unit_id: number) =>
      api<TerritoryOut>("/dc-territories", {
        method: "POST",
        body: JSON.stringify({ dc_user_id: dcUserId, organization_unit_id }),
      }),
    onSuccess: () => {
      invalidate();
      setQuery("");
    },
  });
  const remove = useMutation({
    mutationFn: (territoryId: number) =>
      api(`/dc-territories/${territoryId}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  return (
    <div className="space-y-3">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {dcName}'s territory — officials search on this DC's app is limited to these units and everything under them
      </div>

      {territoryQuery.data && territoryQuery.data.length === 0 && (
        <p className="text-sm text-muted-foreground">No territory assigned yet — this DC sees no officials.</p>
      )}
      {territoryQuery.data && territoryQuery.data.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {territoryQuery.data.map((t) => (
            <span
              key={t.id}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-xs"
            >
              <Badge tone="neutral">{t.organization_unit_type}</Badge>
              {t.organization_unit_name}
              <button
                onClick={() => remove.mutate(t.id)}
                className="text-muted-foreground hover:text-destructive"
                title="Remove"
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="relative flex max-w-sm items-center gap-2">
        <input
          className={inputClass}
          placeholder="Search a unit to add (e.g. an AO, RBO, or Branch)…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {searchQuery.data && searchQuery.data.length > 0 && (
          <ul className="absolute top-full z-10 mt-1 w-full overflow-hidden rounded-lg border border-border bg-card shadow-md">
            {searchQuery.data.map((u) => (
              <li key={u.id}>
                <button
                  onClick={() => assign.mutate(u.id)}
                  className="flex w-full items-center justify-between gap-2 px-2.5 py-1.5 text-left text-sm hover:bg-muted"
                >
                  <span>{u.name}</span>
                  <Badge tone="neutral">{u.type_code}</Badge>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {(assign.error instanceof ApiError || remove.error instanceof ApiError) && (
        <p className="text-xs text-destructive">
          {(assign.error as ApiError)?.message ?? (remove.error as ApiError)?.message}
        </p>
      )}
    </div>
  );
}
