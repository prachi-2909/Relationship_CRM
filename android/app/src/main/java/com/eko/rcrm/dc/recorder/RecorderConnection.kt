/*
 * Derived from CallVault (a fork of ShizuCallRecorder, Copyright (C) kitsumed (Med)),
 * GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 */
package com.eko.rcrm.dc.recorder

import android.os.IBinder
import android.util.Log

/** Holds the binder to the privileged recorder, whoever delivered it. */
object RecorderConnection {
    private const val TAG = "RCRM:RecorderConn"

    @Volatile var service: IRecorderService? = null
        private set

    val isConnected: Boolean
        get() = service?.let { runCatching { it.asBinder().isBinderAlive }.getOrDefault(false) } ?: false

    val deathRecipient = IBinder.DeathRecipient { onBinderDied() }

    fun onBinderReceived(binder: IRecorderService) {
        service = binder
        Log.i(TAG, "recorder binder received")
    }

    fun onBinderDied() {
        service = null
        Log.w(TAG, "recorder binder died")
    }
}
