import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Badge } from "./Badge";
import { ArrowRightIcon, CakeIcon, MailIcon } from "./sectionUi";
import { Card, Spinner } from "./ui";
import { api, ApiError } from "../lib/api";
import type { Csp, CspByRmResponse } from "../types";

function formatDob(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** The shared "SBI Kiosk Operators" (CSP) directory: all active CSPs, searchable by code / name /
 * number and filterable by RM, with their contact, birthday and branch. Used by both the Officials
 * and Relationships sections. */
export function KioskOperators({ onBack }: { onBack: () => void }) {
  const [q, setQ] = useState("");
  const [rmFilter, setRmFilter] = useState("");
  const query = useQuery({
    queryKey: ["csps", "by-rm"],
    queryFn: () => api<CspByRmResponse>("/csps/by-rm"),
  });

  const rmNames = useMemo(
    () => (query.data ? query.data.groups.map((g) => g.rm_name) : []),
    [query.data],
  );
  const all: Csp[] = useMemo(
    () => (query.data ? query.data.groups.flatMap((g) => g.csps) : []),
    [query.data],
  );
  const needle = q.trim().toLowerCase();
  const csps = all.filter((c) => {
    if (rmFilter && c.rm_name !== rmFilter) return false;
    if (!needle) return true;
    return (
      c.csp_id.toLowerCase().includes(needle) ||
      c.name.toLowerCase().includes(needle) ||
      (c.mobile ?? "").includes(needle) ||
      (c.alternate_mobile ?? "").includes(needle)
    );
  });

  return (
    <div>
      <button
        onClick={onBack}
        className="mb-3 rounded-md px-2 py-1 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted"
      >
        &larr; SBI Officials / Kiosk Operators
      </button>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-heading text-xl font-bold text-foreground">SBI Kiosk Operators</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Customer Service Points, searchable by CSP code, name or number.
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search CSP code, name or number…"
          className="w-full max-w-md flex-1 rounded-lg border border-input bg-surface px-3 py-1.5 text-sm outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/25"
        />
        <select
          value={rmFilter}
          onChange={(e) => setRmFilter(e.target.value)}
          className="rounded-lg border border-input bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/25"
        >
          <option value="">All RMs</option>
          {rmNames.map((name) => (
            <option key={name} value={name}>
              RM: {name}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4">
        {query.isPending && <Spinner />}
        {query.error instanceof ApiError && (
          <p className="text-sm text-destructive">{query.error.message}</p>
        )}
        {query.data && (
          <>
            <p className="mb-2 text-xs text-muted-foreground">
              {csps.length} of {all.length} operators
            </p>
            <div className="grid gap-2.5 sm:grid-cols-2">
              {csps.map((c) => {
                const dob = formatDob(c.date_of_birth);
                return (
                  <Card key={c.id} className="p-3.5">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                            {c.csp_id}
                          </span>
                          <Link
                            to={`/kiosk-operators/${c.id}`}
                            className="inline-flex min-w-0 items-center gap-0.5 font-medium text-foreground hover:text-primary hover:underline"
                          >
                            <span className="truncate">{c.name}</span>
                            <ArrowRightIcon className="h-3.5 w-3.5 shrink-0 opacity-60" />
                          </Link>
                          {c.category && <Badge tone="neutral">{c.category}</Badge>}
                        </div>
                        <div className="mt-0.5 text-xs text-muted-foreground">
                          {[c.branch_name, c.district, c.state].filter(Boolean).join(" · ") || "—"}
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                          <span>RM: {c.rm_name}</span>
                          {dob && (
                            <span className="inline-flex items-center gap-1">
                              <CakeIcon className="h-3.5 w-3.5" /> {dob}
                            </span>
                          )}
                          {c.email && (
                            <span className="inline-flex min-w-0 items-center gap-1">
                              <MailIcon className="h-3.5 w-3.5 shrink-0" />
                              <span className="truncate">{c.email}</span>
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="shrink-0 text-right text-sm">
                        {c.mobile ? (
                          <a href={`tel:${c.mobile}`} className="font-medium text-primary hover:underline">
                            {c.mobile}
                          </a>
                        ) : (
                          <span className="text-muted-foreground">no number</span>
                        )}
                        {c.alternate_mobile && (
                          <div className="text-xs text-muted-foreground">alt: {c.alternate_mobile}</div>
                        )}
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
