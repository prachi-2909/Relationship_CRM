package com.eko.rcrm.dc.domain.model

/** A tracked commitment. [party] is "ours" (the RM promised), "theirs" (the CSP promised) or "mutual". */
data class Commitment(
    val id: Int,
    val text: String,
    val party: String,
    val dueDate: String?,
    val status: String
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
    val memory: List<String>,
    val talkingPoints: List<String>
) {
    val isEmpty: Boolean
        get() = lastCall == null && youCommitted.isEmpty() && theyCommitted.isEmpty() &&
            suggested.isEmpty() && talkingPoints.isEmpty() && memory.isEmpty()
}
