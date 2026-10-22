package com.eko.rcrm.dc.data.local

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/** Whether the DC has opted in to mic-recording their native-SIM calls. Off by default, and
 * only ever switched on through the consent dialog on the Profile screen - never implicitly. */
@Singleton
class CallRecordingPrefs @Inject constructor(
    @ApplicationContext context: Context
) {
    private val prefs = context.getSharedPreferences("call_recording", Context.MODE_PRIVATE)

    var enabled: Boolean
        get() = prefs.getBoolean(KEY_ENABLED, false)
        set(value) {
            val editor = prefs.edit().putBoolean(KEY_ENABLED, value)
            if (value) editor.putLong(KEY_CONSENT_AT, System.currentTimeMillis())
            editor.apply()
        }

    /** Which privilege source the two-way recorder uses. Default EMBEDDED_ADB (built-in, no second
     * app); SHIZUKU for DCs who prefer the Shizuku app. */
    var privilegedMode: PrivilegedMode
        get() = runCatching { PrivilegedMode.valueOf(prefs.getString(KEY_MODE, null) ?: "") }
            .getOrDefault(PrivilegedMode.EMBEDDED_ADB)
        set(value) { prefs.edit().putString(KEY_MODE, value.name).apply() }

    private companion object {
        const val KEY_ENABLED = "enabled"
        const val KEY_CONSENT_AT = "consent_at_epoch_ms"
        const val KEY_MODE = "privileged_mode"
    }
}

enum class PrivilegedMode { EMBEDDED_ADB, SHIZUKU }
