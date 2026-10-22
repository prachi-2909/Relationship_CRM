package com.eko.rcrm.dc.nativecall

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.widget.Toast
import androidx.core.app.NotificationCompat
import com.eko.rcrm.dc.R

private const val DIAG_CHANNEL_ID = "native_call_diagnostics"
private const val DIAG_NOTIFICATION_ID = 7342

/** TEMPORARY: surfaces a diagnostic through both a Toast and a notification while this device
 * has no logcat access. Neither channel is fully reliable alone - a Toast vanishes in ~3s
 * (too fast to read or screenshot) and a notification is silently suppressed without the
 * POST_NOTIFICATIONS permission (Android 13+) - so this shows both and whichever gets through
 * is enough. Remove once native calling is verified working end to end. */
fun showNativeCallDiagnostic(
    context: Context,
    title: String,
    throwable: Throwable,
    notificationId: Int = DIAG_NOTIFICATION_ID
) {
    val detail = buildString {
        append(throwable.javaClass.name)
        append(": ")
        append(throwable.message ?: "(no message)")
        append("\n\n")
        append(throwable.stackTraceToString().lineSequence().take(6).joinToString("\n"))
    }
    showNativeCallDiagnostic(context, title, detail, notificationId)
}

fun showNativeCallDiagnostic(
    context: Context,
    title: String,
    message: String,
    notificationId: Int = DIAG_NOTIFICATION_ID
) {
    Handler(Looper.getMainLooper()).post {
        Toast.makeText(context, "$title: $message", Toast.LENGTH_LONG).show()
    }
    val manager = context.getSystemService(NotificationManager::class.java) ?: return
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        manager.createNotificationChannel(
            NotificationChannel(DIAG_CHANNEL_ID, "Native call diagnostics", NotificationManager.IMPORTANCE_HIGH)
        )
    }
    val notification = NotificationCompat.Builder(context, DIAG_CHANNEL_ID)
        .setContentTitle(title)
        .setContentText(message)
        .setStyle(NotificationCompat.BigTextStyle().bigText(message))
        .setSmallIcon(R.mipmap.ic_launcher)
        .setAutoCancel(true)
        .setPriority(NotificationCompat.PRIORITY_HIGH)
        .build()
    manager.notify(notificationId, notification)
}
