/*
 * Derived from CallVault's AdbPairingService (a fork of ShizuCallRecorder,
 * Copyright (C) kitsumed (Med)), GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 */
package com.eko.rcrm.dc.recorder

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.RemoteInput
import com.eko.rcrm.dc.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Foreground service that pairs the built-in recorder with the phone's Wireless Debugging. The DC
 * never leaves the Settings "Pair device with pairing code" popup: this service discovers the pairing
 * port over mDNS and posts a notification with an inline reply, so the 6-digit code is typed straight
 * into the notification. (Typing it inside the app would close the popup and kill the code - which is
 * why an in-app field does not work.)
 */
class AdbPairingService : Service() {

    private var adbMdns: AdbMdns? = null
    private var started = false
    @Volatile private var pairingHandled = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Pairing", NotificationManager.IMPORTANCE_HIGH).apply {
                setSound(null, null); setShowBadge(false)
            }
        )
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = when (intent?.action) {
            ACTION_START -> onStart()
            ACTION_REPLY -> {
                val code = RemoteInput.getResultsFromIntent(intent)?.getCharSequence(REMOTE_INPUT_KEY)?.toString().orEmpty()
                val port = intent.getIntExtra(EXTRA_PORT, -1)
                if (port != -1) onInput(code.trim(), port) else searchingNotification()
            }
            ACTION_STOP -> { stopSearch(); stopForeground(STOP_FOREGROUND_REMOVE); stopSelf(); null }
            else -> return START_NOT_STICKY
        }
        if (notification != null) {
            runCatching {
                val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q)
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC else 0
                startForeground(NOTIFICATION_ID, notification, type)
            }.onFailure {
                getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification)
            }
        }
        return START_NOT_STICKY
    }

    private fun onStart(): Notification {
        if (!started) {
            started = true
            adbMdns = AdbMdns(this, AdbMdns.TLS_PAIRING) { port ->
                if (port > 0) {
                    Log.i(TAG, "pairing service found on port $port")
                    getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, foundNotification(port))
                }
            }.also { it.start() }
        }
        return searchingNotification()
    }

    private fun onInput(code: String, port: Int): Notification {
        if (pairingHandled) return workingNotification()
        pairingHandled = true
        CoroutineScope(Dispatchers.IO).launch {
            val paired = runCatching { AdbConnectionManager.getInstance(applicationContext).pair("127.0.0.1", port, code) }
            stopSearch()
            val nm = getSystemService(NotificationManager::class.java)
            if (paired.getOrNull() == true) {
                Log.i(TAG, "pairing succeeded on port $port")
                nm.notify(NOTIFICATION_ID, resultNotification("Paired ✓", "Two-way recording is set up. Connecting…"))
                runCatching { EmbeddedAdb.ensureRecorderRunning(applicationContext) }
                    .onFailure { Log.w(TAG, "connect after pairing failed: ${it.message}") }
            } else {
                val msg = paired.exceptionOrNull()?.message ?: "Wrong code, or the pairing popup was closed."
                Log.e(TAG, "pairing failed on port $port: $msg")
                nm.notify(NOTIFICATION_ID, resultNotification("Pairing failed", msg))
            }
            pairingHandled = false
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
        return workingNotification()
    }

    private fun stopSearch() { runCatching { adbMdns?.stop() }; adbMdns = null; started = false }

    // ---- Notifications ----

    private fun base(title: String, text: String) = NotificationCompat.Builder(this, CHANNEL_ID)
        .setSmallIcon(R.mipmap.ic_launcher)
        .setContentTitle(title)
        .setContentText(text)
        .setStyle(NotificationCompat.BigTextStyle().bigText(text))
        .setOngoing(true)
        .setOnlyAlertOnce(true)

    private fun searchingNotification(): Notification =
        base("Pairing: waiting…", "Open Settings ▸ Developer options ▸ Wireless debugging ▸ Pair device with pairing code. Keep that popup open.")
            .build()

    private fun foundNotification(port: Int): Notification {
        val remoteInput = RemoteInput.Builder(REMOTE_INPUT_KEY).setLabel("6-digit code").build()
        val replyIntent = Intent(this, AdbPairingService::class.java).setAction(ACTION_REPLY).putExtra(EXTRA_PORT, port)
        val pi = PendingIntent.getService(
            this, port, replyIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
        )
        val action = NotificationCompat.Action.Builder(0, "Enter code", pi)
            .addRemoteInput(remoteInput).build()
        // Heads-up pop-up when the code field is ready, so the DC doesn't have to open the shade.
        return base("Enter the pairing code", "Type the 6-digit code from the pairing popup here.")
            .addAction(action)
            .setOnlyAlertOnce(false)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
    }

    private fun workingNotification(): Notification = base("Pairing…", "Checking the code.").build()
    private fun resultNotification(title: String, text: String): Notification =
        base(title, text).setOngoing(false).build()

    companion object {
        private const val TAG = "RCRM:AdbPairing"
        private const val CHANNEL_ID = "adb_pairing"
        private const val NOTIFICATION_ID = 7711
        private const val REMOTE_INPUT_KEY = "pairing_code"
        const val ACTION_START = "com.eko.rcrm.dc.PAIR_START"
        const val ACTION_REPLY = "com.eko.rcrm.dc.PAIR_REPLY"
        const val ACTION_STOP = "com.eko.rcrm.dc.PAIR_STOP"
        const val EXTRA_PORT = "port"

        fun start(context: android.content.Context) {
            val intent = Intent(context, AdbPairingService::class.java).setAction(ACTION_START)
            androidx.core.content.ContextCompat.startForegroundService(context, intent)
        }
    }
}
