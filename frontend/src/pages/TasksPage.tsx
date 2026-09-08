import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Badge } from "../components/Badge";
import { useAuth } from "../auth/AuthProvider";
import { api, ApiError } from "../lib/api";
import {
  isOverdue,
  type Task,
  type TaskListResponse,
  type TaskStatus,
} from "../types";

export function TasksPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canEdit = user?.role === "admin" || user?.role === "relationship_manager";

  const [mine, setMine] = useState(false);
  const [status, setStatus] = useState<TaskStatus | "">("open");
  const [overdueOnly, setOverdueOnly] = useState(false);

  const params = new URLSearchParams({ sort: "due_at", limit: "100" });
  if (mine) params.set("mine", "true");
  if (status) params.set("status", status);
  if (overdueOnly) params.set("overdue", "true");

  const query = useQuery({
    queryKey: ["tasks", mine, status, overdueOnly],
    queryFn: () => api<TaskListResponse>(`/tasks?${params}`),
  });

  const toggle = useMutation({
    mutationFn: (vars: { id: number; status: TaskStatus }) =>
      api(`/tasks/${vars.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: vars.status }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["relationship"] });
    },
  });

  const data = query.data;
  const control =
    "rounded-md border border-input bg-background px-3 py-1.5 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <div>
      <h1 className="font-heading text-xl font-bold text-foreground">Follow-ups</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Commitments and reminders across relationships. Overdue open items are
        escalated by the nightly sweep.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />
          Assigned to me
        </label>
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={overdueOnly}
            onChange={(e) => setOverdueOnly(e.target.checked)}
          />
          Overdue only
        </label>
        <select
          className={control}
          value={status}
          onChange={(e) => setStatus(e.target.value as TaskStatus | "")}
        >
          <option value="">Any status</option>
          <option value="open">Open</option>
          <option value="done">Done</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </div>

      <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card shadow-sm">
        {query.isPending && (
          <div className="p-4 text-sm text-muted-foreground">Loading…</div>
        )}
        {data && data.items.length === 0 && (
          <div className="p-6 text-sm text-muted-foreground">No follow-ups.</div>
        )}
        {data?.items.map((task) => (
          <TaskRow
            key={task.id}
            task={task}
            canEdit={canEdit}
            onToggle={(next) => toggle.mutate({ id: task.id, status: next })}
          />
        ))}
      </div>
    </div>
  );
}

function TaskRow({
  task,
  canEdit,
  onToggle,
}: {
  task: Task;
  canEdit: boolean;
  onToggle: (next: TaskStatus) => void;
}) {
  const overdue = isOverdue(task);
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3 text-sm last:border-b-0">
      <div className="flex items-start gap-3">
        {canEdit && (
          <input
            type="checkbox"
            className="mt-0.5"
            checked={task.status === "done"}
            onChange={(e) => onToggle(e.target.checked ? "done" : "open")}
          />
        )}
        <div>
          <div
            className={
              task.status === "done"
                ? "font-medium text-muted-foreground line-through"
                : "font-medium text-foreground"
            }
          >
            {task.title}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Link
              to={`/relationships/${task.relationship_id}`}
              className="text-secondary hover:underline"
            >
              {task.official_name}
            </Link>
            {task.due_at && <span>due {new Date(task.due_at).toLocaleDateString()}</span>}
            {overdue && <Badge tone="danger">overdue</Badge>}
            {task.escalated_at && <Badge tone="warn">escalated</Badge>}
          </div>
        </div>
      </div>
    </div>
  );
}

export function AddTaskForm({
  relationshipId,
  presetTitle,
  sourceInteractionId,
  onDone,
}: {
  relationshipId: number;
  presetTitle?: string;
  sourceInteractionId?: number;
  onDone: () => void;
}) {
  const [title, setTitle] = useState(presetTitle ?? "");
  const [dueAt, setDueAt] = useState("");

  const create = useMutation({
    mutationFn: () =>
      api("/tasks", {
        method: "POST",
        body: JSON.stringify({
          relationship_id: relationshipId,
          title,
          due_at: dueAt ? new Date(dueAt).toISOString() : null,
          source_interaction_id: sourceInteractionId ?? null,
        }),
      }),
    onSuccess: () => {
      setTitle("");
      setDueAt("");
      onDone();
    },
  });

  const field =
    "rounded-md border border-input bg-background px-2 py-1 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";

  return (
    <form
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        create.mutate();
      }}
      className="flex flex-wrap items-center gap-2"
    >
      <input
        className={`${field} min-w-[14rem] flex-1`}
        required
        placeholder="Follow-up title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <input
        type="date"
        className={field}
        value={dueAt}
        onChange={(e) => setDueAt(e.target.value)}
      />
      <button
        type="submit"
        disabled={create.isPending}
        className="rounded-md bg-primary px-3 py-1 text-sm font-semibold text-primary-foreground hover:bg-secondary disabled:opacity-60"
      >
        Add
      </button>
      {create.error instanceof ApiError && (
        <span className="text-xs text-destructive">{create.error.message}</span>
      )}
    </form>
  );
}
