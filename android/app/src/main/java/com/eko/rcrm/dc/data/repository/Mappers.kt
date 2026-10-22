package com.eko.rcrm.dc.data.repository

import com.eko.rcrm.dc.data.remote.dto.CallBriefDto
import com.eko.rcrm.dc.data.remote.dto.CallSessionDetailDto
import com.eko.rcrm.dc.data.remote.dto.CallSessionSummaryDto
import com.eko.rcrm.dc.data.remote.dto.DcProfileDto
import com.eko.rcrm.dc.data.remote.dto.DcTerritoryDto
import com.eko.rcrm.dc.data.remote.dto.OfficialDto
import com.eko.rcrm.dc.data.remote.dto.UserDto
import com.eko.rcrm.dc.domain.model.CallBrief
import com.eko.rcrm.dc.domain.model.CallSession
import com.eko.rcrm.dc.domain.model.DcProfile
import com.eko.rcrm.dc.domain.model.DcTerritory
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
    department = department,
    level = level,
    location = location,
    organizationUnitId = organization_unit_id,
    organizationUnitName = organization_unit_name,
    organizationUnitType = organization_unit_type,
    status = status,
    verificationStatus = verification_status
)

fun DcTerritoryDto.toDomain() = DcTerritory(
    id = id,
    dcUserId = dc_user_id,
    dcUserName = dc_user_name,
    organizationUnitId = organization_unit_id,
    organizationUnitName = organization_unit_name,
    organizationUnitType = organization_unit_type,
    assignedAt = assigned_at,
    isDirect = is_direct
)

fun DcProfileDto.toDomain() = DcProfile(
    id = id,
    name = name,
    email = email,
    status = status,
    territory = territory.map { it.toDomain() },
    pendingCalls = pending_calls,
    loggedInteractions = logged_interactions
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
    durationSource = duration_source,
    recordingEngine = recording_engine,
    recordingCapabilityStatus = recording_capability_status,
    channel = channel,
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
    durationSource = duration_source,
    recordingEngine = recording_engine,
    recordingCapabilityStatus = recording_capability_status,
    channel = channel,
    recordingStatus = recording_status,
    identityStatus = identity_status,
    processingStatus = processing_status,
    reminderAt = reminder_at,
    transcriptText = transcript_text,
    transcriptSource = transcript_source,
    brief = brief?.toDomain() ?: CallBrief(),
    recordingStatusDetail = recording_status_detail,
    hasVoiceNote = has_voice_note
)
