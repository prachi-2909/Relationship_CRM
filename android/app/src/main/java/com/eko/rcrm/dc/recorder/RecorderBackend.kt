/*
 * Derived from CallVault's RecorderBackend (a fork of ShizuCallRecorder, Copyright (C) kitsumed (Med)),
 * GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 */
package com.eko.rcrm.dc.recorder

import android.content.Context
import android.os.SystemClock
import android.util.Log
import com.eko.rcrm.dc.data.local.PrivilegedMode

/** Makes sure the privileged recorder is running, via whichever privilege source the DC chose:
 * the built-in embedded ADB (no second app) or Shizuku. */
object RecorderBackend {
    private const val TAG = "RCRM:RecorderBackend"
    private const val BIND_TIMEOUT_MS = 10_000L
    private const val POLL_MS = 100L

    enum class Readiness { READY, NEEDS_PAIRING, SHIZUKU_NOT_INSTALLED, SHIZUKU_NOT_RUNNING, NO_PERMISSION }

    fun readiness(context: Context, mode: PrivilegedMode): Readiness = when (mode) {
        PrivilegedMode.EMBEDDED_ADB ->
            if (EmbeddedAdb.isConnected(context) || RecorderConnection.isConnected) Readiness.READY
            else Readiness.NEEDS_PAIRING
        PrivilegedMode.SHIZUKU -> when {
            !ShizukuBackend.isInstalled(context) -> Readiness.SHIZUKU_NOT_INSTALLED
            !ShizukuBackend.isRunning() -> Readiness.SHIZUKU_NOT_RUNNING
            !ShizukuBackend.hasPermission() -> Readiness.NO_PERMISSION
            else -> Readiness.READY
        }
    }

    /** Blocks until a usable binder is in [RecorderConnection], or the timeout elapses. */
    fun ensureRunning(context: Context, mode: PrivilegedMode): Boolean {
        if (RecorderConnection.isConnected) return true
        return when (mode) {
            PrivilegedMode.EMBEDDED_ADB -> EmbeddedAdb.ensureRecorderRunning(context)
            PrivilegedMode.SHIZUKU -> ensureShizuku(context)
        }
    }

    private fun ensureShizuku(context: Context): Boolean {
        if (readiness(context, PrivilegedMode.SHIZUKU) != Readiness.READY) return false
        if (!ShizukuBackend.start()) return false
        val deadline = SystemClock.elapsedRealtime() + BIND_TIMEOUT_MS
        while (SystemClock.elapsedRealtime() < deadline) {
            if (RecorderConnection.isConnected) return true
            Thread.sleep(POLL_MS)
        }
        Log.w(TAG, "Shizuku did not hand back a binder in ${BIND_TIMEOUT_MS}ms")
        return false
    }
}
