package com.eko.rcrm.dc.data.remote

import com.eko.rcrm.dc.data.local.LocalDataWiper
import com.eko.rcrm.dc.data.local.TokenStore
import dagger.Lazy
import okhttp3.Authenticator
import okhttp3.Request
import okhttp3.Route
import javax.inject.Inject

/**
 * Fires on any 401 response. Wipes the session token AND all other local DC data, then emits a
 * one-shot "session expired" event so the UI forces a return to Login. A 401 on a non-login path
 * means the session is dead, and bank-grade / DPDP handling requires that an expired session not
 * leave the DC's data (DB, call audio, caches, numbers) sitting on the device. Always returns null
 * (no retry) - there is no refresh-token flow in this API, a 401 is terminal.
 *
 * [LocalDataWiper] is injected lazily to avoid a construction cycle (it pulls in the Room database,
 * which must not be built while the OkHttp client that owns this authenticator is still being set up).
 */
class AuthAuthenticator @Inject constructor(
    private val tokenStore: TokenStore,
    private val localDataWiper: Lazy<LocalDataWiper>,
    private val sessionEventBus: SessionEventBus
) : Authenticator {

    override fun authenticate(route: Route?, response: okhttp3.Response): Request? {
        val path = response.request.url.encodedPath
        if (path.endsWith("/auth/login")) {
            // A 401 here just means bad credentials, not an expired session - let the
            // LoginViewModel surface it as a normal error instead of forcing a redirect.
            return null
        }
        if (tokenStore.hasToken()) {
            localDataWiper.get().wipe()
            sessionEventBus.notifySessionExpired()
        }
        return null
    }
}
