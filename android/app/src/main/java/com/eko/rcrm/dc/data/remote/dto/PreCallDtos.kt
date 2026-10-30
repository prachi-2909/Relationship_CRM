package com.eko.rcrm.dc.data.remote.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** The earlier commitment a new one looks like (shown beside it so a person can rule on it). */
@Serializable
data class CommitmentRefDto(
    val id: Int,
    val text: String,
    val party: String = "mutual",
    val status: String = "open",
    val due_date: String? = null,
    val source_call_id: Int? = null
)

@Serializable
data class AlsoMentionedDto(
    val id: Int,
    val due_date: String? = null
)

/** One tracked commitment (pre-call / official briefing, and the status / duplicate endpoints). */
@Serializable
data class CommitmentDto(
    val id: Int,
    val text: String,
    val party: String = "mutual",
    val due_date: String? = null,
    val status: String = "open",
    val source_call_id: Int? = null,
    val owner_user_id: Int? = null,
    val possible_duplicate: CommitmentRefDto? = null,
    val also_mentioned: List<AlsoMentionedDto> = emptyList()
)

/** One generated suggestion, keyed so the user can rate it. type = talking_point | followup. */
@Serializable
data class SuggestionItemDto(
    val key: String,
    val type: String,
    val kind: String = "",
    val text: String,
    val my_verdict: String? = null
)

/** What the RM told the CSP last call: where they stand, why, and what it should be. */
@Serializable
data class PerformanceDto(
    val what: List<String> = emptyList(),
    val why: List<String> = emptyList(),
    val should_be: List<String> = emptyList(),
    val from: String = ""
)

@Serializable
data class PreCallLastCallDto(
    val call_id: Int = 0,
    @SerialName("when") val whenIso: String = "",
    val direction: String = "",
    val summary: String = "",
    val highlights: List<String> = emptyList()
)

@Serializable
data class OpenCommitmentsDto(
    val ours: List<CommitmentDto> = emptyList(),
    val theirs: List<CommitmentDto> = emptyList(),
    val mutual: List<CommitmentDto> = emptyList(),
    val total: Int = 0
)

@Serializable
data class MemoryFactDto(
    val fact: String,
    val kind: String = ""
)

/** The CSP relationship score: relationship, business (from TARA) and overall, with the reasons in words. */
@Serializable
data class CspScoreDto(
    val version: String = "",
    val overall: Int? = null,
    val relationship: Int? = null,
    val business: Int? = null,
    val band: String? = null,
    val tara_included: Boolean = false,
    val reasons: List<String> = emptyList()
)

@Serializable
data class TaraSlabSchemeDto(
    val scheme: String = "",
    val have: Double? = null,
    val threshold: Double? = null,
    val more: Double? = null
)

@Serializable
data class TaraSlabNextDto(
    val name: String? = null,
    val incentive_inr: Double? = null,
    val schemes: List<TaraSlabSchemeDto> = emptyList(),
    val closest_three: List<String> = emptyList(),
    val extra_total: Double? = null
)

@Serializable
data class TaraSlabDto(
    val rule: String? = null,
    val reached: String? = null,
    val reached_in_calling_sheet: String? = null,
    val target_in_calling_sheet: String? = null,
    val basis: String = "",
    val next: TaraSlabNextDto? = null
)

@Serializable
data class TaraProductDto(
    val code: String = "",
    val name: String = "",
    val achieved: Double? = null,
    val sbi_target: Double? = null,
    val tara_goal: Double? = null,
    val agent_target: Double? = null,
    val progress: Double? = null,
    val pace_status: String? = null
)

@Serializable
data class TaraTransactionsDto(
    val count: Double? = null,
    val gtv_inr: Double? = null,
    val days_with_data: Double? = null,
    val last_day_with_data: String? = null
)

