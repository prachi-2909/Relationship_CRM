package com.eko.rcrm.dc.data.remote

import com.eko.rcrm.dc.data.local.TokenStore
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject

/**
 * Adds "Authorization: Bearer <token>" to every request except the login call itself
 * (which has no token yet).
 */
class AuthInterceptor @Inject constructor(
    private val tokenStore: TokenStore
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()
        val path = original.url.encodedPath
        if (path.endsWith("/auth/login")) {
            return chain.proceed(original)
        }
        val token = tokenStore.getToken()
        val request = if (!token.isNullOrBlank()) {
            original.newBuilder()
                .header("Authorization", "Bearer $token")
                .build()
        } else {
            original
        }
        return chain.proceed(request)
    }
}
