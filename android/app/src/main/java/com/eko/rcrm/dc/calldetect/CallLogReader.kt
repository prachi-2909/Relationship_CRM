package com.eko.rcrm.dc.calldetect

import android.content.Context
import android.content.pm.PackageManager
import android.provider.CallLog
import androidx.core.content.ContextCompat

/** Reads the system call log to tell whether a call was actually ANSWERED and for how long. Used so
 * a call that only rang (missed/rejected) is never logged/recorded, and so the ring-back at the start
 * of an outgoing recording can be trimmed off (keep only the talk time). Needs READ_CALL_LOG; without
 * it, or when the entry isn't written yet, returns null = "unknown". */
object CallLogReader {

    /** answered = real talk occurred; durationSec = that talk time (0 when not answered). */
    data class Answer(val answered: Boolean, val durationSec: Int)

    /** The matching call-log entry's outcome, or null when unknown. */
    fun lastAnswer(context: Context, phone: String?, sinceMs: Long): Answer? {
        if (phone.isNullOrBlank()) return null
        if (ContextCompat.checkSelfPermission(context, android.Manifest.permission.READ_CALL_LOG)
            != PackageManager.PERMISSION_GRANTED
        ) return null
        val wantDigits = phone.filter { it.isDigit() }.takeLast(10)
        if (wantDigits.length < 7) return null
        return runCatching {
            context.contentResolver.query(
                CallLog.Calls.CONTENT_URI,
                arrayOf(CallLog.Calls.NUMBER, CallLog.Calls.DURATION, CallLog.Calls.TYPE, CallLog.Calls.DATE),
                "${CallLog.Calls.DATE} >= ?",
                arrayOf((sinceMs - DATE_SLACK_MS).toString()),
                "${CallLog.Calls.DATE} DESC",
            )?.use { c ->
                val numIdx = c.getColumnIndexOrThrow(CallLog.Calls.NUMBER)
                val durIdx = c.getColumnIndexOrThrow(CallLog.Calls.DURATION)
                val typeIdx = c.getColumnIndexOrThrow(CallLog.Calls.TYPE)
                while (c.moveToNext()) {
                    val num = c.getString(numIdx)?.filter { it.isDigit() }?.takeLast(10) ?: continue
                    if (num != wantDigits) continue
                    val duration = c.getInt(durIdx)
                    val type = c.getInt(typeIdx)
                    val notAnswered = type == CallLog.Calls.MISSED_TYPE ||
                        type == CallLog.Calls.REJECTED_TYPE ||
                        type == CallLog.Calls.BLOCKED_TYPE
                    val answered = !notAnswered && duration > 0
                    return@use Answer(answered, if (answered) duration else 0)
                }
                null
            }
        }.getOrNull()
    }

    /** True = answered, false = not, null = unknown. */
    fun wasAnswered(context: Context, phone: String?, sinceMs: Long): Boolean? =
        lastAnswer(context, phone, sinceMs)?.answered

    /** Polls [lastAnswer] up to [timeoutMs] - the entry is written a moment after the call ends. */
    suspend fun awaitAnswer(context: Context, phone: String?, sinceMs: Long, timeoutMs: Long = 5_000L): Answer? {
        var waited = 0L
        while (waited < timeoutMs) {
            lastAnswer(context, phone, sinceMs)?.let { return it }
            kotlinx.coroutines.delay(POLL_MS)
            waited += POLL_MS
        }
        return null
    }

    suspend fun awaitAnswered(context: Context, phone: String?, sinceMs: Long, timeoutMs: Long = 5_000L): Boolean? =
        awaitAnswer(context, phone, sinceMs, timeoutMs)?.answered

    private const val DATE_SLACK_MS = 60_000L
    private const val POLL_MS = 500L
}
