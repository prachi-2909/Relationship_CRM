package com.eko.rcrm.dc.domain.model

data class User(
    val id: Int,
    val name: String,
    val email: String,
    val role: String,
    val status: String
)
