package com.eko.rcrm.dc.nativecall

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.eko.rcrm.dc.R
import com.eko.rcrm.dc.data.local.db.PendingUploadKind
import com.eko.rcrm.dc.calldetect.CallAudioTrimmer
import com.eko.rcrm.dc.calldetect.CallLogReader
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.nativecall.recording.CrmRecordingGate
import com.eko.rcrm.dc.nativecall.recording.RecordingCapabilityLevel
import com.eko.rcrm.dc.nativecall.recording.RecordingEngine
import com.eko.rcrm.dc.nativecall.recording.RecordingEngineProvider
import com.eko.rcrm.dc.nativecall.recording.RecordingResult
import com.eko.rcrm.dc.util.Result
import com.eko.rcrm.dc.work.UploadScheduler
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.time.Instant
import javax.inject.Inject

/** Started the instant the DC's device dials a native-SIM call (ACTION_CALL) and stopped once
 * the call ends. Survives OEM background-kill behavior for the call's duration, times it via
 * [CallStateObserver], and delegates recording to whichever [RecordingEngine]
 * [RecordingEngineProvider] currently selects - this class never assumes a specific capture
 * mechanism, so a future OEM/provider-backed engine plugs in without touching it. */
@AndroidEntryPoint
class NativeCallForegroundService : Service() {

    @Inject
    lateinit var callRepository: CallRepository

    @Inject
    lateinit var uploadScheduler: UploadScheduler

    @Inject
    lateinit var recordingEngineProvider: RecordingEngineProvider

    @Inject
    lateinit var crmRecordingGate: CrmRecordingGate

    private var activeRecordingEngine: RecordingEngine? = null

    /** The CRM-only rule's answer for this call, asked as soon as the call is dialed so it is
     * ready by the time the call connects. Null when the engine would not record anyway. */
    private var gateDecision: Deferred<CrmRecordingGate.Decision>? = null

    /** Why this call is not being recorded under the CRM-only rule, once decided. */
    @Volatile
    private var recordingDenial: String? = null

    /** Serialises engine start against stop, so a call that ends while the gate is still being
     * asked can never start a recorder after it has already been stopped. */
    private val recordingLock = Mutex()

    @Volatile
    private var callEnded = false

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var observer: CallStateObserver? = null
    private var timeoutJob: Job? = null

