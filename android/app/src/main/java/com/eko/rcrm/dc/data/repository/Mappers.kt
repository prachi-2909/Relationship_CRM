package com.eko.rcrm.dc.data.repository

import com.eko.rcrm.dc.data.remote.dto.CallBriefDto
import com.eko.rcrm.dc.data.remote.dto.CallSessionDetailDto
import com.eko.rcrm.dc.data.remote.dto.CallSessionSummaryDto
import com.eko.rcrm.dc.data.remote.dto.OfficialDto
import com.eko.rcrm.dc.data.remote.dto.UserDto
import com.eko.rcrm.dc.domain.model.CallBrief
import com.eko.rcrm.dc.domain.model.CallSession
import com.eko.rcrm.dc.domain.model.Official
import com.eko.rcrm.dc.domain.model.User

fun UserDto.toDomain() = User(
    id = id,
    name = name,
    email = email,
    role = role,
    status = status
)

fun OfficialDto.toDomain() = Official(
    id = id,
    name = name,
    email = email,
    phone = phone,
    designation = designation,
    level = level,
    location = location
)

fun CallBriefDto.toDomain() = CallBrief(
    summary = summary,
    keyPoints = key_points,
    decisions = decisions,
    commitments = commitments,
    actionItems = action_items,
    opportunities = opportunities,
    relationshipSignals = relationship_signals,
    suggestedNextInteraction = suggested_next_interaction
)

fun CallBrief.toDto() = CallBriefDto(
    summary = summary,
    key_points = keyPoints,
    decisions = decisions,
    commitments = commitments,
    action_items = actionItems,
    opportunities = opportunities,
    relationship_signals = relationshipSignals,
    suggested_next_interaction = suggestedNextInteraction
)

fun CallSessionSummaryDto.toDomain() = CallSession(
    id = id,
    dcUserId = dc_user_id,
    dcUserName = dc_user_name,
    direction = direction,
    phoneRef = phone_ref,
    officialId = official_id,
    officialName = official_name,
    relationshipId = relationship_id,
    startedAt = started_at,
    endedAt = ended_at,
    durationSeconds = duration_seconds,
    recordingStatus = recording_status,
    identityStatus = identity_status,
    processingStatus = processing_status,
    reminderAt = reminder_at
)

fun CallSessionDetailDto.toDomain() = CallSession(
    id = id,
    dcUserId = dc_user_id,
    dcUserName = dc_user_name,
    direction = direction,
    phoneRef = phone_ref,
    officialId = official_id,
    officialName = official_name,
    relationshipId = relationship_id,
    startedAt = started_at,
    endedAt = ended_at,
    durationSeconds = duration_seconds,
    recordingStatus = recording_status,
    identityStatus = identity_status,
    processingStatus = processing_status,
    reminderAt = reminder_at,
    transcriptText = transcript_text,
    transcriptSource = transcript_source,
    brief = brief?.toDomain() ?: CallBrief(),
    recordingStatusDetail = recording_status_detail
)
