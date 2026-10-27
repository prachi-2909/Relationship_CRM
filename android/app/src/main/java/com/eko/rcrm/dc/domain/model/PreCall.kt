package com.eko.rcrm.dc.domain.model

/** The earlier commitment a new one looks like. */
data class DuplicateOf(
    val text: String,
    val status: String,
    val dueDate: String?
)

/** A tracked commitment. [party] is "ours" (we promised), "theirs" or "mutual". */
data class Commitment(
    val id: Int,
    val text: String,
    val party: String,
    val dueDate: String?,
    val status: String,
    /** Set while a person has yet to rule that this is (or is not) a repeat of an earlier commitment. */
    val possibleDuplicate: DuplicateOf? = null,
    /** How many repeats a person already folded into this one. */
    val alsoMentioned: Int = 0
)

/** A generated suggestion the user can rate. [type] is "talking_point" or "followup". */
data class Suggestion(
    val key: String,
    val type: String,
    val kind: String,
    val text: String,
    val myVerdict: String?
) {
    val isFollowup: Boolean get() = type == "followup"
}

/** What the RM told the CSP last time: where they stand, why, and what it should be. */
data class PerformanceReview(
    val what: List<String>,
    val why: List<String>,
    val shouldBe: List<String>,
    val fromIso: String
)

data class PreCallLastCall(
    val whenIso: String,
    val direction: String,
    val summary: String,
    val highlights: List<String>
)

/** Everything the RM should know before dialling a CSP. */
data class PreCall(
    val cspId: String,
    val name: String,
    val category: String?,
    val branch: String?,
    val mobile: String?,
    val alternateMobile: String?,
    val callsCount: Int,
    val lastCall: PreCallLastCall?,
    val youCommitted: List<Commitment>,
    val theyCommitted: List<Commitment>,
    /** AI suggestions awaiting the RM's accept / dismiss - not obligations yet. */
    val suggested: List<Commitment>,
    val slabStatus: List<String>,
    val performance: PerformanceReview?,
    val memory: List<String>,
    val talkingPoints: List<Suggestion>,
    val suppressedCount: Int
) {
    val isEmpty: Boolean
        get() = lastCall == null && youCommitted.isEmpty() && theyCommitted.isEmpty() &&
            suggested.isEmpty() && talkingPoints.isEmpty() && memory.isEmpty() && performance == null
}

// ---- SBI-official briefing (the DC-facing counterpart) ----

data class BriefingInteraction(
    val whenIso: String,
    val type: String,
    val direction: String,
    val sentiment: String,
    val summary: String
)

data class BriefingFollowup(
    val title: String,
    val dueAt: String?,
    val overdue: Boolean
)

data class OfficialBriefing(
    /** One line: e.g. "active, health 72 (Healthy), last contact 12 days ago". */
    val relationshipLine: String?,
    val interactions: List<BriefingInteraction>,
    val memory: List<String>,
    /** "You" = the DC (and joint ones); "They" = the official. */
    val youCommitted: List<Commitment>,
    val theyCommitted: List<Commitment>,
    val suggested: List<Commitment>,
    val followups: List<BriefingFollowup>,
    val upcoming: List<String>,
    val talkingPoints: List<Suggestion>,
    val followupSuggestions: List<Suggestion>,
    val suppressedCount: Int
) {
    val isEmpty: Boolean
        get() = interactions.isEmpty() && memory.isEmpty() && youCommitted.isEmpty() && theyCommitted.isEmpty() &&
            suggested.isEmpty() && followups.isEmpty() && talkingPoints.isEmpty() && followupSuggestions.isEmpty()
}
