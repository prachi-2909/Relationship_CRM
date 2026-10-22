package com.eko.rcrm.dc.nativecall.recording

import android.content.Context
import android.os.ParcelFileDescriptor
import android.util.Log
import com.eko.rcrm.dc.data.local.CallAudioStore
import com.eko.rcrm.dc.data.local.CallRecordingPrefs
import com.eko.rcrm.dc.recorder.RecorderBackend
import com.eko.rcrm.dc.recorder.RecorderConnection
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/** Two-sided call recording via the privileged (Shizuku-hosted) recorder ported from CallVault. This
 * is the engine that captures BOTH sides of a phone call (VOICE_CALL), the capability the mic-only
 * engine cannot provide. Requires the Shizuku app installed and permission granted; when it isn't,
 * reports UNSUPPORTED and the pipeline falls back exactly as before. */
@Singleton
class PrivilegedRecordingEngine @Inject constructor(
    @ApplicationContext private val context: Context,
    private val callAudioStore: CallAudioStore,
    private val callRecordingPrefs: CallRecordingPrefs
) : RecordingEngine {

    override val id: String = ENGINE_ID

    private var activeFile: File? = null
    private var activeSessionId: Int? = null
    private var startedAtMs: Long = 0L

    override fun getCapability(): RecordingCapability {
        val mode = callRecordingPrefs.privilegedMode
        val readiness = RecorderBackend.readiness(context, mode)
        val ready = readiness == RecorderBackend.Readiness.READY
        return RecordingCapability(
            level = if (ready) RecordingCapabilityLevel.SUPPORTED else RecordingCapabilityLevel.UNSUPPORTED,
            engineId = ENGINE_ID,
            reason = if (ready) {
                "Both sides of the call are recorded via the privileged recorder ($mode)."
            } else {
                "Two-way recording isn't set up on this device yet ($mode: $readiness). Set it up on " +
                    "the Recording Capability screen."
            }
        )
    }

    override suspend fun start(callSessionId: Int): RecordingResult = withContext(Dispatchers.IO) {
        val capability = getCapability()
        if (capability.level != RecordingCapabilityLevel.SUPPORTED) {
            return@withContext RecordingResult.Unavailable(capability.reason)
        }
        if (!RecorderBackend.ensureRunning(context, callRecordingPrefs.privilegedMode)) {
            return@withContext RecordingResult.Unavailable("The privileged recorder could not be started.")
        }
        val service = RecorderConnection.service
            ?: return@withContext RecordingResult.Unavailable("No recorder connection.")

        val dir = callAudioStore.recordingsDir.apply { mkdirs() }
        val out = File(dir, "callrec_${callSessionId}_${System.currentTimeMillis()}.ogg")
        val result = runCatching {
            ParcelFileDescriptor.open(
                out,
                ParcelFileDescriptor.MODE_CREATE or ParcelFileDescriptor.MODE_READ_WRITE or ParcelFileDescriptor.MODE_TRUNCATE
            ).use { pfd ->
                service.startRecording("voice-call", "opus", 24_000, pfd)
            }
        }
        if (result.isFailure) {
            out.delete()
            return@withContext RecordingResult.Failed(
                result.exceptionOrNull()?.message ?: "Could not start privileged recording",
                result.exceptionOrNull()
            )
        }
        activeFile = out
        activeSessionId = callSessionId
        startedAtMs = System.currentTimeMillis()
        RecordingResult.Started(capability)
    }

    override suspend fun stop(callSessionId: Int): RecordingResult = withContext(Dispatchers.IO) {
        val file = activeFile
        if (file == null || activeSessionId != callSessionId) {
            return@withContext RecordingResult.Unavailable("No privileged recording was in progress for this call.")
        }
        activeFile = null
        activeSessionId = null
        val seconds = ((System.currentTimeMillis() - startedAtMs) / 1000).toInt()
        runCatching { RecorderConnection.service?.stopRecording() }
            .onFailure { Log.w(TAG, "stopRecording failed: ${it.message}") }
        if (!file.exists() || file.length() < MIN_BYTES || seconds < MIN_SECONDS) {
            file.delete()
            return@withContext RecordingResult.NoUsableAudio(
                "Captured ${seconds}s but no usable audio - the OS may have refused the call stream on this device."
            )
        }
        RecordingResult.Stopped(file, seconds, getCapability())
    }

    override fun purge(callSessionId: Int) {
        if (activeSessionId == callSessionId) {
            runCatching { RecorderConnection.service?.stopRecording() }
            activeFile?.delete()
            activeFile = null
            activeSessionId = null
        }
    }

    companion object {
        const val ENGINE_ID = "privileged_shizuku"
        private const val TAG = "RCRM:PrivEngine"
        private const val MIN_SECONDS = 1
        private const val MIN_BYTES = 1024L
    }
}
