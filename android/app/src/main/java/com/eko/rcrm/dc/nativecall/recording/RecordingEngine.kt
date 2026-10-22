package com.eko.rcrm.dc.nativecall.recording

import java.io.File

/** How much of "both sides of this call" an engine can actually capture, and why. Android
 * restricts the call's own audio stream (VOICE_CALL / CAPTURE_AUDIO_OUTPUT) to privileged,
 * pre-installed system apps - no third-party app, including this one, can be granted that
 * without the device being rooted or its security model bypassed, which this app will not do.
 * Every engine reports this honestly instead of pretending a mic-only capture is a real
 * two-way recording. */
enum class RecordingCapabilityLevel {
    /** True two-way call audio. Not achievable by this app on a normal, non-privileged
     * installation - reserved for a future OEM/provider-backed engine that is actually entitled
     * to the privileged audio source. */
    SUPPORTED,

    /** Captures only what the phone's microphone can pick up (the DC's own voice reliably; the
     * other party only if the call is on speaker, and even then not guaranteed). Never
     * presented to the DC as a full recording - see [RecordingCapability.reason]. */
    PARTIALLY_SUPPORTED,

    /** No capture is attempted. The call still proceeds normally; CallSession is marked
     * RECORDING_UNAVAILABLE and the DC falls back to the existing voice-note/manual-text recap. */
    UNSUPPORTED,

    /** Not yet determined (e.g. the permission prompt hasn't been answered). */
    UNKNOWN
}

data class RecordingCapability(
    val level: RecordingCapabilityLevel,
    val engineId: String,
    val reason: String,
    val manufacturer: String = android.os.Build.MANUFACTURER,
    val model: String = android.os.Build.MODEL,
    val androidVersion: String = android.os.Build.VERSION.RELEASE,
    val sdkInt: Int = android.os.Build.VERSION.SDK_INT
)

sealed interface RecordingResult {
    data class Started(val capability: RecordingCapability) : RecordingResult
    data class Stopped(val file: File, val seconds: Int, val capability: RecordingCapability) : RecordingResult
    /** Captured something, but it didn't meet the quality bar to be worth uploading (e.g.
     * silence, because the OS muted the mic for the call) - not an error, just nothing usable. */
    data class NoUsableAudio(val reason: String) : RecordingResult
    data class Unavailable(val reason: String) : RecordingResult
    data class Failed(val reason: String, val cause: Throwable? = null) : RecordingResult
}

/** One capture mechanism, behind one interface, so the CRM's call-tracking code
 * (NativeCallForegroundService) never has to know which mechanism is active. A future
 * OEM-partnership or cloud-provider-backed implementation plugs in here without touching
 * anything else - the call-tracking/transcription/review/CRM-logging pipeline is unaffected
 * either way, since it already treats "no recording" as a normal, first-class case. */
interface RecordingEngine {
    val id: String

    /** Cheap, synchronous, side-effect-free - callable any time to decide what to show the DC,
     * without starting anything. */
    fun getCapability(): RecordingCapability

    /** Begins capture for [callSessionId]. Returns [RecordingResult.Unavailable] rather than
     * throwing when the engine cannot run right now (permission missing, etc.). */
    suspend fun start(callSessionId: Int): RecordingResult

    /** Ends capture and returns what was captured, or why nothing usable was. Always safe to
     * call even if [start] was never called or already failed. */
    suspend fun stop(callSessionId: Int): RecordingResult

    /** Deletes any temporary file this engine is still holding for [callSessionId]. Safe to
     * call even if nothing is held. */
    fun purge(callSessionId: Int)
}
