package com.eko.rcrm.dc.domain.model

/** A single organisation unit a DC is assigned to see officials under. */
data class DcTerritory(
    val id: Int?,
    val dcUserId: Int,
    val dcUserName: String,
    val organizationUnitId: Int,
    val organizationUnitName: String,
    val organizationUnitType: String,
    val assignedAt: String?,
    val isDirect: Boolean = true
)

data class DcProfile(
    val id: Int,
    val name: String,
    val email: String?,
    val status: String?,
    val territory: List<DcTerritory>,
    val pendingCalls: Int,
    val loggedInteractions: Int
)