    private var callSessionId: Int = -1
    private var phone: String? = null
    private var hasLeftIdle = false
    private var hasConnected = false
    private var connectedAtEpochMs: Long = 0L

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val sessionId = intent?.getIntExtra(EXTRA_CALL_SESSION_ID, -1) ?: -1
        if (sessionId == -1) {
            stopSelf()
            return START_NOT_STICKY
        }
        callSessionId = sessionId
        phone = intent?.getStringExtra(EXTRA_PHONE)
        activeRecordingEngine = recordingEngineProvider.currentEngine()
        val wouldRecord = activeRecordingEngine?.getCapability()?.level
            .let { it != null && it != RecordingCapabilityLevel.UNSUPPORTED }
        if (wouldRecord) {
            val dialed = phone
            gateDecision = scope.async {
                crmRecordingGate.check(dialed).also { decision ->
                    // Only now - with the number confirmed as a CRM contact - tell the DC it is recorded.
                    if (decision is CrmRecordingGate.Decision.Allowed && !callEnded) {
                        getSystemService(NotificationManager::class.java)
                            .notify(NOTIFICATION_ID, buildNotification(recordingOn = true))
                    }
                }
            }
        }
        // This whole sequence rides on platform behavior (FGS-start eligibility, telephony
        // callback registration) that varies across OEM/API combinations we can't test here.
        // Losing duration/recording tracking is a minor degradation; crashing the app mid-call
        // isn't acceptable, so any failure here just ends this service quietly instead.
        try {
            startForegroundNotification()
            armTimeout()
            observer = provideCallStateObserver(this).also { it.start(::onStateChanged) }
        } catch (t: Throwable) {
            showNativeCallDiagnostic(this, "Native call tracking failed to start", t)
            stopSelf()
        }
        return START_NOT_STICKY
    }

    private fun onStateChanged(state: CallPhoneState) {
        when (state) {
            CallPhoneState.OFFHOOK -> {
                timeoutJob?.cancel()
                if (!hasConnected) {
                    hasConnected = true
                    connectedAtEpochMs = System.currentTimeMillis()
                    scope.launch { callRepository.markArmedNativeCallInProgress(callSessionId) }
                    startRecording()
                }
                hasLeftIdle = true
            }
            CallPhoneState.RINGING -> {
                hasLeftIdle = true
            }
            CallPhoneState.IDLE -> {
                if (hasLeftIdle) {
                    finishCall()
                }
            }
        }
    }

    private fun startRecording() {
        val engine = activeRecordingEngine ?: return
        val sessionId = callSessionId
        scope.launch {
            val decision = gateDecision?.await()
            val denial = when {
                decision is CrmRecordingGate.Decision.Denied -> decision.reason
                decision != null && !crmRecordingGate.isLoggedIn() -> "Logged out of the CRM app - not recorded."
                else -> null
            }
            if (denial != null) {
                recordingDenial = denial
                showNativeCallDiagnostic(this@NativeCallForegroundService, "Call not recorded", denial, RECORDING_DIAG_NOTIFICATION_ID)
                return@launch
            }
            val result = recordingLock.withLock {
                if (callEnded) return@launch
                engine.start(sessionId)
            }
            when (result) {
                is RecordingResult.Started -> Unit // nothing to show the DC yet; see finishCall
                is RecordingResult.Unavailable ->
                    showNativeCallDiagnostic(this@NativeCallForegroundService, "Recording unavailable", result.reason)
                is RecordingResult.Failed ->
                    showNativeCallDiagnostic(this@NativeCallForegroundService, "Recording failed to start", result.cause ?: RuntimeException(result.reason))
                else -> Unit
            }
        }
    }

    /** No OFFHOOK observed within this window (no answer, no signal, bad number) - treat it as
     * never connected rather than waiting indefinitely for an IDLE that may already have been
     * the starting state. */
    private fun armTimeout() {
        timeoutJob = scope.launch {
            kotlinx.coroutines.delay(NO_ANSWER_TIMEOUT_MS)
            if (!hasConnected) finishCall()
        }
    }

    private fun finishCall() {
        timeoutJob?.cancel()
        observer?.stop()
        observer = null
        callEnded = true
        val dialedPhone = phone
        val sessionId = callSessionId
        val engine = activeRecordingEngine
        // stopSelf() must wait until AFTER the report actually completes - calling it right
        // after launch{} (as this used to) tears the service, and this scope with it, down
        // immediately, silently cancelling the in-flight network request before it ever
        // reaches the server. This was why no call ever got its duration reported despite
        // the "ended" diagnostic always firing.
        scope.launch {
            // For an outgoing call, OFFHOOK fires at dial, not at answer - so confirm from the call
            // log whether the other side actually picked up. Not answered -> the call is cancelled,
            // never logged into the queue and never recorded. Unknown (no permission) -> keep the old
            // behaviour so a real call is never lost.
            val answer = if (hasConnected) {
                CallLogReader.awaitAnswer(this@NativeCallForegroundService, dialedPhone, connectedAtEpochMs)
            } else null
            // Unknown (no permission / entry not written) -> assume answered so a real call isn't lost.
            val answered = if (hasConnected) (answer?.answered ?: true) else false
            val connected = hasConnected && answered
            val durationSeconds = if (connected) {
                ((System.currentTimeMillis() - connectedAtEpochMs) / 1000).toInt()
            } else 0
            showNativeCallDiagnostic(this@NativeCallForegroundService, "Native call ended", "connected=$connected duration=${durationSeconds}s, reporting...")
            var recordingResult = recordingLock.withLock {
                val denial = recordingDenial
                when {
                    !connected || engine == null -> null
                    denial != null -> RecordingResult.Unavailable(denial)
                    else -> engine.stop(sessionId)
                }
            }
            // Outgoing call: OFFHOOK is dial time, so the recording starts during ringing. Trim the
            // ring-back off the front, keeping only the answered talk time the call log reports.
            val talk = answer?.durationSec ?: 0
            if (recordingResult is RecordingResult.Stopped && talk > 0) {
                val trimmed = CallAudioTrimmer.keepLastSeconds((recordingResult as RecordingResult.Stopped).file, talk)
                recordingResult = RecordingResult.Stopped(trimmed, talk, (recordingResult as RecordingResult.Stopped).capability)
            }
            val result = callRepository.completeNativeCall(
                callId = sessionId,
                endedAtIso = Instant.now().toString(),
                durationSeconds = durationSeconds,
                connected = connected,
                recordingEngineId = engine?.id,
                recordingCapabilityLevel = if (recordingDenial != null) {
                    RecordingCapabilityLevel.UNSUPPORTED.name
                } else {
                    recordingCapabilityLevelFor(recordingResult, engine)
                }
            )
            when (result) {
                is Result.Success -> showNativeCallDiagnostic(this@NativeCallForegroundService, "Call report sent OK", "duration=${durationSeconds}s")
                is Result.Error -> showNativeCallDiagnostic(this@NativeCallForegroundService, "Call report FAILED", result.message)
            }
            callRepository.clearArmedNativeCall()
            handleRecordingResult(sessionId, recordingResult)
            ServiceCompat.stopForeground(this@NativeCallForegroundService, ServiceCompat.STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    private fun recordingCapabilityLevelFor(result: RecordingResult?, engine: RecordingEngine?): String? = when (result) {
        is RecordingResult.Stopped -> result.capability.level.name
        is RecordingResult.NoUsableAudio -> RecordingCapabilityLevel.UNSUPPORTED.name
        is RecordingResult.Unavailable, is RecordingResult.Failed -> engine?.getCapability()?.level?.name
        else -> engine?.getCapability()?.level?.name
    }

    /** Uploads a successfully captured recording through the same voice-note path (so it gets
     * transcribed, briefed and reviewed like any other source) - every other outcome is a
     * normal, first-class case: nothing to record (never attempted), unavailable (engine
     * declined), or no usable audio (captured but not worth keeping). None of these are errors
     * the DC needs to act on beyond the existing voice-note/manual-text recap. */
    private suspend fun handleRecordingResult(sessionId: Int, result: RecordingResult?) {
        val ctx = this@NativeCallForegroundService
        when (result) {
            null -> return // call never connected, nothing was meant to record
            is RecordingResult.Unavailable ->
                showNativeCallDiagnostic(ctx, "Recording unavailable", result.reason, RECORDING_DIAG_NOTIFICATION_ID)
            is RecordingResult.NoUsableAudio ->
                showNativeCallDiagnostic(ctx, "Recording discarded", result.reason, RECORDING_DIAG_NOTIFICATION_ID)
            is RecordingResult.Failed ->
                showNativeCallDiagnostic(ctx, "Recording failed", result.cause ?: RuntimeException(result.reason), RECORDING_DIAG_NOTIFICATION_ID)
            is RecordingResult.Started -> Unit // stop() always supersedes this; nothing to do
            is RecordingResult.Stopped -> {
                val file = result.file
                val upload = callRepository.uploadVoiceNoteFile(sessionId, file, PendingUploadKind.CALL_RECORDING)
                when {
                    upload is Result.Success ->
                        showNativeCallDiagnostic(ctx, "Recording uploaded", "${result.seconds}s via ${result.capability.engineId}", RECORDING_DIAG_NOTIFICATION_ID)
                    callRepository.isPermanentRejection(upload) ->
                        // Already deleted by uploadVoiceNoteFile - e.g. the server found the number isn't a CRM contact.
                        showNativeCallDiagnostic(ctx, "Recording discarded", (upload as Result.Error).message, RECORDING_DIAG_NOTIFICATION_ID)
                    else -> {
                        val uploadId = callRepository.enqueueVoiceNoteUpload(sessionId, file.absolutePath, PendingUploadKind.CALL_RECORDING)
                        uploadScheduler.enqueueUpload(uploadId)
                        showNativeCallDiagnostic(ctx, "Recording queued for upload", "${result.seconds}s via ${result.capability.engineId}", RECORDING_DIAG_NOTIFICATION_ID)
                    }
                }
            }
        }
    }

    override fun onDestroy() {
        observer?.stop()
        timeoutJob?.cancel()
        activeRecordingEngine?.purge(callSessionId)
        scope.cancel()
        super.onDestroy()
    }

    private var notificationStartedAtMs = 0L

    /** "Recording is ON" only once the CRM-only rule has allowed it (see [gateDecision]) - until
     * then, and for any call it refuses, the DC is told the call is only being logged. */
    private fun buildNotification(recordingOn: Boolean) =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Call in progress")
            .setContentText(
                if (recordingOn) "Recording is ON - make sure the other person knows this call is recorded"
                else phone?.let { "Calling $it - logging for the CRM once it ends" }
                    ?: "Logging this call for the CRM once it ends"
            )
            .setSmallIcon(R.mipmap.ic_launcher)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            // Live ticking timer, starting right as the call is dialed - the same instant the
            // eventual reported duration is measured from, so what the DC watches count up here
            // is exactly what gets logged, dial time included.
            .setUsesChronometer(true)
            .setWhen(notificationStartedAtMs)
            .build()

    private fun startForegroundNotification() {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID, "Active call", NotificationManager.IMPORTANCE_LOW
            )
            manager.createNotificationChannel(channel)
        }
        val capability = activeRecordingEngine?.getCapability()
        val recording = capability?.level != null && capability.level != RecordingCapabilityLevel.UNSUPPORTED
        notificationStartedAtMs = System.currentTimeMillis()
        val notification = buildNotification(recordingOn = false)
        // dataSync, not phoneCall - see the manifest's <service> comment for why. The type
        // passed here must be a subset of what the manifest declares, or startForeground()
        // throws. The microphone type is added only when the active engine actually needs the
        // mic and has permission: declaring it without the permission throws SecurityException
        // and would take the whole call-tracking service down with it, so a recording engine's
        // state must never be able to break duration tracking.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            var types = ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            val micGranted = ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED
            if (recording && micGranted) types = types or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
            startForeground(NOTIFICATION_ID, notification, types)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    companion object {
        private const val CHANNEL_ID = "native_call"
        private const val NOTIFICATION_ID = 7341
        private const val RECORDING_DIAG_NOTIFICATION_ID = 7343
        private const val NO_ANSWER_TIMEOUT_MS = 45_000L
        private const val EXTRA_CALL_SESSION_ID = "call_session_id"
        private const val EXTRA_PHONE = "phone"

        fun intent(context: Context, callSessionId: Int, phone: String): Intent =
            Intent(context, NativeCallForegroundService::class.java)
                .putExtra(EXTRA_CALL_SESSION_ID, callSessionId)
                .putExtra(EXTRA_PHONE, phone)
    }
}
