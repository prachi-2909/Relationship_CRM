import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../components/Badge";
import { useAuth } from "../auth/AuthProvider";
import { api, ApiError } from "../lib/api";
import {
  ACTION_TONE,
  type ImportPreview,
  type ImportSummary,
} from "../types";

const SAMPLE_CSV =
  "Name,Level,Designation,Department,Location,Email\n" +
  "Ashok Nair,AGM,Assistant General Manager,Partnerships,Mumbai,ashok.nair@partner.example\n";

export function ImportPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const canUpload = isAdmin || user?.role === "relationship_manager";
  const queryClient = useQueryClient();

  const [filename, setFilename] = useState("officials.csv");
  const [csvText, setCsvText] = useState("");
  const [activeId, setActiveId] = useState<number | null>(null);

  const listQuery = useQuery({
    queryKey: ["imports"],
    queryFn: () => api<ImportSummary[]>("/imports"),
  });
  const previewQuery = useQuery({
    queryKey: ["import", activeId],
    queryFn: () => api<ImportPreview>(`/imports/${activeId}/preview`),
    enabled: activeId !== null,
  });

  const stage = useMutation({
    mutationFn: () =>
      api<ImportSummary>("/imports", {
        method: "POST",
        body: JSON.stringify({ filename, csv_text: csvText }),
      }),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["imports"] });
      setActiveId(created.id);
      setCsvText("");
    },
  });

  const commit = useMutation({
    mutationFn: (id: number) => api(`/imports/${id}/commit`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["imports"] });
      queryClient.invalidateQueries({ queryKey: ["import", activeId] });
      queryClient.invalidateQueries({ queryKey: ["officials"] });
    },
  });
  const cancel = useMutation({
    mutationFn: (id: number) => api(`/imports/${id}/cancel`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["imports"] });
      queryClient.invalidateQueries({ queryKey: ["import", activeId] });
    },
  });

  const field =
    "rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30";
  const preview = previewQuery.data;

  return (
    <div>
      <h1 className="font-heading text-xl font-bold text-foreground">Data Ingestion</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Paste CSV of officials. It is validated and resolved against existing
        records; nothing is written until an admin commits.
      </p>

      {canUpload && (
        <div className="mt-4 rounded-lg border border-border bg-card shadow-sm p-4">
          <input
            className={`${field} mb-2 w-64`}
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
          />
          <textarea
            className={`${field} w-full font-mono text-xs`}
            rows={6}
            placeholder={SAMPLE_CSV}
            value={csvText}
            onChange={(e) => setCsvText(e.target.value)}
          />
          <div className="mt-2 flex items-center gap-3">
            <button
              disabled={!csvText.trim() || stage.isPending}
              onClick={() => stage.mutate()}
              className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-secondary disabled:opacity-50"
            >
              {stage.isPending ? "Staging…" : "Stage import"}
            </button>
            <button
              type="button"
              onClick={() => setCsvText(SAMPLE_CSV)}
              className="text-xs text-muted-foreground hover:underline"
            >
              Use example
            </button>
            {stage.error instanceof ApiError && (
              <span className="text-sm text-destructive">{stage.error.message}</span>
            )}
          </div>
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_2fr]">
        <div className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
          <div className="border-b border-border px-4 py-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Recent imports
          </div>
          {listQuery.data?.length === 0 && (
            <div className="p-4 text-sm text-muted-foreground">None yet.</div>
          )}
          {listQuery.data?.map((imp) => (
            <button
              key={imp.id}
              onClick={() => setActiveId(imp.id)}
              className={`block w-full border-b border-border px-4 py-2 text-left text-sm last:border-b-0 hover:bg-muted ${
                activeId === imp.id ? "bg-primary/10" : ""
              }`}
            >
              <div className="font-medium text-foreground">{imp.filename}</div>
              <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                <span>{imp.status}</span>
                <span>
                  {imp.accepted_count} ok · {imp.rejected_count} skipped
                </span>
              </div>
            </button>
          ))}
        </div>

        <div>
          {!preview && (
            <p className="text-sm text-muted-foreground">
              Select an import to review its rows.
            </p>
          )}
          {preview && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-sm font-medium text-foreground">
                  {preview.filename}
                </span>
                <Badge tone="neutral">{preview.status}</Badge>
                <span className="text-sm text-muted-foreground">
                  {preview.accepted_count} to apply · {preview.rejected_count} skipped
                </span>
                {preview.status === "pending" && isAdmin && (
                  <>
                    <button
                      onClick={() => commit.mutate(preview.id)}
                      disabled={commit.isPending}
                      className="rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground hover:bg-secondary disabled:opacity-60"
                    >
                      {commit.isPending ? "Committing…" : "Commit"}
                    </button>
                    <button
                      onClick={() => cancel.mutate(preview.id)}
                      className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted"
                    >
                      Cancel
                    </button>
                  </>
                )}
              </div>

              {preview.samples.length > 0 && (
                <div className="rounded-lg border border-border bg-card shadow-sm p-3 text-sm">
                  <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Worked sample — what commit will write
                  </div>
                  {preview.samples.map((s) => (
                    <div key={s.row_number} className="mb-2 last:mb-0">
                      <Badge tone={ACTION_TONE[s.action]}>{s.action}</Badge>{" "}
                      <span className="font-medium text-foreground">
                        {s.official_name}
                      </span>
                      <div className="ml-1 mt-1 text-xs text-muted-foreground">
                        {Object.keys(s.writes).length === 0
                          ? "no field changes"
                          : Object.entries(s.writes)
                              .map(([k, v]) => `${k} = ${String(v)}`)
                              .join("  ·  ")}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="overflow-x-auto rounded-lg border border-border bg-card shadow-sm">
                <table className="w-full text-sm">
                  <thead className="bg-muted text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 font-medium">#</th>
                      <th className="px-3 py-2 font-medium">Name</th>
                      <th className="px-3 py-2 font-medium">Action</th>
                      <th className="px-3 py-2 font-medium">Confidence</th>
                      <th className="px-3 py-2 font-medium">Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((r) => (
                      <tr key={r.row_number} className="border-t border-border">
                        <td className="px-3 py-2 text-muted-foreground">{r.row_number}</td>
                        <td className="px-3 py-2">{r.normalized.name ?? "—"}</td>
                        <td className="px-3 py-2">
                          <Badge tone={ACTION_TONE[r.action]}>{r.action}</Badge>
                        </td>
                        <td className="px-3 py-2 tabular-nums">{r.confidence}</td>
                        <td className="px-3 py-2 text-xs text-muted-foreground">
                          {r.error ?? ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
