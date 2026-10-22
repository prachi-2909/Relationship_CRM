package com.eko.rcrm.dc.security

import android.content.Context
import android.content.pm.ApplicationInfo
import android.os.Build
import android.os.Debug
import com.eko.rcrm.dc.BuildConfig
import java.io.File

/**
 * Best-effort root / debugger / tamper checks for a bank-grade release build. None of these are
 * unbeatable on their own - a determined attacker on a rooted device can patch them out - which is
 * why real assurance needs server-side Google Play Integrity attestation (a separate, infra-level
 * addition). These raise the bar locally and let the app refuse to run on an obviously compromised
 * device. Enforcement is release-only, so developers' rooted test phones and the debugger aren't
 * blocked during development.
 */
object DeviceIntegrity {

    data class Report(val rooted: Boolean, val debuggerAttached: Boolean, val debuggableBuild: Boolean) {
        val isCompromised: Boolean get() = rooted || debuggerAttached || debuggableBuild
    }

    /** Whether the app should refuse to run: a real compromise, but never in a debug build. */
    fun shouldBlock(context: Context): Boolean = !BuildConfig.DEBUG && inspect(context).isCompromised

    fun inspect(context: Context): Report = Report(
        rooted = isRooted(),
        debuggerAttached = Debug.isDebuggerConnected() || Debug.waitingForDebugger(),
        debuggableBuild = (context.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0,
    )

    private fun isRooted(): Boolean =
        hasSuBinary() || hasRootPackages() || hasTestKeysBuild()

    private fun hasSuBinary(): Boolean = SU_PATHS.any { runCatching { File(it).exists() }.getOrDefault(false) }

    private fun hasRootPackages(): Boolean = ROOT_FILES.any { runCatching { File(it).exists() }.getOrDefault(false) }

    /** A ROM signed with public test-keys (common on rooted/custom builds). */
    private fun hasTestKeysBuild(): Boolean = Build.TAGS?.contains("test-keys") == true

    private val SU_PATHS = listOf(
        "/system/bin/su", "/system/xbin/su", "/sbin/su", "/system/sd/xbin/su",
        "/system/bin/failsafe/su", "/data/local/xbin/su", "/data/local/bin/su",
        "/data/local/su", "/su/bin/su", "/system/app/Superuser.apk",
    )
    private val ROOT_FILES = listOf(
        "/sbin/magisk", "/system/app/Magisk", "/data/adb/magisk", "/data/adb/modules",
        "/system/app/SuperSU", "/system/xbin/daemonsu",
    )
}
