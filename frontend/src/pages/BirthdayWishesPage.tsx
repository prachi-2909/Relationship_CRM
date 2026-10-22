import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { Badge } from "../components/Badge";
import { CakeIcon, MailIcon } from "../components/sectionUi";
import { Card, PageHeader, Spinner } from "../components/ui";
import { api, ApiError } from "../lib/api";
import type { BirthdayWishDraft, BirthdayWishesPreview } from "../types";

/** Birthday Wishes — see the exact personalised, bilingual (Hindi + English) message that would be
 * sent to each CSP, today and over the coming week. Read-only preview: nothing is ever sent from
 * here; sending stays gated on the Gmail key and the draft-only / enabled switches. */
export function BirthdayWishesPage() {
  // A ?csp=<code> deep-link (e.g. from the dashboard's birthday list) opens that CSP's draft.
  const [params] = useSearchParams();
  const highlight = params.get("csp");
  const { data, isPending, error } = useQuery({
    queryKey: ["birthday-wishes", "preview"],
    queryFn: () => api<BirthdayWishesPreview>("/csps/birthday-wishes/preview"),
  });

  return (
    <div>
      <PageHeader
        title="Birthday Wishes"
        description="The exact personalised, bilingual message each Kiosk Operator would receive — today's and the week ahead. Nothing is sent from here."
      />

      {isPending && <Spinner />}
      {error instanceof ApiError && <p className="text-sm text-destructive">{error.message}</p>}

      {data && (
        <>
          <StatusBanner data={data} />

          <Section
            title="Today"
            hint={`${data.today.length} ${data.today.length === 1 ? "wish" : "wishes"} ready`}
          >
            {data.today.length === 0 ? (
              <Card className="p-6 text-center text-sm text-muted-foreground">
                No CSP has a birthday today.
              </Card>
            ) : (
              data.today.map((d) => (
                <DraftCard
                  key={d.csp_id}
                  draft={d}
                  sendable
                  gmailConfigured={data.gmail_configured}
                  highlight={highlight === d.csp_id}
                />
              ))
            )}
          </Section>

          <Section title="Coming up" hint="Next 30 days">
            {data.upcoming.length === 0 ? (
              <Card className="p-6 text-center text-sm text-muted-foreground">
                No birthdays in the next 30 days.
              </Card>
            ) : (
              data.upcoming.map((d) => (
                <DraftCard key={d.csp_id} draft={d} highlight={highlight === d.csp_id} />
              ))
            )}
          </Section>
        </>
      )}
    </div>
  );
}

function StatusBanner({ data }: { data: BirthdayWishesPreview }) {
  if (!data.gmail_configured) {
    return (
      <div className="mb-5 rounded-lg border border-saffron/40 bg-saffron/10 px-4 py-2.5 text-sm text-[hsl(38_80%_28%)]">
        <span className="font-semibold">Sending is off.</span> The Gmail key isn't set yet — these are
        previews only. Set it to enable the Send button.
      </div>
    );
  }
  return (
    <div className="mb-5 rounded-lg border border-[hsl(155_45%_40%)]/30 bg-[hsl(155_45%_40%)]/10 px-4 py-2.5 text-sm text-[hsl(155_45%_28%)]">
      <span className="font-semibold">Gmail connected.</span> Use <span className="font-medium">Send now</span>{" "}
      on a card to send that wish immediately. Automatic daily sending is still off — it will be turned
      on after deployment.
    </div>
  );
}

