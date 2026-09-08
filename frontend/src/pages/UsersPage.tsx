import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { ROLE_LABELS, type User } from "../types";

export function UsersPage() {
  const { data, isPending, error } = useQuery({
    queryKey: ["users"],
    queryFn: () => api<User[]>("/users"),
  });

  return (
    <div>
      <h1 className="font-heading text-xl font-bold text-foreground">Users</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Accounts and roles. Admin only. Create and edit endpoints exist; UI forms
        arrive with the rest of admin in a later pass.
      </p>

      <div className="mt-6 overflow-hidden rounded-lg border border-border bg-card shadow-sm">
        {isPending && (
          <div className="p-4 text-sm text-muted-foreground">Loading…</div>
        )}
        {error && (
          <div className="p-4 text-sm text-destructive">Could not load users.</div>
        )}
        {data && (
          <table className="w-full text-sm">
            <thead className="bg-muted text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Email</th>
                <th className="px-4 py-2 font-medium">Role</th>
                <th className="px-4 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.map((user) => (
                <tr key={user.id} className="border-t border-border">
                  <td className="px-4 py-2">{user.name}</td>
                  <td className="px-4 py-2 text-muted-foreground">{user.email}</td>
                  <td className="px-4 py-2">{ROLE_LABELS[user.role]}</td>
                  <td className="px-4 py-2">
                    <span
                      className={
                        user.status === "active"
                          ? "text-accent"
                          : "text-muted-foreground"
                      }
                    >
                      {user.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
