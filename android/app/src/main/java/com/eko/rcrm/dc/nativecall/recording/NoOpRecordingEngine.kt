package com.eko.rcrm.dc.nativecall.recording

import javax.inject.Inject
import javax.inject.Singleton

/** The safe default: attempts nothing, and says so. Used whenever no engine with real
 * capability is configured - the call still proceeds normally, and CallSession ends up
 * RECORDING_UNAVAILABLE rather than the app pretending otherwise. */
@Singleton
class NoOpRecordingEngine @Inject constructor() : RecordingEngine {
    override val id: String = ENGINE_ID

    override fun getCapability(): RecordingCapability = RecordingCapability(
        level = RecordingCapabilityLevel.UNSUPPORTED,
        engineId = ENGINE_ID,
        reason = "No recording engine is configured for native-SIM calls on this device. " +
            "Android reserves the call's own audio stream (CAPTURE_AUDIO_OUTPUT / VOICE_CALL) for " +
            "privileged, pre-installed system apps - a normal installed app cannot be granted it " +
            "without rooting the device or bypassing Android's security model, which this app does " +
            "not do. The call still proceeds; add a recap from Call Review afterwards."
    )

    override suspend fun start(callSessionId: Int): RecordingResult =
        RecordingResult.Unavailable(getCapability().reason)

    override suspend fun stop(callSessionId: Int): RecordingResult =
        RecordingResult.Unavailable(getCapability().reason)

    override fun purge(callSessionId: Int) {
        // Nothing was ever captured.
    }

    companion object {
        const val ENGINE_ID = "noop"
    }
}
