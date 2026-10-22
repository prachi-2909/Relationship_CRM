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
    val duration_source: String? = null,
    val recording_engine: String? = null,
    val recording_capability_status: String? = null,
    val channel: String = "knowlarity",
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
    val duration_source: String? = null,
    val recording_engine: String? = null,
    val recording_capability_status: String? = null,
    val channel: String = "knowlarity",
    val recording_status: String? = null,
    val identity_status: String? = null,
    val processing_status: String? = null,
    val reminder_at: String? = null,
    val transcript_text: String? = null,
    val transcript_source: String? = null,
    val brief: CallBriefDto? = null,
    val recording_status_detail: String? = null,
    val has_voice_note: Boolean = false
)

/** Reported by the device after a native-SIM call it placed itself ends - see
 * services/call_intelligence.py::complete_native_call on the backend. */
@Serializable
data class NativeCallCompleteRequestDto(
    val ended_at: String,
    val duration_seconds: Int,
    val connected: Boolean,
    val recording_engine: String? = null,
    val recording_capability_status: String? = null
)

/** A call on the DC's own SIM that didn't go through the in-app Call button - reported after
 * the fact, either auto-detected by the phone or entered by hand (manual = true). */
@Serializable
data class IncomingNativeCallRequestDto(
    val phone: String,
    val started_at: String,
    val ended_at: String,
    val duration_seconds: Int,
    val direction: String = "inbound",
    val manual: Boolean = false
)

@Serializable
data class CallerLookupResultDto(
    val official_id: Int,
    val name: String,
    val designation: String? = null,
    val organization_unit_name: String? = null
)

@Serializable
data class CallerLookupRequestDto(
    // Sent in the request body, never the URL, so the number stays out of server access logs.
    val phone: String
)

@Serializable
data class CallerLookupResponseDto(
    val official: CallerLookupResultDto? = null,
    // Server-authoritative: true for a Relationship Manager, who records EVERY call while logged in
    // (not CRM-gated). When true the app records even though the number is not a CRM official.
    val record_all: Boolean = false
)

/** Exactly one of official_id/phone is set - phone is the in-app manual dial pad. */
@Serializable
data class OutgoingCallRequestDto(
    val official_id: Int? = null,
    val phone: String? = null
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
