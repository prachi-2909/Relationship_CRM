/*
 * Derived from CallVault's AdbShell / RecorderServerLauncher (a fork of ShizuCallRecorder,
 * Copyright (C) kitsumed (Med)), GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 */
package com.eko.rcrm.dc.recorder

import android.content.Context
import android.os.SystemClock
import android.util.Log
import com.eko.rcrm.dc.BuildConfig

/** Built-in (no second app) privilege source: the app's own embedded ADB client pairs with the
 * phone's Wireless Debugging, connects over the loopback, and launches the shell-uid recorder daemon
 * ([RecorderServer]). Needs Developer Options + Wireless Debugging ON; nothing else is installed. */
object EmbeddedAdb {
    private const val TAG = "RCRM:EmbeddedAdb"
    private const val PAIR_DISCOVER_MS = 15_000L
    private const val LAUNCH_POLL_MS = 100L
    private const val LAUNCH_TIMEOUT_MS = 12_000L

    val authority: String get() = BuildConfig.APPLICATION_ID + RecorderBinderProvider.AUTHORITY_SUFFIX

    /** Daemon launch over `app_process`, detached with setsid so it survives Wireless Debugging going off. */
    private fun launchCommand(apkPath: String): String =
        "setsid sh -c 'CLASSPATH=$apkPath exec app_process / " +
            "com.eko.rcrm.dc.recorder.RecorderServer $apkPath $authority' >/dev/null 2>&1 </dev/null & sleep 1"

    /** Pairs with the phone's Wireless Debugging using the 6-digit code the user reads from
     * Settings ▸ Developer options ▸ Wireless debugging ▸ Pair device with pairing code. Blocking; off-main. */
    fun pair(context: Context, code: String): Result<Unit> = runCatching {
        val port = AdbMdns.discoverPort(context, AdbMdns.TLS_PAIRING, PAIR_DISCOVER_MS)
            ?: error("Could not find the pairing service. Open 'Pair device with pairing code' first.")
        AdbConnectionManager.getInstance(context).pair("127.0.0.1", port, code)
        Log.i(TAG, "paired on port $port")
    }

    /** Whether the embedded client currently holds a live ADB connection. */
    fun isConnected(context: Context): Boolean =
        runCatching { AdbConnectionManager.getInstance(context).isConnected }.getOrDefault(false)

    /** Connects if not already: tries the OFF-WIFI loopback first (works without Wi-Fi once armed),
     * then falls back to Wireless Debugging (needs Wi-Fi). Blocking; off-main. */
    fun ensureConnected(context: Context): Boolean {
        val mgr = AdbConnectionManager.getInstance(context)
        if (runCatching { mgr.isConnected }.getOrDefault(false)) return true
        if (connectLoopback(context)) return true
        return runCatching {
            mgr.autoConnect(context.applicationContext, CONNECT_TIMEOUT_MS)
            mgr.isConnected
        }.onFailure { Log.w(TAG, "Wireless-debugging connect failed: ${it.message}") }.getOrDefault(false)
    }

    /** Connects to the classic-tcpip loopback listener (127.0.0.1:[LOOPBACK_PORT]). Works with NO
     * Wi-Fi once [armOffWifi] has run since the last reboot. Fast-fails when not armed. */
    private fun connectLoopback(context: Context): Boolean {
        val mgr = AdbConnectionManager.getInstance(context)
        return connectBounded("loopback :$LOOPBACK_PORT") { mgr.connect("127.0.0.1", LOOPBACK_PORT) }
    }

    /** Whether off-Wi-Fi recording is armed and reachable right now. */
    fun isOffWifiArmed(context: Context): Boolean = connectLoopback(context)

