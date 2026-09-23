package com.eko.rcrm.dc.navigation

object Routes {
    const val LOGIN = "login"
    const val HOME = "home"
    const val OFFICIAL_SEARCH = "official_search"
    const val PENDING_QUEUE = "pending_queue"
    const val CALL_HISTORY = "call_history"

    const val CALL_REVIEW_ARG = "callSessionId"
    const val CALL_REVIEW = "call_review/{$CALL_REVIEW_ARG}"
    const val VOICE_NOTE_RECORDING = "voice_note_recording/{$CALL_REVIEW_ARG}"
    const val MANUAL_TEXT_ENTRY = "manual_text_entry/{$CALL_REVIEW_ARG}"

    fun callReview(callSessionId: Int) = "call_review/$callSessionId"
    fun voiceNoteRecording(callSessionId: Int) = "voice_note_recording/$callSessionId"
    fun manualTextEntry(callSessionId: Int) = "manual_text_entry/$callSessionId"
}
