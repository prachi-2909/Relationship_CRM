package com.eko.rcrm.dc.data.remote.dto

import kotlinx.serialization.Serializable

@Serializable
data class OfficialDto(
    val id: Int,
    val name: String,
    val email: String? = null,
    val phone: String? = null,
    val designation: String? = null,
    val level: String? = null,
    val location: String? = null
)

@Serializable
data class OfficialListResponseDto(
    val items: List<OfficialDto>,
    val total: Int,
    val limit: Int,
    val offset: Int
)
