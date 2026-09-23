package com.eko.rcrm.dc.domain.model

/**
 * Unified domain model for both CallSessionSummary and CallSessionDetail API shapes.
 * The detail-only fields are simply null when this was mapped from a summary response
 * (list/pending/history endpoints) rather than a single-call fetch.
 */
data class CallSession(
    val id: Int,
    val dcUserId: Int,
    val dcUserName: String,
    val direction: String,
    val phoneRef: String?,
    val officialId: Int?,
    val officialName: String?,
    val relationshipId: Int?,
    val startedAt: String?,
    val endedAt: String?,
    val durationSeconds: Int?,
    val recordingStatus: String?,
    val identityStatus: String?,
    val processingStatus: String?,
    val reminderAt: String?,
    // Detail-only fields, null when mapped from a summary-shaped response.
    val transcriptText: String? = null,
    val transcriptSource: String? = null,
    val brief: CallBrief? = null,
    val recordingStatusDetail: String? = null
) {
    /** Mirrors the web app's canConfirm logic. */
    val canConfirm: Boolean
        get() = relationshipId != null &&
            !transcriptText.isNullOrBlank() &&
            processingStatus != "crm_logged"

    /** Identity resolution is needed only when there is no relationship on file yet. */
    val needsIdentityResolution: Boolean
        get() = relationshipId == null
}

data class CallBrief(
    val summary: String = "",
    val keyPoints: List<String> = emptyList(),
    val decisions: List<String> = emptyList(),
    val commitments: List<String> = emptyList(),
    val actionItems: List<String> = emptyList(),
    val opportunities: List<String> = emptyList(),
    val relationshipSignals: List<String> = emptyList(),
    val suggestedNextInteraction: String = ""
)
