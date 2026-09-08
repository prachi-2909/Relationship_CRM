import type { ReactNode } from "react";

import type { VerificationStatus } from "../types";
import { VERIFICATION_LABELS } from "../types";

type Tone = "neutral" | "primary" | "good" | "warn" | "danger";

const TONES: Record<Tone, string> = {
  neutral: "bg-muted text-muted-foreground",
  primary: "bg-primary/10 text-secondary",
  good: "bg-accent/10 text-accent",
  warn: "bg-saffron/20 text-[hsl(38_80%_32%)]",
  danger: "bg-destructive/10 text-destructive",
};

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

const VERIFICATION_TONE: Record<VerificationStatus, Tone> = {
  unverified: "warn",
  partially_verified: "primary",
  verified: "good",
};

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  return (
    <Badge tone={VERIFICATION_TONE[status]}>{VERIFICATION_LABELS[status]}</Badge>
  );
}
