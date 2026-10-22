package com.eko.rcrm.dc.data.remote.dto

import kotlinx.serialization.Serializable

/** A Customer Service Point assigned to the logged-in Relationship Manager (GET /csps/mine). */
@Serializable
data class CspDto(
    val id: Int,
    val csp_id: String,
    val name: String,
    val mobile: String? = null,
    val alternate_mobile: String? = null,
    val category: String? = null,
    val branch_name: String? = null,
    val district: String? = null,
    val state: String? = null
)
