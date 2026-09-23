package com.eko.rcrm.dc.domain.model

data class Official(
    val id: Int,
    val name: String,
    val email: String?,
    val phone: String?,
    val designation: String?,
    val level: String?,
    val location: String?
)
