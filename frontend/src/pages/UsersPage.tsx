import { Fragment, type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../components/Badge";
import { Button, Card, inputClass, PageHeader } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { ROLE_LABELS, type Role, type User, type UserStatus } from "../types";

const ROLES: Role[] = ["admin", "relationship_manager", "approver_viewer"];

export function UsersPage() {
  const queryClient = useQueryClient();
  const [addingOpen, setAddingOpen] = useState(false);
  const [resettingId, setResettingId] = useState<number | null>(null);
  const [newPassword, setNewPassword] = useState("");

  const { data, isPending, error } = useQuery({
    queryKey: ["users"],
    queryFn: () => api<User[]>("/users"),
  });

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
                      </div>
                    </td>
                  </tr>
                  {resettingId === user.id && (
                    <tr className="border-t border-border bg-muted/40">
                      <td colSpan={5} className="px-4 py-3">
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
