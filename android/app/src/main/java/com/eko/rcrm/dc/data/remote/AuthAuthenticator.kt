package com.eko.rcrm.dc.data.remote

import com.eko.rcrm.dc.data.local.TokenStore
import okhttp3.Authenticator
import okhttp3.Request
import okhttp3.Route
import javax.inject.Inject

/**
 * Fires on any 401 response. Clears the stored token and emits a one-shot "session expired"
 * event so the UI layer can force-navigate to Login and pop the whole back stack. Always
 * returns null (no retry) - there is no refresh-token flow in this API, a 401 is terminal.
 */
class AuthAuthenticator @Inject constructor(
    private val tokenStore: TokenStore,
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
            tokenStore.clear()
            sessionEventBus.notifySessionExpired()
        }
        return null
    }
}
