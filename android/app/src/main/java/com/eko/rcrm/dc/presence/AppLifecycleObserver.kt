package com.eko.rcrm.dc.presence

import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import com.eko.rcrm.dc.data.repository.PresenceRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import javax.inject.Inject
import javax.inject.Singleton

/** Registered on ProcessLifecycleOwner (app-wide foreground/background, not per-screen)
 * so the admin CRM's "who's active" view reflects whether the DC's app is actually open,
 * not just whether they're logged in. See services/presence.py for the "online" rule
 * this feeds - a killed app (no onStop ever fires) still falls back to offline once its
 * heartbeat goes stale, so this never needs to be perfectly reliable to stay accurate. */
@Singleton
class AppLifecycleObserver @Inject constructor(
    private val presenceRepository: PresenceRepository
) : DefaultLifecycleObserver {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var heartbeatJob: Job? = null

    override fun onStart(owner: LifecycleOwner) {
        heartbeatJob?.cancel()
        heartbeatJob = scope.launch {
            while (isActive) {
                presenceRepository.sendHeartbeat()
                delay(HEARTBEAT_INTERVAL_MS)
            }
        }
    }

    override fun onStop(owner: LifecycleOwner) {
        heartbeatJob?.cancel()
        heartbeatJob = null
        scope.launch { presenceRepository.sendBackground() }
    }

    companion object {
        private const val HEARTBEAT_INTERVAL_MS = 20_000L
    }
}
