package com.eko.rcrm.dc.domain.model

data class Official(
    val id: Int,
    val name: String,
    val email: String?,
    val phone: String?,
    val designation: String?,
    val department: String? = null,
    val level: String?,
    val location: String?,
    // Present on officials/{id} (and now optionally on search results); null when not returned.
    val organizationUnitId: Int? = null,
    val organizationUnitName: String? = null,
    val organizationUnitType: String? = null,
    val status: String? = null,
    val verificationStatus: String? = null
)
