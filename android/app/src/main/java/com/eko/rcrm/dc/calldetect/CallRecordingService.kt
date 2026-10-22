package com.eko.rcrm.dc.calldetect

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.eko.rcrm.dc.R
import com.eko.rcrm.dc.data.local.db.PendingUploadKind
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.nativecall.CallPhoneState
import com.eko.rcrm.dc.nativecall.CallStateObserver
import com.eko.rcrm.dc.nativecall.provideCallStateObserver
import com.eko.rcrm.dc.nativecall.recording.CrmRecordingGate
import com.eko.rcrm.dc.nativecall.recording.RecordingCapabilityLevel
import com.eko.rcrm.dc.nativecall.recording.RecordingEngine
import com.eko.rcrm.dc.nativecall.recording.RecordingEngineProvider
import com.eko.rcrm.dc.nativecall.recording.RecordingResult
import com.eko.rcrm.dc.util.Result
import com.eko.rcrm.dc.work.UploadScheduler
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.time.Instant
import javax.inject.Inject

/** Records a call that was NOT placed from the app's own Call button - an answered incoming call, or
 * a call dialed from the phone's dialer. Recording only ever starts once the call is actually
 * answered (this service is started on the answered transition), and only when the number is a CRM
 * official in the DC's territory ([CrmRecordingGate]); a call that was never answered never reaches
 * here, so nothing is recorded for it. On end, a usable recording is logged + uploaded; a silent /
 * too-short take is discarded. An app-placed call is left to NativeCallForegroundService (guarded by
 * the armed-native-call check) so it is never recorded twice. */
@AndroidEntryPoint
class CallRecordingService : Service() {

    @Inject lateinit var callRepository: CallRepository
    @Inject lateinit var crmRecordingGate: CrmRecordingGate
    @Inject lateinit var engineProvider: RecordingEngineProvider
    @Inject lateinit var uploadScheduler: UploadScheduler

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val lock = Mutex()
    private var observer: CallStateObserver? = null
    private var engine: RecordingEngine? = null
    private var tempId = 0
    private var number: String? = null
    private var direction = "inbound"
    private var answeredAtMs = 0L
    @Volatile private var started = false
    @Volatile private var ended = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        number = intent?.getStringExtra(EXTRA_NUMBER)
        direction = intent?.getStringExtra(EXTRA_DIRECTION) ?: "inbound"
        answeredAtMs = intent?.getLongExtra(EXTRA_ANSWERED_AT, System.currentTimeMillis()) ?: System.currentTimeMillis()
        tempId = (answeredAtMs and 0x7fffffff).toInt()
        startForegroundNotification()
        engine = engineProvider.currentEngine()
        scope.launch { beginIfAllowed() }
        runCatching { observer = provideCallStateObserver(this).also { it.start(::onState) } }
        return START_NOT_STICKY
    }

    private suspend fun beginIfAllowed() {
        // An app-placed call records through NativeCallForegroundService; don't double-record it.
        if (runCatching { callRepository.hasActiveArmedNativeCall() }.getOrDefault(false)) { finish(); return }
        val level = engine?.getCapability()?.level
        if (level == null || level == RecordingCapabilityLevel.UNSUPPORTED) { finish(); return }
        // CRM-only: never record a number that isn't a CRM official in this DC's territory.
        if (crmRecordingGate.check(number) !is CrmRecordingGate.Decision.Allowed) { finish(); return }
        lock.withLock { if (!ended) { engine?.start(tempId); started = true } }
    }

    private fun onState(state: CallPhoneState) {
        if (state == CallPhoneState.IDLE) finish()
    }

    private fun finish() {
        if (ended) return
        ended = true
        observer?.stop(); observer = null
        scope.launch {
            val result = lock.withLock { if (started) engine?.stop(tempId) else null }
            val endMs = System.currentTimeMillis()
            val durationSec = ((endMs - answeredAtMs) / 1000).toInt().coerceAtLeast(0)
            val num = number
            // If the call wasn't actually answered (only rang), discard the recording and don't log
            // it - a missed/rejected call must never reach the CRM queue. Unknown (no call-log
            // permission) falls through so real calls are never lost.
            val answer = CallLogReader.awaitAnswer(applicationContext, num, answeredAtMs)
            if (answer?.answered == false) {
                (result as? RecordingResult.Stopped)?.file?.delete()
                runCatching { androidx.core.app.ServiceCompat.stopForeground(this@CallRecordingService, androidx.core.app.ServiceCompat.STOP_FOREGROUND_REMOVE) }
                stopSelf()
                return@launch
            }
            // Outgoing (dialer) call: trim the ring-back off the front; incoming already starts at answer.
            var stopped = result
            val talk = answer?.durationSec ?: 0
            if (stopped is RecordingResult.Stopped && direction == "outbound" && talk > 0) {
                val trimmed = CallAudioTrimmer.keepLastSeconds(stopped.file, talk)
                stopped = RecordingResult.Stopped(trimmed, talk, stopped.capability)
            }
            if (stopped is RecordingResult.Stopped && num != null) {
                val logged = callRepository.logNativeCall(
                    phone = num,
                    startedAtIso = Instant.ofEpochMilli(answeredAtMs).toString(),
                    endedAtIso = Instant.ofEpochMilli(endMs).toString(),
                    durationSeconds = durationSec,
                    direction = direction,
                    manual = false,
                )
                if (logged is Result.Success) {
                    val sessionId = logged.data.id
                    val upload = callRepository.uploadVoiceNoteFile(sessionId, stopped.file, PendingUploadKind.CALL_RECORDING)
                    if (upload is Result.Error && !callRepository.isPermanentRejection(upload)) {
                        val uploadId = callRepository.enqueueVoiceNoteUpload(sessionId, stopped.file.absolutePath, PendingUploadKind.CALL_RECORDING)
                        uploadScheduler.enqueueUpload(uploadId)
                    }
                }
            }
            runCatching { androidx.core.app.ServiceCompat.stopForeground(this@CallRecordingService, androidx.core.app.ServiceCompat.STOP_FOREGROUND_REMOVE) }
            stopSelf()
        }
    }

    override fun onDestroy() {
        observer?.stop()
        scope.cancel()
        super.onDestroy()
    }

    private fun startForegroundNotification() {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "Call recording", NotificationManager.IMPORTANCE_LOW))
        }
        val n: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Call in progress")
            .setContentText("Recording is ON for this CRM call - make sure the other person knows.")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            // Must include MICROPHONE: the mic-fallback engine opens the microphone, and on
            // targetSdk 34+ a mic-using FGS declared dataSync-only is denied while-in-use mic access
            // (silent, discarded take). The privileged engine doesn't need it, but declaring both is
            // correct for either engine. Matches NativeCallForegroundService.
            startForeground(
                NOTIFICATION_ID, n,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE,
            )
        } else {
            startForeground(NOTIFICATION_ID, n)
        }
    }

    companion object {
        private const val CHANNEL_ID = "call_recording"
        private const val NOTIFICATION_ID = 7351
        private const val EXTRA_NUMBER = "number"
        private const val EXTRA_DIRECTION = "direction"
        private const val EXTRA_ANSWERED_AT = "answered_at"

        fun start(context: Context, number: String?, direction: String, answeredAtMs: Long) {
            val intent = Intent(context, CallRecordingService::class.java)
                .putExtra(EXTRA_NUMBER, number)
                .putExtra(EXTRA_DIRECTION, direction)
                .putExtra(EXTRA_ANSWERED_AT, answeredAtMs)
            androidx.core.content.ContextCompat.startForegroundService(context, intent)
        }
    }
}
