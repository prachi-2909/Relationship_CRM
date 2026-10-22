package com.eko.rcrm.dc.nativecall.recording

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import com.eko.rcrm.dc.nativecall.CallMicRecorder
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import javax.inject.Inject
import javax.inject.Singleton

/** Microphone-only capture during a native-SIM call: the one capability actually available to
 * a normal, non-privileged Android app (see [RecordingEngine] for why true call-audio capture
 * is not). Reliably gets the DC's own voice; the other party only if the call is on speaker,
 * and on many phones the OS mutes third-party mic capture for the whole call regardless - a
 * silent or too-short take is reported as [RecordingResult.NoUsableAudio], never uploaded as if
 * it were a real recording. Confirmed experimentally silent on at least one tested device
 * (Motorola Edge 70 Fusion, Android 16); other devices may behave differently, which is why
 * this stays PARTIALLY_SUPPORTED rather than UNSUPPORTED - the per-call amplitude check is the
 * real, final answer, not this static capability label. */
@Singleton
class MicRecordingEngine @Inject constructor(
    @ApplicationContext private val context: Context
) : RecordingEngine {

    override val id: String = ENGINE_ID

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var recorder: CallMicRecorder? = null
    private var activeSessionId: Int? = null

    override fun getCapability(): RecordingCapability {
        val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED
        return RecordingCapability(
            level = if (granted) RecordingCapabilityLevel.PARTIALLY_SUPPORTED else RecordingCapabilityLevel.UNSUPPORTED,
            engineId = ENGINE_ID,
            reason = if (granted) {
                "Microphone-only capture (experimental). Reliably captures the DC's own voice; the " +
                    "other party only if the call is on speaker. Many phones mute third-party mic " +
                    "capture during a call entirely - each recording is checked for actual sound " +
                    "before it is kept, so a silent attempt is discarded rather than uploaded."
            } else {
                "Microphone permission is not granted, so even partial capture is unavailable."
            }
        )
    }

    override suspend fun start(callSessionId: Int): RecordingResult {
        val capability = getCapability()
        if (capability.level == RecordingCapabilityLevel.UNSUPPORTED) {
            return RecordingResult.Unavailable(capability.reason)
        }
        val r = CallMicRecorder(context)
        val error = r.start(scope, callSessionId)
        if (error != null) {
            return RecordingResult.Failed(error.message ?: "Could not start microphone recording", error)
        }
        recorder = r
        activeSessionId = callSessionId
        return RecordingResult.Started(capability)
    }

    override suspend fun stop(callSessionId: Int): RecordingResult {
        val r = recorder
        if (r == null || activeSessionId != callSessionId) {
            return RecordingResult.Unavailable("No recording was in progress for this call.")
        }
        recorder = null
        activeSessionId = null
        val outcome = r.stop()
        val file = outcome.file
        if (file == null || outcome.seconds < MIN_SECONDS || outcome.peakAmplitude < SILENCE_PEAK_THRESHOLD) {
            file?.delete()
            val reason = outcome.error?.let { "${it.javaClass.simpleName}: ${it.message}" }
                ?: "Captured ${outcome.seconds}s but the microphone was silent (peak ${outcome.peakAmplitude}) - " +
                    "this phone likely mutes third-party mic capture during calls."
            return RecordingResult.NoUsableAudio(reason)
        }
        return RecordingResult.Stopped(file, outcome.seconds, getCapability())
    }

    override fun purge(callSessionId: Int) {
        if (activeSessionId == callSessionId) {
            recorder?.stop()
            recorder = null
            activeSessionId = null
        }
    }

    companion object {
        const val ENGINE_ID = "mic_experimental"
        private const val MIN_SECONDS = 3
        // MediaRecorder.getMaxAmplitude() tops out at 32767; room noise alone is typically in the
        // low hundreds, a spoken voice well above a thousand.
        private const val SILENCE_PEAK_THRESHOLD = 800
    }
}
