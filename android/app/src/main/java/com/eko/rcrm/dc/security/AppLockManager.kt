package com.eko.rcrm.dc.security

import android.os.SystemClock
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * App lock with an idle timeout. While a DC is logged in, the app must be unlocked with the phone's
 * own credential (PIN / pattern / biometric) on a cold start and whenever it returns to the
 * foreground after being away longer than [IDLE_TIMEOUT_MS]. This protects a lost or handed-over
 * phone that is already logged in - the gap a bank-grade review flags alongside the logout wipe.
 *
 * State only; the actual credential prompt is driven by the Activity (KeyguardManager), which is the
 * one place that can show it.
 */
@Singleton
class AppLockManager @Inject constructor() {

    private val _locked = MutableStateFlow(false)
    val locked: StateFlow<Boolean> = _locked.asStateFlow()

    private var backgroundedAtMs: Long? = null
    private var everUnlockedThisProcess = false

    /** Called when the app goes to the background; starts the idle clock. */
    fun onEnterBackground() {
        backgroundedAtMs = SystemClock.elapsedRealtime()
    }

    /** Called when the app returns to the foreground. Locks if logged in and either never unlocked
     * this process (cold start) or idle longer than the timeout. */
    fun onEnterForeground(isLoggedIn: Boolean) {
        if (!isLoggedIn) {
            _locked.value = false
            return
        }
        val away = backgroundedAtMs?.let { SystemClock.elapsedRealtime() - it } ?: Long.MAX_VALUE
        if (!everUnlockedThisProcess || away >= IDLE_TIMEOUT_MS) {
            _locked.value = true
        }
        backgroundedAtMs = null
    }

    fun markUnlocked() {
        everUnlockedThisProcess = true
        _locked.value = false
        backgroundedAtMs = null
    }

    /** On logout: forget unlock state so the next DC must authenticate from scratch. */
    fun reset() {
        everUnlockedThisProcess = false
        _locked.value = false
        backgroundedAtMs = null
    }

    private companion object {
        const val IDLE_TIMEOUT_MS = 2 * 60 * 1000L
    }
}
