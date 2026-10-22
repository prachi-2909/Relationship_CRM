package com.eko.rcrm.dc.data.local

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/** Every place this app keeps call audio on the phone, and the one way to delete it. Audio
 * exists only to be uploaded and transcribed (DPDP Act data minimisation): it is deleted as
 * soon as the server has it, again when the call is logged into the CRM, when an upload is
 * given up on, and - as a backstop for anything those miss - once older than [MAX_AGE_MS].
 *
 * Locations, by file-name convention (`<prefix>_<callSessionId>_...` / `<prefix>_<callSessionId>.<ext>`):
 *  - filesDir/voice_notes/callrec_<id>_<ms>.*  - the call itself, from a RecordingEngine
 *  - filesDir/voice_notes/voicenote_<id>_<ms>.* - the DC's own recap
 *  - cacheDir/voice_note_review_<id>.m4a        - Call Review's playback copy
 *  - cacheDir/callrec_<id>.<ext>                - RecordingImporter's upload copy
 * voice_notes/ is also excluded from Android backup (res/xml/backup_rules.xml). */
@Singleton
class CallAudioStore @Inject constructor(
    @ApplicationContext private val context: Context
) {
    val recordingsDir: File
        get() = File(context.filesDir, RECORDINGS_DIR)

    fun reviewPlaybackFile(callSessionId: Int): File =
        File(context.cacheDir, "voice_note_review_$callSessionId.m4a")

    /** Deletes every local copy of [callSessionId]'s audio. */
    fun purgeCall(callSessionId: Int) {
        val id = callSessionId.toString()
        audioFiles().filter { it.name.belongsTo(id) }.forEach { it.delete() }
    }

    /** Deletes ALL call audio this app holds - used when wiping local data on logout/session end. */
    fun purgeAll() {
        audioFiles().forEach { it.delete() }
    }

    /** Backstop for anything the event-driven deletes missed (a crash mid-upload, a call that
     * was never reviewed): removes audio older than [maxAgeMs], whatever state it was left in. */
    fun purgeOlderThan(maxAgeMs: Long = MAX_AGE_MS, nowMs: Long = System.currentTimeMillis()) {
        audioFiles().filter { nowMs - it.lastModified() > maxAgeMs }.forEach { it.delete() }
    }

    private fun audioFiles(): List<File> {
        val recordings = recordingsDir.listFiles()?.filter { it.isFile }.orEmpty()
        val cached = context.cacheDir.listFiles()?.filter { file ->
            file.isFile && CACHE_PREFIXES.any { file.name.startsWith(it) }
        }.orEmpty()
        return recordings + cached
    }

    /** `callrec_12_1700000000000.m4a`, `voice_note_review_12.m4a`, `callrec_12.ogg` all belong to
     * call 12; `callrec_120_...` does not. */
    private fun String.belongsTo(id: String): Boolean {
        val rest = PREFIXES.firstOrNull { startsWith(it) }?.let { removePrefix(it) } ?: return false
        return rest.startsWith("${id}_") || rest.startsWith("$id.")
    }

    companion object {
        const val RECORDINGS_DIR = "voice_notes"
        /** Matches the server's unconfirmed_call_audio_retention_days. */
        const val MAX_AGE_MS = 7L * 24 * 60 * 60 * 1000
        private val CACHE_PREFIXES = listOf("voice_note_review_", "callrec_")
        private val PREFIXES = listOf("voice_note_review_", "voicenote_", "callrec_")
    }
}
