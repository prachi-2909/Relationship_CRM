export type Role = "admin" | "relationship_manager" | "approver_viewer";
export type UserStatus = "active" | "disabled";

export interface User {
  id: number;
  name: string;
  email: string;
  role: Role;
  status: UserStatus;
}

export const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin",
  relationship_manager: "Relationship Manager",
  approver_viewer: "Approver / Viewer",
};

// --- organisation ---------------------------------------------------------

export type UnitStatus = "active" | "archived";

export interface UnitType {
  code: string;
  label: string;
  rank: number;
  active: boolean;
}

export interface OrgUnit {
  id: number;
  name: string;
  type_code: string;
  parent_id: number | null;
  location: string | null;
  department: string | null;
  status: UnitStatus;
  metadata: Record<string, unknown> | null;
}

export interface OrgUnitNode extends OrgUnit {
  children: OrgUnitNode[];
}

// --- officials ----------------------------------------------------------

export type OfficialStatus = "active" | "archived";
export type VerificationStatus =
  | "unverified"
  | "partially_verified"
  | "verified";
export type FieldVerification = "unverified" | "verified";

export const PROVENANCED_FIELDS = [
  "designation",
  "department",
  "level",
  "location",
  "organization_unit_id",
] as const;
export type ProvenancedField = (typeof PROVENANCED_FIELDS)[number];

export const FIELD_LABELS: Record<ProvenancedField, string> = {
  designation: "Designation",
  department: "Department",
  level: "Level",
  location: "Location",
  organization_unit_id: "Organisation unit",
};

export interface FieldProvenance {
  field: string;
  source: string;
  confidence: number | null;
  note: string | null;
  verification_status: FieldVerification;
  verified_by: number | null;
  verified_at: string | null;
  updated_at: string;
}

export interface OfficialSummary {
  id: number;
  name: string;
  designation: string | null;
  level: string | null;
  location: string | null;
  organization_unit_id: number | null;
  status: OfficialStatus;
  verification_status: VerificationStatus;
}

export interface OfficialDetail extends OfficialSummary {
  department: string | null;
  fields: Record<string, FieldProvenance>;
}

