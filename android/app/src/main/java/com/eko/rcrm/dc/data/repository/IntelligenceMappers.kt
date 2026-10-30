package com.eko.rcrm.dc.data.repository

import com.eko.rcrm.dc.data.remote.dto.CommitmentDto
import com.eko.rcrm.dc.data.remote.dto.CspScoreDto
import com.eko.rcrm.dc.data.remote.dto.OfficialBriefingDto
import com.eko.rcrm.dc.data.remote.dto.PerformanceDto
import com.eko.rcrm.dc.data.remote.dto.PreCallDto
import com.eko.rcrm.dc.data.remote.dto.SuggestionItemDto
import com.eko.rcrm.dc.data.remote.dto.TaraPanelDto
import com.eko.rcrm.dc.domain.model.BriefingFollowup
import com.eko.rcrm.dc.domain.model.BriefingInteraction
import com.eko.rcrm.dc.domain.model.Commitment
import com.eko.rcrm.dc.domain.model.CspScore
import com.eko.rcrm.dc.domain.model.DuplicateOf
import com.eko.rcrm.dc.domain.model.OfficialBriefing
import com.eko.rcrm.dc.domain.model.PerformanceReview
import com.eko.rcrm.dc.domain.model.PreCall
import com.eko.rcrm.dc.domain.model.PreCallLastCall
import com.eko.rcrm.dc.domain.model.Suggestion
import com.eko.rcrm.dc.domain.model.TaraPanel
import com.eko.rcrm.dc.domain.model.TaraSlab
import com.eko.rcrm.dc.domain.model.TaraProduct
import com.eko.rcrm.dc.domain.model.TaraSlabNext
import com.eko.rcrm.dc.domain.model.TaraSlabScheme

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

private fun CspScoreDto.toDomain(): CspScore? = overall?.let {
    CspScore(
        overall = it, relationship = relationship, business = business, band = band,
        taraIncluded = tara_included, reasons = reasons
    )
}

private fun TaraPanelDto.toDomain() = TaraPanel(
    available = available,
    asOf = as_of,
    month = month,
    slab = slab?.let { s ->
        TaraSlab(
            reached = s.reached ?: s.reached_in_calling_sheet,
            target = s.target_in_calling_sheet,
            basis = s.basis,
            rule = s.rule,
            next = s.next?.let { n ->
                TaraSlabNext(
                    name = n.name,
                    incentiveInr = n.incentive_inr,
                    schemes = n.schemes.map { TaraSlabScheme(it.scheme, it.have, it.threshold, it.more) },
                    closestThree = n.closest_three,
                    extraTotal = n.extra_total
                )
            }
        )
    },
    products = products.map {
        TaraProduct(it.name, it.achieved, it.sbi_target, it.tara_goal, it.agent_target, it.progress, it.pace_status)
    },
    transactionsCount = transactions?.count,
    transactionsValueInr = transactions?.gtv_inr,
    lastDayWithData = transactions?.last_day_with_data,
    earningsMonth = earnings?.month,
    earnedInr = earnings?.value_inr,
    usualInr = earnings?.usual_inr,
    growthPct = earnings?.growth_pct,
    earningsStatus = earnings?.status,
    rankInDistrict = earnings?.rank_in_district,
    ofInDistrict = earnings?.of_in_district,
    lastLoginDate = activity?.last_login_date,
    daysWithoutActivity = activity?.days_without_activity,
    terminalStatus = activity?.terminal_status,
    matmStatus = activity?.matm_status,
    passbookPrinterStatus = activity?.passbook_printer_status,
    gpsDongleStatus = activity?.gps_dongle_status,
    caveats = caveats
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
    score = score?.toDomain(),
    tara = tara?.toDomain(),
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
