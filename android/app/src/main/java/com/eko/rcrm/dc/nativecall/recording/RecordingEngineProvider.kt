package com.eko.rcrm.dc.nativecall.recording

import com.eko.rcrm.dc.BuildConfig
import com.eko.rcrm.dc.data.local.CallRecordingPrefs
import javax.inject.Inject
import javax.inject.Singleton

/** The one place that decides which [RecordingEngine] handles the next call. Everything else
 * (NativeCallForegroundService, the capability screen) asks this rather than constructing an
 * engine itself - swapping in a future OEM/provider-backed engine is a change here only. */
@Singleton
class RecordingEngineProvider @Inject constructor(
    private val privilegedRecordingEngine: PrivilegedRecordingEngine,
    private val micRecordingEngine: MicRecordingEngine,
    private val mockRecordingEngine: MockRecordingEngine,
    private val noOpRecordingEngine: NoOpRecordingEngine,
    private val callRecordingPrefs: CallRecordingPrefs
) {
    /** True in debug builds only, and only once explicitly turned on - keeps an accidental
     * production dependency on fabricated recordings impossible by construction. */
    var useMockEngineForTesting: Boolean = false

    fun currentEngine(): RecordingEngine = when {
        BuildConfig.DEBUG && useMockEngineForTesting -> mockRecordingEngine
        !callRecordingPrefs.enabled -> noOpRecordingEngine
        // Prefer true two-sided capture when the privileged (Shizuku) recorder is actually available
        // on this device; otherwise fall back to the mic-only engine, same as before.
        privilegedRecordingEngine.getCapability().level == RecordingCapabilityLevel.SUPPORTED ->
            privilegedRecordingEngine
        else -> micRecordingEngine
    }

    /** For the capability screen: every engine this build could use, regardless of whether the
     * DC has opted into it, so the screen can explain each one rather than just the active one. */
    fun allEngines(): List<RecordingEngine> = buildList {
        add(noOpRecordingEngine)
        add(privilegedRecordingEngine)
        add(micRecordingEngine)
        if (BuildConfig.DEBUG) add(mockRecordingEngine)
    }
}
