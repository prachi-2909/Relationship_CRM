package com.eko.rcrm.dc.calldetect

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.telephony.TelephonyManager
import androidx.work.Constraints
import androidx.work.Data
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager

/** Tracks when any call on this phone starts, connects and ends (via the PHONE_STATE
 * broadcast, which wakes the app even if it isn't running), and hands each finished call to
 * [CallDetectedWorker]. The broadcast itself carries no phone number without the restricted
 * call-log permission, so the number comes from [CrmCallScreeningService] via
 * [CallDetectionStore]. Whether the call is a CRM contact is decided in the worker - nothing
 * about non-CRM calls ever leaves the phone. */
class PhoneStateReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != TelephonyManager.ACTION_PHONE_STATE_CHANGED) return
        val state = intent.getStringExtra(TelephonyManager.EXTRA_STATE) ?: return
        val store = CallDetectionStore(context.applicationContext)
        val last = store.lastState
        // Devices commonly send each transition twice.
        if (state == last) return
        val now = System.currentTimeMillis()

        when (state) {
            TelephonyManager.EXTRA_STATE_RINGING -> {
                store.callStartMs = now
                store.answeredMs = 0L
                store.outgoing = false
            }
            TelephonyManager.EXTRA_STATE_OFFHOOK -> {
                if (last == TelephonyManager.EXTRA_STATE_RINGING) {
                    store.answeredMs = now // incoming call picked up
                    // Recording starts ONLY now that the call is answered. The service checks the
                    // CRM-only rule and whether an app-placed call is already recording; if either
                    // fails it records nothing.
                    CallRecordingService.start(
                        context.applicationContext,
                        number = store.screenedNumberNear(store.callStartMs),
                        direction = "inbound",
                        answeredAtMs = now,
                    )
                } else {
                    store.callStartMs = now // outgoing: off-hook starts at dial time
                    store.answeredMs = now
                    store.outgoing = true
                    // Dialer-placed outgoing call (an app-placed one is handled by
                    // NativeCallForegroundService, and the service bails when that is armed).
                    CallRecordingService.start(
                        context.applicationContext,
                        number = store.screenedNumberNear(now),
                        direction = "outbound",
                        answeredAtMs = now,
                    )
                }
            }
            TelephonyManager.EXTRA_STATE_IDLE -> {
                if (last == TelephonyManager.EXTRA_STATE_OFFHOOK && store.answeredMs > 0L) {
                    enqueue(context.applicationContext, store, endedAtMs = now)
                }
                store.clearCall()
            }
        }
        store.lastState = state
    }

    private fun enqueue(context: Context, store: CallDetectionStore, endedAtMs: Long) {
        val start = store.callStartMs
        val durationSeconds = ((endedAtMs - store.answeredMs) / 1000).toInt().coerceAtLeast(0)
        val builder = Data.Builder()
            .putLong(CallDetectedWorker.KEY_STARTED_AT, start)
            .putLong(CallDetectedWorker.KEY_ENDED_AT, endedAtMs)
            .putInt(CallDetectedWorker.KEY_DURATION, durationSeconds)
            .putBoolean(CallDetectedWorker.KEY_OUTGOING, store.outgoing)
        store.screenedNumberNear(start)?.let { builder.putString(CallDetectedWorker.KEY_NUMBER, it) }

        val request = OneTimeWorkRequestBuilder<CallDetectedWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setInputData(builder.build())
            .build()
        WorkManager.getInstance(context).enqueue(request)
    }
}