function Section({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <h2 className="mb-2 flex items-baseline gap-2">
        <span className="font-heading text-base font-semibold text-foreground">{title}</span>
        <span className="text-xs text-muted-foreground">{hint}</span>
      </h2>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function DraftCard({
  draft,
  sendable = false,
  gmailConfigured = false,
  highlight = false,
}: {
  draft: BirthdayWishDraft;
  sendable?: boolean;
  gmailConfigured?: boolean;
  highlight?: boolean;
}) {
  const [open, setOpen] = useState(sendable || highlight);
  const [hi, en] = splitBilingual(draft.message);
  const ref = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const [sent, setSent] = useState(draft.already_sent);

  const send = useMutation({
    mutationFn: () =>
      api<{ ok: boolean; sent_to: string }>(`/csps/${draft.id}/birthday-wish`, { method: "POST" }),
    onSuccess: () => {
      setSent(true);
      queryClient.invalidateQueries({ queryKey: ["dashboard", "overview"] });
    },
  });

  useEffect(() => {
    if (highlight && ref.current) {
      setOpen(true);
      ref.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [highlight]);

  return (
    <Card
      id={`csp-${draft.csp_id}`}
      className={`overflow-hidden ${highlight ? "ring-2 ring-[#DB2777]/50" : ""}`}
    >
      <div ref={ref} />
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 p-3.5 text-left"
      >
        <span
          className={`grid h-10 w-10 shrink-0 place-items-center rounded-full text-xs font-bold tabular-nums ${
            draft.in_days === 0 ? "bg-[#DB2777] text-white" : "bg-[#DB2777]/10 text-[#DB2777]"
          }`}
        >
          {draft.in_days === 0 ? <CakeIcon className="h-5 w-5" /> : `${draft.in_days}d`}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-foreground">{draft.name}</span>
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
              {draft.csp_id}
            </span>
            <Badge tone="neutral">{draft.generated_by === "template" ? "template" : "AI"}</Badge>
          </span>
          <span className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
            <span>RM {draft.rm_name}</span>
            {draft.email ? (
              <span className="inline-flex min-w-0 items-center gap-1">
                <MailIcon className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{draft.email}</span>
              </span>
            ) : (
              <span className="text-destructive">no email on file</span>
            )}
          </span>
        </span>
        <span className="shrink-0 text-xs text-muted-foreground">{open ? "Hide" : "Preview"}</span>
      </button>

      {open && (
        <div className="border-t border-border bg-muted/30 p-3.5">
          <div className="mb-1 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Subject:</span> {draft.subject}
          </div>
          <div className="mb-2 text-[11px] text-muted-foreground/80">
            The email template adds the <span className="font-medium">Hi {"{name}"},</span> greeting at
            the top and the Eko sign-off at the bottom automatically.
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-border bg-card p-3">
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                हिंदी
              </div>
              <p className="whitespace-pre-wrap text-sm text-foreground">{hi}</p>
            </div>
            <div className="rounded-lg border border-border bg-card p-3">
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                English
              </div>
              <p className="whitespace-pre-wrap text-sm text-foreground">{en}</p>
            </div>
          </div>
          {sendable && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {sent ? (
                <span className="inline-flex items-center gap-1.5 rounded-lg bg-[hsl(155_45%_40%)]/10 px-3 py-1.5 text-sm font-medium text-[hsl(155_45%_28%)]">
                  <CheckIcon className="h-4 w-4" /> Sent
                </span>
              ) : (
                <button
                  onClick={() => send.mutate()}
                  disabled={!gmailConfigured || !draft.email || send.isPending}
                  title={
                    !gmailConfigured
                      ? "Gmail key not set"
                      : !draft.email
                        ? "This CSP has no email on file"
                        : "Send this birthday wish now"
                  }
                  className="rounded-lg bg-primary px-4 py-1.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {send.isPending ? "Sending…" : "Send now"}
                </button>
              )}
              {send.error instanceof ApiError && (
                <span className="text-xs text-destructive">{send.error.message}</span>
              )}
              {!sent && !gmailConfigured && (
                <span className="text-xs text-muted-foreground">Set the Gmail key to enable.</span>
              )}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={2.5}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 10.5l4 4 8-9" />
    </svg>
  );
}

/** The backend joins the Hindi and English halves with a divider; split them back for a side-by-side
 * view. Greeting and sign-off are NOT in the message - the email template adds those. Falls back to
 * one block if the divider moves. */
function splitBilingual(message: string): [string, string] {
  const parts = message.split("───────────────");
  if (parts.length < 2) return [message.trim(), ""];
  return [parts[0].trim(), parts[1].trim()];
}
