package com.eko.rcrm.dc.data.remote.dto

import kotlinx.serialization.Serializable

@Serializable
data class DcTerritoryDto(
    val id: Int? = null,
    val dc_user_id: Int,
    val dc_user_name: String,
    val organization_unit_id: Int,
    val organization_unit_name: String,
    val organization_unit_type: String,
    val assigned_at: String? = null,
    // False for a parent RBO/AO shown only because it carries officials that
    // cover the DC's assigned branches (e.g. a shared Field Investigator).
    val is_direct: Boolean = true
)

@Serializable
data class DcProfileDto(
    val id: Int,
    val name: String,
    val email: String? = null,
    val status: String? = null,
    val territory: List<DcTerritoryDto> = emptyList(),
    val pending_calls: Int = 0,
    val logged_interactions: Int = 0
)
