"""SQLAlchemy models. Importing this package registers every table on Base.metadata."""

from .agent import (
    AgentRecommendation,
    AgentRun,
    AgentRunScope,
    AgentRunStatus,
    AgentTrigger,
    RecommendationStatus,
    RecommendationType,
    RiskTier,
)
from .audit import AuditLog
from .base import Base, TimestampMixin
from .call_intelligence import (
    CallAIAnalysis,
    CallIdentityCandidate,
    CallRecording,
    CallReview,
    CallSession,
    CallSessionStatus,
    CallTranscript,
    CallVoiceNote,
    IdentityStatus,
)
from .media_deletion import MediaDeletion
from .commitment import (
    Commitment,
    CommitmentParty,
    CommitmentSourceKind,
    CommitmentStatus,
)
from .connection import Connection, ConnectionStatus, ConnectionType
from .conversation import AskConversation, AskMessage, MessageRole
from .csp import Csp, CspStatus
from .data_import import DataImport, ImportRow, ImportStatus, RowAction
from .dc_territory import DCTerritory
from .engagement_moment import EngagementMoment, MomentStatus, MomentType
from .interaction import Direction, Interaction, InteractionType, Sentiment
from .knowledge import KnowledgeChunk
from .official import (
    FieldVerification,
    Official,
    OfficialFieldProvenance,
    OfficialStatus,
    PROVENANCED_FIELDS,
    VerificationStatus,
)
from .official_date import DateKind, OfficialDate
from .opportunity import (
    Opportunity,
    OpportunityActivity,
    OpportunityActivityType,
    OpportunityStage,
    OpportunityStatus,
)
from .org_unit_type import OrgUnitType
from .organization_unit import OrganizationUnit, OrgUnitStatus
from .outcome import OutcomeStatus, RecommendationOutcome
from .relationship import (
    Importance,
    Relationship,
    RelationshipScoreHistory,
    RelationshipStatus,
    RiskLevel,
)
from .semantic_memory import SemanticMemoryFact, SemanticVerificationState
from .session import UserSession
from .strategic_insight import StrategicInsight
from .strategy import (
    Experiment,
    ExperimentArm,
    ExperimentAssignment,
    ExperimentStatus,
    Strategy,
    StrategyStatus,
    StrategyVersion,
    StrategyVersionStatus,
)
from .task import Task, TaskStatus
from .user import Role, User, UserStatus

__all__ = [
    "Base",
    "TimestampMixin",
    "AgentRun",
    "AgentRecommendation",
    "AgentTrigger",
    "AgentRunScope",
    "AgentRunStatus",
    "RecommendationType",
    "RiskTier",
    "RecommendationStatus",
    "User",
    "Role",
    "UserStatus",
    "UserSession",
    "AuditLog",
    "OrgUnitType",
    "OrganizationUnit",
    "OrgUnitStatus",
    "Official",
    "OfficialStatus",
    "OfficialFieldProvenance",
    "FieldVerification",
    "VerificationStatus",
    "PROVENANCED_FIELDS",
    "Relationship",
    "RelationshipScoreHistory",
    "RelationshipStatus",
    "Importance",
    "RiskLevel",
    "Interaction",
    "InteractionType",
    "Direction",
    "Sentiment",
    "Task",
    "TaskStatus",
    "DataImport",
    "ImportRow",
    "ImportStatus",
    "RowAction",
    "OfficialDate",
    "DateKind",
    "EngagementMoment",
    "MomentType",
    "MomentStatus",
    "Connection",
    "ConnectionType",
    "ConnectionStatus",
    "Csp",
    "CspStatus",
    "MediaDeletion",
    "Commitment",
    "CommitmentParty",
    "CommitmentStatus",
    "CommitmentSourceKind",
    "AskConversation",
    "AskMessage",
    "MessageRole",
    "Opportunity",
    "OpportunityActivity",
    "OpportunityStatus",
    "OpportunityStage",
    "OpportunityActivityType",
    "KnowledgeChunk",
    "SemanticMemoryFact",
    "SemanticVerificationState",
    "StrategicInsight",
    "RecommendationOutcome",
    "OutcomeStatus",
    "Strategy",
    "StrategyStatus",
    "StrategyVersion",
    "StrategyVersionStatus",
    "Experiment",
    "ExperimentStatus",
    "ExperimentAssignment",
    "ExperimentArm",
    "CallSession",
    "CallSessionStatus",
    "IdentityStatus",
    "CallRecording",
    "CallVoiceNote",
    "CallTranscript",
    "CallAIAnalysis",
    "CallIdentityCandidate",
    "CallReview",
    "DCTerritory",
]