    /**
     * Arms off-Wi-Fi recording: opens `tcpip:<port>` so adbd restarts listening on a TCP port that is
     * also reachable over loopback (always up, no Wi-Fi). Needs Wi-Fi + Wireless Debugging ONCE to arm
     * through, and USB debugging ON so the listener survives; after that, recording connects off-Wi-Fi
     * until the next reboot (then re-arm on Wi-Fi once). Must NOT run while recording - adbd restarts.
     * Blocking; off-main.
     */
    fun armOffWifi(context: Context): Boolean {
        if (connectLoopback(context)) { Log.i(TAG, "off-Wi-Fi already armed"); return true }
        val mgr = AdbConnectionManager.getInstance(context)
        // Base connection over Wireless Debugging to arm through.
        if (!runCatching { mgr.isConnected }.getOrDefault(false)) {
            runCatching { mgr.autoConnect(context.applicationContext, CONNECT_TIMEOUT_MS) }
            if (!runCatching { mgr.isConnected }.getOrDefault(false)) {
                Log.w(TAG, "cannot arm: no Wireless-Debugging base connection (need Wi-Fi + WD on)")
                return false
            }
        }
        // Fire tcpip: arm on a throwaway thread - adbd restarts on the OPEN and kills this stream.
        Thread {
            runCatching { mgr.openStream("tcpip:$LOOPBACK_PORT").close() }
                .onFailure { Log.d(TAG, "tcpip arm stream closed: ${it.message}") }
        }.apply { isDaemon = true; start() }
        Thread.sleep(TCPIP_RESTART_WAIT_MS)
        runCatching { mgr.disconnect() }
        Thread.sleep(POST_DISCONNECT_WAIT_MS)
        var waited = 0L
        while (waited < LOOPBACK_SELFHEAL_MS) {
            if (connectLoopback(context)) { Log.i(TAG, "off-Wi-Fi armed on :$LOOPBACK_PORT"); return true }
            Thread.sleep(LOOPBACK_RETRY_MS); waited += LOOPBACK_RETRY_MS
        }
        Log.w(TAG, "loopback port did not come up after arming")
        return false
    }

    /** Runs a libadb connect under a hard time bound (the library's connect has none and can hang if
     * adbd is mid-restart). Abandons on timeout so callers never park forever. */
    private fun connectBounded(what: String, connect: () -> Boolean): Boolean {
        val ok = java.util.concurrent.atomic.AtomicBoolean(false)
        val worker = Thread {
            runCatching { ok.set(connect()) }.onFailure { Log.d(TAG, "$what unavailable: ${it.message}") }
        }.apply { isDaemon = true; name = "rcrm-adb-connect" }
        worker.start()
        runCatching { worker.join(CONNECT_BOUNDED_MS) }
        return if (worker.isAlive) {
            Log.w(TAG, "$what did not finish the ADB handshake in ${CONNECT_BOUNDED_MS}ms; abandoning")
            worker.interrupt()
            false
        } else ok.get()
    }

    /** Ensures the shell-uid recorder daemon is running and its binder is in [RecorderConnection]. */
    fun ensureRecorderRunning(context: Context): Boolean {
        if (RecorderConnection.isConnected) return true
        if (!ensureConnected(context)) return false
        val apk = context.applicationInfo.sourceDir
        runCatching {
            AdbConnectionManager.getInstance(context).openStream("shell:${launchCommand(apk)}").use { stream ->
                // Drain briefly so the command is delivered before the stream closes.
                runCatching { stream.openInputStream().use { it.readBytes() } }
            }
        }.onFailure { Log.w(TAG, "daemon launch failed: ${it.message}") }

        val deadline = SystemClock.elapsedRealtime() + LAUNCH_TIMEOUT_MS
        while (SystemClock.elapsedRealtime() < deadline) {
            if (RecorderConnection.isConnected) return true
            Thread.sleep(LAUNCH_POLL_MS)
        }
        Log.w(TAG, "daemon did not deliver its binder within ${LAUNCH_TIMEOUT_MS}ms")
        return false
    }

    private const val CONNECT_TIMEOUT_MS = 10_000L

    // Off-Wi-Fi loopback: a fixed high port adbd is told to listen on (classic tcpip), reachable over
    // 127.0.0.1 with no Wi-Fi. Persists until reboot. Needs USB debugging ON to survive.
    private const val LOOPBACK_PORT = 48653
    private const val CONNECT_BOUNDED_MS = 6_000L
    private const val TCPIP_RESTART_WAIT_MS = 2_500L
    private const val POST_DISCONNECT_WAIT_MS = 800L
    private const val LOOPBACK_SELFHEAL_MS = 12_000L
    private const val LOOPBACK_RETRY_MS = 1_500L
}
