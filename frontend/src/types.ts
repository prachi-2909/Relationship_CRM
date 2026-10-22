export type Role = "admin" | "relationship_manager" | "approver_viewer" | "dc";
export type UserStatus = "active" | "disabled";

export interface User {
  id: number;
  name: string;
  email: string;
  role: Role;
  status: UserStatus;
}

export interface PresenceStatus {
  user_id: number;
  name: string;
  email: string;
  role: Role;
  is_logged_in: boolean;
  is_online: boolean;
  last_active_at: string | null;
}

export const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin",
  relationship_manager: "Relationship Manager",
  approver_viewer: "Approver / Viewer",
  dc: "DC",
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

export interface UnitSummary extends OrgUnit {
  child_count: number;
  official_count: number;
}

export interface UnitStats {
  unit_id: number;
  direct_officials: number;
  total_officials: number;
  total_units: number;
}

export interface TerritoryOut {
  id: number;
  dc_user_id: number;
  dc_user_name: string;
  organization_unit_id: number;
  organization_unit_name: string;
  organization_unit_type: string;
  assigned_at: string;
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
  email: string | null;
  phone: string | null;
  designation: string | null;
  level: string | null;
  location: string | null;
  organization_unit_id: number | null;
  organization_unit_name: string | null;
  organization_unit_type: string | null;
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
  actor_name: string | null;
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

export interface RelationshipBrief {
  relationship_id: number;
  official_name: string;
  official_level: string | null;
  unit: string | null;
  owner_id: number | null;
  status: string;
  importance: Importance;
  score: number;
  band: string;
  days_since_last_contact: number | null;
  narrative: string;
  generated_by: string;
  what_is_important: string;
  what_changed: string[];
  reconnect_opportunity: { yes: boolean; reason: string };
  next_interaction: string;
  stakeholders: {
    available: boolean;
    note: string;
    connections: {
      official_id: number;
      name: string;
      level: string | null;
      type: ConnectionType;
      direction: ConnectionDirection;
      label: string;
      note: string | null;
    }[];
    suggested_count: number;
    mentioned: string[];
  };
  open_followups: { title: string; due_at: string | null; overdue: boolean }[];
  recent_commitments: string[];
  open_moments: {
    type: string;
    status: string;
    trigger: string | null;
    suppressed: boolean;
  }[];
  upcoming_dates: { kind: string; date: string; in_days: number }[];
  open_opportunities: {
    id: number;
    title: string;
    status: string;
    stage: string;
    days_since_activity: number;
  }[];
  recent_interactions: {
    occurred_at: string;
    type: string;
    direction: string;
    sentiment: string;
    summary: string;
  }[];
}

// --- connections (stakeholder graph) --------------------------------
export type ConnectionType = "reports_to" | "works_with" | "introduced_by";
export type ConnectionStatus = "suggested" | "confirmed" | "dismissed";
export type ConnectionDirection = "outgoing" | "incoming" | "mutual";

export const CONNECTION_TYPES: ConnectionType[] = [
  "reports_to",
  "works_with",
  "introduced_by",
];

export const CONNECTION_TYPE_LABELS: Record<ConnectionType, string> = {
  reports_to: "Reports to",
  works_with: "Works with",
  introduced_by: "Introduced by",
};

export interface Neighbor {
  connection_id: number;
  official_id: number;
  name: string;
  level: string | null;
  type: ConnectionType;
  direction: ConnectionDirection;
  status: ConnectionStatus;
  label: string;
  note: string | null;
  source: string;
}

export interface OfficialGraph {
  official_id: number;
  confirmed: Neighbor[];
  suggested: Neighbor[];
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

export interface RelationMention {
  from: string;
  to: string;
  type: ConnectionType;
  evidence?: string;
}

export interface InteractionStructured {
  topics?: string[];
  commitments?: string[];
  requests?: string[];
  people?: string[];
  relations?: RelationMention[];
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

export type DateKind = "birthday" | "joined" | "promoted" | "marriage_anniversary";

export const DATE_KIND_LABELS: Record<DateKind, string> = {
  birthday: "Birthday",
  joined: "Date of joining",
  promoted: "Promotion",
  marriage_anniversary: "Marriage anniversary",
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
  | "marriage_anniversary"
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
  marriage_anniversary: "Marriage anniversary",
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

// --- opportunities --------------------------------------------------------
// Detection mirrors the stakeholder connection graph: a manual entry lands
// confirmed; something extracted from an interaction note lands suggested and
// waits for a human to confirm or dismiss it. Stage only progresses once
// confirmed.

export type OpportunityStatus = "suggested" | "confirmed" | "dismissed";
export type OpportunityStage =
  | "identified"
  | "qualified"
  | "proposal"
  | "negotiation"
  | "won"
  | "lost";
export type OpportunityActivityType = "email" | "call" | "meeting" | "note" | "stage_change";

export const OPPORTUNITY_STAGES: OpportunityStage[] = [
  "identified",
  "qualified",
  "proposal",
  "negotiation",
  "won",
  "lost",
];

export const OPPORTUNITY_STAGE_LABELS: Record<OpportunityStage, string> = {
  identified: "Identified",
  qualified: "Qualified",
  proposal: "Proposal",
  negotiation: "Negotiation",
  won: "Won",
  lost: "Lost",
};

export const OPPORTUNITY_STATUS_TONE: Record<
  OpportunityStatus,
  "neutral" | "primary" | "good" | "warn"
> = {
  suggested: "primary",
  confirmed: "good",
  dismissed: "neutral",
};

export const OPPORTUNITY_ACTIVITY_TYPES: OpportunityActivityType[] = [
  "email",
  "call",
  "meeting",
  "note",
];

export interface OpportunitySummary {
  id: number;
  relationship_id: number;
  official_id: number;
  official_name: string;
  title: string;
  status: OpportunityStatus;
  stage: OpportunityStage;
  source: string;
  source_interaction_id: number | null;
  closed_at: string | null;
  created_at: string;
}

export interface OpportunityActivity {
  id: number;
  opportunity_id: number;
  type: OpportunityActivityType;
  occurred_at: string;
  note: string;
  from_stage: OpportunityStage | null;
  to_stage: OpportunityStage | null;
  created_by: number | null;
  created_at: string;
}

export interface OpportunityDetail extends OpportunitySummary {
  detail: string | null;
  outcome_note: string | null;
  created_by: number | null;
  decided_by: number | null;
  decided_at: string | null;
  activities: OpportunityActivity[];
}

export interface OpportunityListResponse {
  items: OpportunitySummary[];
  total: number;
  limit: number;
  offset: number;
}

// --- autonomous agent ---------------------------------------------------
// Observe + recommend only: a run never writes a real domain object itself,
// it only produces recommendations a human must approve.

export type AgentTrigger = "manual" | "nightly";
export type AgentRunScope = "relationship" | "portfolio";
export type AgentRunStatus = "running" | "completed" | "failed";
export type RecommendationType = "create_task" | "draft_moment" | "create_opportunity";
export type RiskTier = "low" | "medium" | "high";
export type RecommendationStatus = "pending" | "approved" | "rejected" | "expired";

export const AGENT_REC_TYPE_LABELS: Record<RecommendationType, string> = {
  create_task: "Create a follow-up",
  draft_moment: "Draft an engagement moment",
  create_opportunity: "Create an opportunity",
};

export const RECOMMENDATION_STATUS_TONE: Record<
  RecommendationStatus,
  "neutral" | "primary" | "good" | "warn"
> = {
  pending: "primary",
  approved: "good",
  rejected: "warn",
  expired: "neutral",
};

export const RISK_TIER_TONE: Record<RiskTier, "good" | "warn" | "danger"> = {
  low: "good",
  medium: "warn",
  high: "danger",
};

export interface AgentRunSummary {
  id: number;
  trigger: AgentTrigger;
  scope: AgentRunScope;
  relationship_id: number | null;
  requested_by: number | null;
  status: AgentRunStatus;
  model: string;
  relationships_considered: number;
  recommendations_created: number;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  error: string | null;
}

export interface AgentRunDetail extends AgentRunSummary {
  tools_used: string[];
  recommendations: RecommendationSummary[];
}

export interface AgentRunListResponse {
  items: AgentRunSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface RecommendationSummary {
  id: number;
  run_id: number;
  relationship_id: number;
  official_id: number;
  official_name: string;
  type: RecommendationType;
  risk_tier: RiskTier;
  reasoning: string;
  status: RecommendationStatus;
  created_at: string;
  expires_at: string | null;
}

export interface RecommendationDetail extends RecommendationSummary {
  evidence: Record<string, unknown>;
  payload: Record<string, unknown>;
  result_ref: Record<string, unknown> | null;
  decided_by: number | null;
  decided_at: string | null;
}

export interface RecommendationListResponse {
  items: RecommendationSummary[];
  total: number;
  limit: number;
  offset: number;
}

// --- outcomes & learning --------------------------------------------------
// What happened after a recommendation was approved (Phase 11). Never an
// LLM guess - a deterministic verdict computed from the tracked task/
// moment/opportunity's real state.

export type OutcomeStatus = "pending" | "positive" | "negative" | "neutral" | "inconclusive";

export const OUTCOME_STATUS_TONE: Record<OutcomeStatus, "neutral" | "primary" | "good" | "warn" | "danger"> = {
  pending: "neutral",
  positive: "good",
  negative: "danger",
  neutral: "warn",
  inconclusive: "neutral",
};

export interface RecommendationOutcome {
  id: number;
  recommendation_id: number;
  tracked_object_type: string;
  tracked_object_id: number;
  status: OutcomeStatus;
  checked_at: string;
  resolved_at: string | null;
  detail: Record<string, unknown>;
}

export interface EvaluationSummary {
  total_decided: number;
  approval_rate: number | null;
  resolved_outcomes: number;
  positive_outcome_rate: number | null;
  median_days_to_resolution: number | null;
}

export type StrategyStatus = "draft" | "testing" | "active" | "retired";
export type StrategyVersionStatus = "draft" | "testing" | "active" | "retired" | "rejected";
export type ExperimentStatus = "draft" | "running" | "completed" | "aborted";

export const STRATEGY_STATUS_TONE: Record<StrategyStatus, "neutral" | "primary" | "good" | "warn"> = {
  draft: "neutral",
  testing: "primary",
  active: "good",
  retired: "warn",
};

export const STRATEGY_VERSION_STATUS_TONE: Record<
  StrategyVersionStatus,
  "neutral" | "primary" | "good" | "warn" | "danger"
> = {
  draft: "neutral",
  testing: "primary",
  active: "good",
  retired: "warn",
  rejected: "danger",
};

export const EXPERIMENT_STATUS_TONE: Record<ExperimentStatus, "neutral" | "primary" | "good" | "warn"> = {
  draft: "neutral",
  running: "primary",
  completed: "good",
  aborted: "warn",
};

export interface StrategyVersionOut {
  id: number;
  strategy_id: number;
  version: number;
  config: Record<string, unknown>;
  evaluation_metrics: Record<string, unknown> | null;
  experiment_metadata: Record<string, unknown> | null;
  status: StrategyVersionStatus;
  created_by: number | null;
  approved_by: number | null;
  approved_at: string | null;
  created_at: string;
}

export interface StrategyOut {
  id: number;
  strategy_id: string;
  name: string;
  category: string;
  current_version_id: number | null;
  status: StrategyStatus;
  versions: StrategyVersionOut[];
}

export interface ExperimentAssignmentOut {
  relationship_id: number;
  arm: "control" | "treatment";
}

export interface ExperimentOut {
  id: number;
  strategy_id: number;
  control_version_id: number;
  treatment_version_id: number;
  status: ExperimentStatus;
  started_at: string | null;
  ended_at: string | null;
  minimum_sample_size: number;
  assignments: ExperimentAssignmentOut[];
}

// --- audit log --------------------------------------------------------

export interface AuditEntry {
  id: number;
  actor_id: number | null;
  actor_name: string | null;
  actor_role: string | null;
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

// --- supervisor / ask ---------------------------------------------------

export interface AskConsidered {
  relationship_id: number;
  official_name: string;
}

export interface AskResponse {
  conversation_id: number;
  answer: string;
  generated_by: string;
  scope: "targeted" | "portfolio";
  considered: AskConsidered[];
}

// --- call intelligence ----------------------------------------------------
// A Call Session is the technical event; it only becomes a CRM Interaction
// once a human (the DC) reviews and confirms. "RECORDING FAIL != INTERACTION
// FAIL" - a call with no recording is just as loggable via voice note/manual
// text, never a broken/second-class path.

export type CallDirection = "inbound" | "outbound" | "internal";
export type CallProcessingStatus =
  | "initiated" | "ringing" | "connected" | "ended" | "recording" | "no_recording"
  | "upload_pending" | "uploaded" | "transcribing" | "analyzing" | "review_required"
  | "approved" | "crm_logged" | "cancelled" | "recording_unavailable" | "upload_failed"
  | "transcription_failed" | "analysis_failed" | "review_rejected" | "crm_write_failed";
export type CallIdentityStatus =
  | "registered" | "unregistered" | "possible_identity" | "verified_new_official" | "unidentified" | "csp";

export const CALL_PROCESSING_STATUS_TONE: Record<CallProcessingStatus, "neutral" | "primary" | "good" | "warn" | "danger"> = {
  initiated: "neutral", ringing: "neutral", connected: "neutral", ended: "neutral",
  recording: "primary", no_recording: "warn", upload_pending: "neutral", uploaded: "neutral",
  transcribing: "primary", analyzing: "primary", review_required: "primary", approved: "good",
  crm_logged: "good", cancelled: "neutral", recording_unavailable: "warn", upload_failed: "danger",
  transcription_failed: "danger", analysis_failed: "danger", review_rejected: "danger",
  crm_write_failed: "danger",
};

export const CALL_IDENTITY_STATUS_TONE: Record<CallIdentityStatus, "neutral" | "primary" | "good" | "warn" | "danger"> = {
  registered: "good", unregistered: "warn", possible_identity: "primary",
  verified_new_official: "good", unidentified: "neutral", csp: "good",
};

export const CALL_IDENTITY_STATUS_LABEL: Record<CallIdentityStatus, string> = {
  registered: "registered", unregistered: "unregistered", possible_identity: "possible identity",
  verified_new_official: "verified new official", unidentified: "unidentified",
  csp: "Kiosk Operator",
};

export interface CallSessionSummary {
  id: number;
  dc_user_id: number;
  dc_user_name: string;
  direction: CallDirection;
  phone_ref: string;
  official_id: number | null;
  official_name: string | null;
  csp_id: number | null;
  csp_name: string | null;
  relationship_id: number | null;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  duration_source: string | null;
  channel: string;
  recording_status: string;
  identity_status: CallIdentityStatus;
  processing_status: CallProcessingStatus;
  reminder_at: string | null;
}

export interface CallBrief {
  summary?: string;
  highlights?: string[];
  key_points?: string[];
  decisions?: string[];
  commitments?: string[];
  action_items?: string[];
  opportunities?: string[];
  relationship_signals?: string[];
  suggested_next_interaction?: string;
}

export interface CallSessionDetail extends CallSessionSummary {
  transcript_text: string | null;
  transcript_source: string | null;
  brief: CallBrief | null;
  recording_status_detail: string | null;
  has_voice_note: boolean;
}

export interface CallSessionListResponse {
  items: CallSessionSummary[];
  total: number;
}

export interface DcOption {
  id: number;
  name: string;
  role?: string; // "dc" | "relationship_manager"
}

// --- CSPs (Customer Service Points), grouped by Relationship Manager -----
export interface Csp {
  id: number;
  csp_id: string;
  name: string;
  mobile: string | null;
  alternate_mobile: string | null;
  category: string | null;
  rm_name: string;
  rm_user_id: number | null;
  branch_name: string | null;
  district: string | null;
  state: string | null;
  status: string;
  date_of_birth: string | null;
  gender: string | null;
  email: string | null;
  address: string | null;
  pincode: string | null;
  home_phone: string | null;
}

export interface CspRmGroup {
  rm_name: string;
  rm_user_id: number | null;
  count: number;
  csps: Csp[];
}

export interface CspByRmResponse {
  groups: CspRmGroup[];
  total: number;
}

export interface CspProfileResponse {
  csp: Csp;
  calls: CallSessionDetail[];
  calls_total: number;
}

export interface NameValue {
  name: string;
  value: number;
}

export interface UpcomingBirthday {
  csp_id: string;
  name: string;
  rm_name: string;
  date: string;
  in_days: number;
  email: string | null;
}

export interface DashboardOverview {
  kpis: {
    active_csps: number;
    relationship_managers: number;
    sbi_officials: number;
    calls_total: number;
    recordings: number;
    birthdays_7d: number;
  };
  csps_by_rm: NameValue[];
  csps_by_category: NameValue[];
  csps_by_state: NameValue[];
  calls_by_rm: NameValue[];
  calls_by_direction: NameValue[];
  calls_timeline: { date: string; value: number }[];
  upcoming_birthdays: UpcomingBirthday[];
}