export interface OfficialListResponse {
  items: OfficialSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface TimelineEntry {
  action: string;
  entity_type: string;
  at: string;
  actor_id: number | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export const VERIFICATION_LABELS: Record<VerificationStatus, string> = {
  unverified: "Unverified",
  partially_verified: "Partly verified",
  verified: "Verified",
};

// --- relationships ------------------------------------------------------

export type RelationshipStatus =
  | "new"
  | "developing"
  | "active"
  | "strong"
  | "strategic"
  | "declining"
  | "at_risk"
  | "inactive";
export type Importance = "routine" | "important" | "strategic";
export type RiskLevel = "low" | "medium" | "high";

export const RELATIONSHIP_STATUSES: RelationshipStatus[] = [
  "new",
  "developing",
  "active",
  "strong",
  "strategic",
  "declining",
  "at_risk",
  "inactive",
];
export const IMPORTANCE_VALUES: Importance[] = ["routine", "important", "strategic"];

export interface OfficialRef {
  id: number;
  name: string;
  designation: string | null;
  level: string | null;
  organization_unit_id: number | null;
}

export interface RelationshipSummary {
  id: number;
  official_id: number;
  official_name: string;
  official_level: string | null;
  owner_id: number | null;
  status: RelationshipStatus;
  importance: Importance;
  risk_level: RiskLevel;
  score: number;
  last_interaction_at: string | null;
  next_action_at: string | null;
}

export interface RelationshipDetail extends RelationshipSummary {
  official: OfficialRef;
  score_components: Record<string, unknown> | null;
}

export interface RelationshipListResponse {
  items: RelationshipSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface ScoreHistoryEntry {
  score: number;
  components: Record<string, unknown>;
  weights_version: string;
  reason: string | null;
  computed_at: string;
}

export const SCORE_BANDS: { min: number; label: string; risk: RiskLevel }[] = [
  { min: 80, label: "Strong", risk: "low" },
  { min: 60, label: "Healthy", risk: "low" },
  { min: 40, label: "Attention", risk: "medium" },
  { min: 0, label: "At risk", risk: "high" },
];

// --- interactions -----------------------------------------------------

export type InteractionType = "email" | "call" | "meeting" | "note";
export type Direction = "inbound" | "outbound" | "internal";
export type Sentiment = "positive" | "neutral" | "negative" | "unknown";

export const INTERACTION_TYPES: InteractionType[] = ["email", "call", "meeting", "note"];
export const DIRECTIONS: Direction[] = ["inbound", "outbound", "internal"];

export interface InteractionStructured {
  topics?: string[];
  commitments?: string[];
  requests?: string[];
  people?: string[];
}

export interface InteractionSummary {
  id: number;
  relationship_id: number;
  official_id: number;
  type: InteractionType;
  direction: Direction;
  occurred_at: string;
  channel: string | null;
  sentiment: Sentiment;
  ai_summary: string | null;
}

export interface InteractionDetail extends InteractionSummary {
  raw_notes: string;
  ai_structured: InteractionStructured | null;
  ai_model: string | null;
  structured: InteractionStructured | null;
  created_by: number | null;
  created_at: string;
}

export interface InteractionListResponse {
  items: InteractionSummary[];
  total: number;
  limit: number;
  offset: number;
}

export const SENTIMENT_TONE: Record<
  Sentiment,
  "good" | "warn" | "danger" | "neutral"
> = {
  positive: "good",
  neutral: "neutral",
  negative: "danger",
  unknown: "neutral",
};

// --- tasks -----------------------------------------------------------

export type TaskStatus = "open" | "done" | "cancelled";

export interface Task {
  id: number;
  relationship_id: number;
  official_id: number;
  official_name: string;
  title: string;
  detail: string | null;
  due_at: string | null;
  status: TaskStatus;
  assigned_to: number | null;
  source_interaction_id: number | null;
  completed_at: string | null;
  escalated_at: string | null;
  created_at: string;
}

export interface TaskListResponse {
  items: Task[];
  total: number;
  limit: number;
  offset: number;
}

export function isOverdue(task: Task): boolean {
  return (
    task.status === "open" && task.due_at !== null && new Date(task.due_at) < new Date()
  );
}

// --- imports ---------------------------------------------------------

export type ImportStatus = "pending" | "committed" | "cancelled";
export type RowAction = "create" | "merge" | "skip";

export interface ImportSummary {
  id: number;
  filename: string;
  status: ImportStatus;
  row_count: number;
  accepted_count: number;
  rejected_count: number;
  committed_at: string | null;
  created_at: string;
}

export interface ImportRow {
  row_number: number;
  raw: Record<string, unknown>;
  normalized: Record<string, string | null>;
  resolved_official_id: number | null;
  action: RowAction;
  confidence: number;
  error: string | null;
}

export interface WorkedSample {
  action: RowAction;
  row_number: number;
  official_name: string;
  writes: Record<string, unknown>;
}

export interface ImportPreview extends ImportSummary {
  rows: ImportRow[];
  samples: WorkedSample[];
}

export const ACTION_TONE: Record<RowAction, "good" | "primary" | "neutral"> = {
  create: "good",
  merge: "primary",
  skip: "neutral",
};

// --- official dates ------------------------------------------------------

export type DateKind = "birthday" | "joined" | "promoted";

export const DATE_KIND_LABELS: Record<DateKind, string> = {
  birthday: "Birthday",
  joined: "Date of joining",
  promoted: "Promotion",
};

export interface OfficialDate {
  id: number;
  kind: DateKind;
  value: string;
  source: string;
  confidence: number | null;
  note: string | null;
  verification_status: FieldVerification;
  verified_by: number | null;
  verified_at: string | null;
}

// --- engagement moments -----------------------------------------------

export type MomentType =
  | "promotion"
  | "birthday"
  | "work_anniversary"
  | "inactivity";
export type MomentStatus =
  | "detected"
  | "draft_ready"
  | "approved"
  | "sent_manually"
  | "dismissed";

export const MOMENT_TYPE_LABELS: Record<MomentType, string> = {
  promotion: "Promotion",
  birthday: "Birthday",
  work_anniversary: "Work anniversary",
  inactivity: "Inactivity",
};

export const MOMENT_STATUS_TONE: Record<
  MomentStatus,
  "neutral" | "primary" | "good" | "warn"
> = {
  detected: "neutral",
  draft_ready: "primary",
  approved: "good",
  sent_manually: "good",
  dismissed: "warn",
};

export interface MomentSummary {
  id: number;
  official_id: number;
  official_name: string;
  relationship_id: number;
  type: MomentType;
  event_date: string | null;
  status: MomentStatus;
  suppressed_reason: string | null;
  created_at: string;
}

export interface MomentDetail extends MomentSummary {
  evidence: Record<string, unknown>;
  draft_text: string | null;
  decided_by: number | null;
  decided_at: string | null;
}

export interface MomentListResponse {
  items: MomentSummary[];
  total: number;
  limit: number;
  offset: number;
}

// --- audit log --------------------------------------------------------

export interface AuditEntry {
  id: number;
  actor_id: number | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  at: string;
}

export interface AuditListResponse {
  items: AuditEntry[];
  total: number;
  limit: number;
  offset: number;
}