@Serializable
data class TaraEarningsDto(
    val month: String? = null,
    val value_inr: Double? = null,
    val usual_inr: Double? = null,
    val growth_pct: Double? = null,
    val status: String? = null,
    val rank_in_district: Double? = null,
    val of_in_district: Double? = null
)

@Serializable
data class TaraActivityDto(
    val days_without_activity: Double? = null,
    val last_login_date: String? = null,
    val terminal_status: String? = null,
    val matm_status: String? = null,
    val passbook_printer_status: String? = null,
    val gps_dongle_status: String? = null
)

/** TARA's figures for one CSP, copied as TARA sends them. available=false means TARA gave nothing. */
@Serializable
data class TaraPanelDto(
    val available: Boolean = false,
    val as_of: String? = null,
    val month: String? = null,
    val slab: TaraSlabDto? = null,
    val products: List<TaraProductDto> = emptyList(),
    val transactions: TaraTransactionsDto? = null,
    val earnings: TaraEarningsDto? = null,
    val activity: TaraActivityDto? = null,
    val caveats: List<String> = emptyList()
)

/** The same pre-call briefing the web CRM shows - one backend source of truth. */
@Serializable
data class PreCallDto(
    val csp_id: String,
    val name: String,
    val category: String? = null,
    val branch: String? = null,
    val rm_name: String = "",
    val mobile: String? = null,
    val alternate_mobile: String? = null,
    val calls_count: Int = 0,
    val last_call: PreCallLastCallDto? = null,
    val open_commitments: OpenCommitmentsDto = OpenCommitmentsDto(),
    val proposed_commitments: List<CommitmentDto> = emptyList(),
    val slab_status: List<String> = emptyList(),
    val score: CspScoreDto? = null,
    val tara: TaraPanelDto? = null,
    val performance: PerformanceDto? = null,
    val memory: List<MemoryFactDto> = emptyList(),
    val talking_point_items: List<SuggestionItemDto> = emptyList(),
    val suppressed_count: Int = 0
)

// ---- SBI-official briefing (the DC-facing counterpart) ----

@Serializable
data class BriefingRelationshipDto(
    val status: String = "",
    val importance: String = "",
    val score: Int = 0,
    val band: String = "",
    val days_since_contact: Int? = null
)

@Serializable
data class BriefingInteractionDto(
    val id: Int = 0,
    val occurred_at: String = "",
    val type: String = "",
    val direction: String = "",
    val sentiment: String = "",
    val summary: String = ""
)

@Serializable
data class BriefingMemoryDto(
    val fact: String,
    val kind: String = "",
    val state: String? = null
)

@Serializable
data class BriefingFollowupDto(
    val id: Int = 0,
    val title: String = "",
    val due_at: String? = null,
    val overdue: Boolean = false
)

@Serializable
data class BriefingDateDto(
    val kind: String = "",
    val label: String = "",
    val in_days: Int = 0
)

@Serializable
data class OfficialBriefingDto(
    val relationship: BriefingRelationshipDto? = null,
    val interactions: List<BriefingInteractionDto> = emptyList(),
    val memory: List<BriefingMemoryDto> = emptyList(),
    val commitments: OpenCommitmentsDto = OpenCommitmentsDto(),
    val proposed_commitments: List<CommitmentDto> = emptyList(),
    val followups: List<BriefingFollowupDto> = emptyList(),
    val upcoming_dates: List<BriefingDateDto> = emptyList(),
    val talking_point_items: List<SuggestionItemDto> = emptyList(),
    val followup_suggestion_items: List<SuggestionItemDto> = emptyList(),
    val suppressed_count: Int = 0
)

// ---- requests ----

@Serializable
data class CommitmentStatusRequestDto(
    val status: String,
    /** "fulfilled" | "not_fulfilled" - how it ended (omitted when null). */
    val outcome: String? = null
)

@Serializable
data class DuplicateDecisionRequestDto(val decision: String)

@Serializable
data class FeedbackRequestDto(
    val target_type: String,
    val key: String,
    val verdict: String
)
