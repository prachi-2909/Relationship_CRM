package com.eko.rcrm.dc.data.repository

import com.eko.rcrm.dc.data.remote.dto.CommitmentDto
import com.eko.rcrm.dc.data.remote.dto.OfficialBriefingDto
import com.eko.rcrm.dc.data.remote.dto.PerformanceDto
import com.eko.rcrm.dc.data.remote.dto.PreCallDto
import com.eko.rcrm.dc.data.remote.dto.SuggestionItemDto
import com.eko.rcrm.dc.domain.model.BriefingFollowup
import com.eko.rcrm.dc.domain.model.BriefingInteraction
import com.eko.rcrm.dc.domain.model.Commitment
import com.eko.rcrm.dc.domain.model.DuplicateOf
import com.eko.rcrm.dc.domain.model.OfficialBriefing
import com.eko.rcrm.dc.domain.model.PerformanceReview
import com.eko.rcrm.dc.domain.model.PreCall
import com.eko.rcrm.dc.domain.model.PreCallLastCall
import com.eko.rcrm.dc.domain.model.Suggestion

// Shared by the CSP and SBI-official repositories: one place turns the briefing JSON into domain models.

internal fun CommitmentDto.toDomain() = Commitment(
    id = id,
    text = text,
    party = party,
    dueDate = due_date,
    status = status,
    possibleDuplicate = possible_duplicate?.let { DuplicateOf(it.text, it.status, it.due_date) },
    alsoMentioned = also_mentioned.size
)

internal fun SuggestionItemDto.toDomain() = Suggestion(
    key = key,
    type = type,
    kind = kind,
    text = text,
    myVerdict = my_verdict
)

private fun PerformanceDto.toDomain() = PerformanceReview(
    what = what,
    why = why,
    shouldBe = should_be,
    fromIso = from
)

internal fun PreCallDto.toDomain() = PreCall(
    cspId = csp_id,
    name = name,
    category = category,
    branch = branch,
    mobile = mobile,
    alternateMobile = alternate_mobile,
    callsCount = calls_count,
    lastCall = last_call?.let {
        PreCallLastCall(
            whenIso = it.whenIso,
            direction = it.direction,
            summary = it.summary,
            highlights = it.highlights
        )
    },
    // The RM's own side also carries the joint ones; the CSP's side is what the CSP promised.
    youCommitted = (open_commitments.ours + open_commitments.mutual).map { it.toDomain() },
    theyCommitted = open_commitments.theirs.map { it.toDomain() },
    suggested = proposed_commitments.map { it.toDomain() },
    slabStatus = slab_status,
    performance = performance?.takeIf { it.what.isNotEmpty() || it.why.isNotEmpty() || it.should_be.isNotEmpty() }
        ?.toDomain(),
    memory = memory.map { it.fact },
    talkingPoints = talking_point_items.map { it.toDomain() },
    suppressedCount = suppressed_count
)

internal fun OfficialBriefingDto.toDomain(): OfficialBriefing {
    val line = relationship?.let { r ->
        buildList {
            add(r.status.replace('_', ' '))
            add("health ${r.score} (${r.band})")
            r.days_since_contact?.let { add("last contact $it day${if (it == 1) "" else "s"} ago") }
        }.joinToString(", ")
    }
    return OfficialBriefing(
        relationshipLine = line,
        interactions = interactions.map {
            BriefingInteraction(it.occurred_at.take(10), it.type, it.direction, it.sentiment, it.summary)
        },
        memory = memory.map { it.fact },
        youCommitted = (commitments.ours + commitments.mutual).map { it.toDomain() },
        theyCommitted = commitments.theirs.map { it.toDomain() },
        suggested = proposed_commitments.map { it.toDomain() },
        followups = followups.map { BriefingFollowup(it.title, it.due_at?.take(10), it.overdue) },
        upcoming = upcoming_dates.map {
            "${it.label} ${if (it.in_days == 0) "today" else "in ${it.in_days} day${if (it.in_days == 1) "" else "s"}"}"
        },
        talkingPoints = talking_point_items.map { it.toDomain() },
        followupSuggestions = followup_suggestion_items.map { it.toDomain() },
        suppressedCount = suppressed_count
    )
}
