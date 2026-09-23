package com.eko.rcrm.dc.data.remote.dto

import kotlinx.serialization.Serializable

@Serializable
data class LoginRequestDto(
    val email: String,
    val password: String
)

@Serializable
data class LoginResponseDto(
    val id: Int,
    val name: String,
    val email: String,
    val role: String,
    val status: String,
    val token: String
)

@Serializable
data class UserDto(
    val id: Int,
    val name: String,
    val email: String,
    val role: String,
    val status: String
)
