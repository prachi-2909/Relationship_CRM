package com.eko.rcrm.dc.data.remote.dto

import kotlinx.serialization.Serializable

@Serializable
data class OfficialDto(
    val id: Int,
    val name: String,
    val email: String? = null,
    val phone: String? = null,
    val designation: String? = null,
    val department: String? = null,
    val level: String? = null,
    val location: String? = null,
    // Only populated by officials/{id} today; search results may omit these. The per-field
    // provenance map ("fields") the backend also returns is intentionally not modeled here -
    // v1 doesn't render it, and ignoreUnknownKeys on the shared Json instance skips it safely.
    val organization_unit_id: Int? = null,
    val organization_unit_name: String? = null,
    val organization_unit_type: String? = null,
    val status: String? = null,
    val verification_status: String? = null
)

@Serializable
data class OfficialListResponseDto(
    val items: List<OfficialDto>,
    val total: Int,
    val limit: Int,
    val offset: Int
)

/** Body for POST officials. organization_unit_id is required when the caller is a DC. */
@Serializable
data class OfficialCreateRequestDto(
    val name: String,
    val phone: String? = null,
    val email: String? = null,
    val designation: String? = null,
    val department: String? = null,
    val level: String? = null,
    val location: String? = null,
    val organization_unit_id: Int
)

/** Body for PATCH officials/{id} - every field optional/partial. */
@Serializable
data class OfficialUpdateRequestDto(
    val name: String? = null,
    val phone: String? = null,
    val email: String? = null,
    val designation: String? = null,
    val department: String? = null,
    val level: String? = null,
    val location: String? = null,
    val organization_unit_id: Int? = null
)
