package com.eko.rcrm.dc.calldetect

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/** Small shared scratchpad between the pieces of call auto-detection, which run in separate
 * short-lived contexts (the system-bound screening service, the PHONE_STATE receiver, a
 * WorkManager job) and so can only hand data to each other through storage.
 *
 * The screening service is the only call-log-free source of a call's phone number; the
 * PHONE_STATE broadcast is the only thing that says when it started and ended. Neither alone
 * is enough, so [recordScreened] stashes the number and the receiver pairs it with the
 * timestamps by proximity. Plain SharedPreferences, written with commit() - these are tiny
 * writes and the process can be killed right after. */
@Singleton
class CallDetectionStore @Inject constructor(
    @ApplicationContext context: Context
) {
    private val prefs = context.getSharedPreferences("call_detection", Context.MODE_PRIVATE)

    // --- number captured by the call-screening service ---------------------------------

    fun recordScreened(number: String?, atMs: Long = System.currentTimeMillis()) {
        prefs.edit()
            .putString(KEY_SCREENED_NUMBER, number)
            .putLong(KEY_SCREENED_AT, atMs)
            .commit()
    }

    /** The screened number, if the screening callback fired close to when the call started. */
    fun screenedNumberNear(callStartMs: Long): String? {
        val at = prefs.getLong(KEY_SCREENED_AT, 0L)
        if (at == 0L || kotlin.math.abs(at - callStartMs) > NUMBER_MATCH_WINDOW_MS) return null
        return prefs.getString(KEY_SCREENED_NUMBER, null)?.takeIf { it.isNotBlank() }
    }

    // --- phone-state machine -------------------------------------------------------------

    var lastState: String
        get() = prefs.getString(KEY_STATE, "IDLE") ?: "IDLE"
        set(value) { prefs.edit().putString(KEY_STATE, value).commit() }

    var callStartMs: Long
        get() = prefs.getLong(KEY_CALL_START, 0L)
        set(value) { prefs.edit().putLong(KEY_CALL_START, value).commit() }

    /** When the call actually connected: for an incoming call, when it was answered. */
    var answeredMs: Long
        get() = prefs.getLong(KEY_ANSWERED, 0L)
        set(value) { prefs.edit().putLong(KEY_ANSWERED, value).commit() }

    var outgoing: Boolean
        get() = prefs.getBoolean(KEY_OUTGOING, false)
        set(value) { prefs.edit().putBoolean(KEY_OUTGOING, value).commit() }

    fun clearCall() {
        // Drop the screened phone number too (DPDP data minimisation): it is only needed to pair a
        // call's number with its timing while the call is live, never to be retained afterwards.
        prefs.edit()
            .putLong(KEY_CALL_START, 0L)
            .putLong(KEY_ANSWERED, 0L)
            .remove(KEY_SCREENED_NUMBER)
            .remove(KEY_SCREENED_AT)
            .commit()
    }

    // --- last outcome, shown on the Profile screen so detection can be verified ----------

    fun setLastResult(text: String) {
        prefs.edit().putString(KEY_RESULT, text).putLong(KEY_RESULT_AT, System.currentTimeMillis()).commit()
    }

    val lastResult: String?
        get() = prefs.getString(KEY_RESULT, null)

    val lastResultAtMs: Long
        get() = prefs.getLong(KEY_RESULT_AT, 0L)

    private companion object {
        const val NUMBER_MATCH_WINDOW_MS = 60_000L
        const val KEY_SCREENED_NUMBER = "screened_number"
        const val KEY_SCREENED_AT = "screened_at"
        const val KEY_STATE = "state"
        const val KEY_CALL_START = "call_start"
        const val KEY_ANSWERED = "answered"
        const val KEY_OUTGOING = "outgoing"
        const val KEY_RESULT = "last_result"
        const val KEY_RESULT_AT = "last_result_at"
    }
}
