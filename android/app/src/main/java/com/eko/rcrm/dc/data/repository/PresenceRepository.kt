package com.eko.rcrm.dc.data.repository

import com.eko.rcrm.dc.data.local.TokenStore
import com.eko.rcrm.dc.data.remote.ApiService
import javax.inject.Inject
import javax.inject.Singleton

/** Best-effort app-foreground signals for the admin CRM's live "who's active" view -
 * never surfaced to the DC, never blocks anything, so every call swallows its own errors. */
@Singleton
class PresenceRepository @Inject constructor(
    private val apiService: ApiService,
    private val tokenStore: TokenStore
) {
    suspend fun sendHeartbeat() {
        if (!tokenStore.hasToken()) return
        runCatching { apiService.presenceHeartbeat() }
    }

    suspend fun sendBackground() {
        if (!tokenStore.hasToken()) return
        runCatching { apiService.presenceBackground() }
    }
}
