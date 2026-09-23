package com.eko.rcrm.dc.data.repository

import com.eko.rcrm.dc.data.local.TokenStore
import com.eko.rcrm.dc.data.remote.ApiService
import com.eko.rcrm.dc.data.remote.dto.LoginRequestDto
import com.eko.rcrm.dc.domain.model.User
import com.eko.rcrm.dc.util.Result
import com.eko.rcrm.dc.util.safeApiCall
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AuthRepository @Inject constructor(
    private val apiService: ApiService,
    private val tokenStore: TokenStore
) {
    private var cachedUser: User? = null

    val isLoggedIn: Boolean
        get() = tokenStore.hasToken()

    suspend fun login(email: String, password: String): Result<User> = safeApiCall {
        val response = apiService.login(LoginRequestDto(email = email, password = password))
        tokenStore.setToken(response.token)
        val user = User(
            id = response.id,
            name = response.name,
            email = response.email,
            role = response.role,
            status = response.status
        )
        cachedUser = user
        user
    }

    suspend fun currentUser(): Result<User> = safeApiCall {
        val user = apiService.me().toDomain()
        cachedUser = user
        user
    }

    fun cachedUserOrNull(): User? = cachedUser

    suspend fun logout() {
        try {
            apiService.logout()
        } catch (_: Throwable) {
            // Best-effort - we clear local state regardless of server response.
        } finally {
            cachedUser = null
            tokenStore.clear()
        }
    }
}
