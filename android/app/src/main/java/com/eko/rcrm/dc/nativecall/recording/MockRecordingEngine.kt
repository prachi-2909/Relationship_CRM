package com.eko.rcrm.dc.nativecall.recording

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/** Exercises the full CallSession -> recording -> upload -> transcription -> AI -> review ->
 * CRM-logging -> purge pipeline without touching the microphone or any real call - a short
 * silent audio file stands in for a capture. For development/testing only; never wired up in a
 * release build (see RecordingEngineProvider). Always reports SUPPORTED so the pipeline can be
 * tested as if a privileged/provider engine were plugged in. */
@Singleton
class MockRecordingEngine @Inject constructor(
    @ApplicationContext private val context: Context
) : RecordingEngine {

    override val id: String = ENGINE_ID

    private var startedAtMs: Long? = null
    private var activeSessionId: Int? = null

    override fun getCapability(): RecordingCapability = RecordingCapability(
        level = RecordingCapabilityLevel.SUPPORTED,
        engineId = ENGINE_ID,
        reason = "Mock engine for development/testing - simulates a successful two-way recording " +
            "without using the microphone or capturing a real call. Never used in a release build."
    )

    override suspend fun start(callSessionId: Int): RecordingResult {
        startedAtMs = System.currentTimeMillis()
        activeSessionId = callSessionId
        return RecordingResult.Started(getCapability())
    }

    override suspend fun stop(callSessionId: Int): RecordingResult {
        val started = startedAtMs
        if (started == null || activeSessionId != callSessionId) {
            return RecordingResult.Unavailable("No mock recording was in progress for this call.")
        }
        startedAtMs = null
        activeSessionId = null
        val seconds = ((System.currentTimeMillis() - started) / 1000).toInt().coerceAtLeast(1)
        val file = writeSilentPlaceholder(callSessionId)
        return RecordingResult.Stopped(file, seconds, getCapability())
    }

    override fun purge(callSessionId: Int) {
        File(context.cacheDir, fileName(callSessionId)).delete()
    }

    /** A tiny, technically-valid M4A so the real upload/transcription path can be driven
     * end-to-end; the transcription service will fail to extract speech from it, which is the
     * correct outcome for silence and exercises that failure/retry path too. */
    private fun writeSilentPlaceholder(callSessionId: Int): File {
        val file = File(context.cacheDir, fileName(callSessionId))
        file.outputStream().use { it.write(MINIMAL_M4A_HEADER) }
        return file
    }

    private fun fileName(callSessionId: Int) = "mock_recording_$callSessionId.m4a"

    companion object {
        const val ENGINE_ID = "mock"

        // Minimal valid MPEG-4/M4A "ftyp" box - enough for the file to be recognised as audio by
        // format-sniffing on the way through the upload pipeline; it carries no actual audio.
        private val MINIMAL_M4A_HEADER = byteArrayOf(
            0x00, 0x00, 0x00, 0x18, 0x66, 0x74, 0x79, 0x70,
            0x4D, 0x34, 0x41, 0x20, 0x00, 0x00, 0x00, 0x00,
            0x4D, 0x34, 0x41, 0x20, 0x6D, 0x70, 0x34, 0x32
        )
    }
}
