package com.eko.rcrm.dc.nativecall

import android.content.Context
import android.os.Build
import android.telephony.PhoneStateListener
import android.telephony.TelephonyCallback
import android.telephony.TelephonyManager
import androidx.core.content.ContextCompat
import androidx.core.content.getSystemService

/** Mirrors only the three states a non-privileged observer can see - good enough to time a
 * call (OFFHOOK->IDLE) and tell "never connected" (RINGING straight to IDLE) from "connected,
 * then ended". Never attempts to read or record audio - see NativeCallForegroundService. */
enum class CallPhoneState { IDLE, RINGING, OFFHOOK }

interface CallStateObserver {
    /** [onStateChanged] is invoked on each transition, starting from the current state. */
    fun start(onStateChanged: (CallPhoneState) -> Unit)
    fun stop()
}

private fun Int.toCallPhoneState(): CallPhoneState = when (this) {
    TelephonyManager.CALL_STATE_RINGING -> CallPhoneState.RINGING
    TelephonyManager.CALL_STATE_OFFHOOK -> CallPhoneState.OFFHOOK
    else -> CallPhoneState.IDLE
}

/** API 31+: TelephonyCallback replaces the deprecated PhoneStateListener.LISTEN_CALL_STATE. */
private class TelephonyCallbackObserver(
    private val context: Context,
    private val telephonyManager: TelephonyManager
) : CallStateObserver {

    private var callback: TelephonyCallback? = null

    override fun start(onStateChanged: (CallPhoneState) -> Unit) {
        val listener = object : TelephonyCallback(), TelephonyCallback.CallStateListener {
            override fun onCallStateChanged(state: Int) {
                onStateChanged(state.toCallPhoneState())
            }
        }
        callback = listener
        telephonyManager.registerTelephonyCallback(ContextCompat.getMainExecutor(context), listener)
    }

    override fun stop() {
        callback?.let { telephonyManager.unregisterTelephonyCallback(it) }
        callback = null
    }
}

/** API 26-30: the only option before TelephonyCallback existed. */
@Suppress("DEPRECATION")
private class LegacyPhoneStateListenerObserver(private val telephonyManager: TelephonyManager) : CallStateObserver {

    private var listener: PhoneStateListener? = null

    override fun start(onStateChanged: (CallPhoneState) -> Unit) {
        val l = object : PhoneStateListener() {
            override fun onCallStateChanged(state: Int, phoneNumber: String?) {
                onStateChanged(state.toCallPhoneState())
            }
        }
        listener = l
        telephonyManager.listen(l, PhoneStateListener.LISTEN_CALL_STATE)
    }

    override fun stop() {
        listener?.let { telephonyManager.listen(it, PhoneStateListener.LISTEN_NONE) }
        listener = null
    }
}

/** Needs READ_PHONE_STATE, requested at runtime before this is ever called (same pattern as
 * RECORD_AUDIO for voice notes) - without it the OS reports only a coarse/absent state. */
fun provideCallStateObserver(context: Context): CallStateObserver {
    val appContext = context.applicationContext
    val telephonyManager = appContext.getSystemService<TelephonyManager>()
        ?: error("TelephonyManager unavailable")
    return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        TelephonyCallbackObserver(appContext, telephonyManager)
    } else {
        LegacyPhoneStateListenerObserver(telephonyManager)
    }
}
