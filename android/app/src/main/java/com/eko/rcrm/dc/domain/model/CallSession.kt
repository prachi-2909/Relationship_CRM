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
    val durationSource: String? = null,
    val recordingEngine: String? = null,
    val recordingCapabilityStatus: String? = null,
    // "knowlarity" | "manual" (DC calls from their own phone, Knowlarity-unconfigured) |
    // "android_native" (this device places the call itself via ACTION_CALL).
    val channel: String = "knowlarity",
    val recordingStatus: String?,
    val identityStatus: String?,
    val processingStatus: String?,
    val reminderAt: String?,
    // Detail-only fields, null when mapped from a summary-shaped response.
    val transcriptText: String? = null,
    val transcriptSource: String? = null,
    val brief: CallBrief? = null,
    val recordingStatusDetail: String? = null,
    val hasVoiceNote: Boolean = false
) {
    /** Mirrors the web app's canConfirm logic. A call already logged can still be
     * re-confirmed (e.g. after re-recording or editing the brief) - the backend
     * updates the same Interaction in place rather than duplicating it. */
    val canConfirm: Boolean
        get() = relationshipId != null && !transcriptText.isNullOrBlank()

    val isAlreadyLogged: Boolean
        get() = processingStatus == "crm_logged"

    /** True when this device must place the call itself (ACTION_CALL) rather than the
     * backend having already routed it through Knowlarity. */
    val isAndroidNative: Boolean
        get() = channel == "android_native"

    /** Identity resolution is needed only when there is no relationship on file yet. */
    val needsIdentityResolution: Boolean
        get() = relationshipId == null

    /** "2m 14s" / "43s" - null until the call has actually ended and reported a duration. */
    val formattedDuration: String?
        get() = durationSeconds?.let { seconds ->
            val minutes = seconds / 60
            val secs = seconds % 60
            val base = if (minutes > 0) "${minutes}m ${secs}s" else "${secs}s"
            // device_estimated (native-SIM calls): OFFHOOK->IDLE elapsed time, which
            // conflates ring-time and talk-time for a non-privileged observer - flagged
            // rather than presented as carrier-precise.
            if (durationSource == "device_estimated") "$base (approx.)" else base
        }

    /** "05 Oct, 02:43 pm" in the phone's own timezone. The backend sends UTC (with a "Z");
     * a value without any offset is treated as UTC too, since that's what it always is. */
    private fun formatTimestamp(raw: String?): String? {
        if (raw.isNullOrBlank()) return null
        return try {
            val instant = try {
                java.time.OffsetDateTime.parse(raw).toInstant()
            } catch (_: java.time.format.DateTimeParseException) {
                java.time.LocalDateTime.parse(raw).toInstant(java.time.ZoneOffset.UTC)
            }
            instant.atZone(java.time.ZoneId.systemDefault())
                .format(java.time.format.DateTimeFormatter.ofPattern("dd MMM, hh:mm a", java.util.Locale.ENGLISH))
        } catch (_: Throwable) {
            raw.replace("T", " ").take(16)
        }
    }

    private fun parseInstant(raw: String?): java.time.Instant? {
        if (raw.isNullOrBlank()) return null
        return try {
            try {
                java.time.OffsetDateTime.parse(raw).toInstant()
            } catch (_: java.time.format.DateTimeParseException) {
                java.time.LocalDateTime.parse(raw).toInstant(java.time.ZoneOffset.UTC)
            }
        } catch (_: Throwable) {
            null
        }
    }

    val startedAtInstant: java.time.Instant? get() = parseInstant(startedAt)
    val endedAtInstant: java.time.Instant? get() = parseInstant(endedAt)

    /** A finished call that has no recording or transcript yet - where a recording can still be attached. */
    val canAttachRecording: Boolean
        get() = endedAt != null && !hasVoiceNote && transcriptText.isNullOrBlank()

    val formattedStartedAt: String? get() = formatTimestamp(startedAt)
    val formattedEndedAt: String? get() = formatTimestamp(endedAt)
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
