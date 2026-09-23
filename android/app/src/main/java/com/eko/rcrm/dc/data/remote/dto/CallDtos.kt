package com.eko.rcrm.dc.data.remote.dto

import kotlinx.serialization.Serializable

@Serializable
data class CallBriefDto(
    val summary: String = "",
    val key_points: List<String> = emptyList(),
    val decisions: List<String> = emptyList(),
    val commitments: List<String> = emptyList(),
    val action_items: List<String> = emptyList(),
    val opportunities: List<String> = emptyList(),
    val relationship_signals: List<String> = emptyList(),
    val suggested_next_interaction: String = ""
)

@Serializable
data class CallSessionSummaryDto(
    val id: Int,
    val dc_user_id: Int,
    val dc_user_name: String,
    val direction: String,
    val phone_ref: String? = null,
    val official_id: Int? = null,
    val official_name: String? = null,
    val relationship_id: Int? = null,
    val started_at: String? = null,
    val ended_at: String? = null,
    val duration_seconds: Int? = null,
    val recording_status: String? = null,
    val identity_status: String? = null,
    val processing_status: String? = null,
    val reminder_at: String? = null
)

@Serializable
data class CallSessionDetailDto(
    val id: Int,
    val dc_user_id: Int,
    val dc_user_name: String,
    val direction: String,
    val phone_ref: String? = null,
    val official_id: Int? = null,
    val official_name: String? = null,
    val relationship_id: Int? = null,
    val started_at: String? = null,
    val ended_at: String? = null,
    val duration_seconds: Int? = null,
    val recording_status: String? = null,
    val identity_status: String? = null,
    val processing_status: String? = null,
    val reminder_at: String? = null,
    val transcript_text: String? = null,
    val transcript_source: String? = null,
    val brief: CallBriefDto? = null,
    val recording_status_detail: String? = null
)

@Serializable
data class OutgoingCallRequestDto(
    val official_id: Int
)

@Serializable
data class CallSessionListResponseDto(
    val items: List<CallSessionSummaryDto>,
    val total: Int
)

@Serializable
data class ManualTextRequestDto(
    val text: String
)

@Serializable
data class IdentityLinkRequestDto(
    val official_id: Int,
    val update_phone: Boolean
)

@Serializable
data class IdentityCreateRequestDto(
    val name: String,
    val phone: String? = null,
    val designation: String? = null,
    val department: String? = null,
    val level: String? = null,
    val location: String? = null
)

@Serializable
data class ConfirmRequestDto(
    val brief: CallBriefDto,
    val identity_action: String = "link"
)

@Serializable
data class RemindLaterRequestDto(
    val hours: Int? = null
)
