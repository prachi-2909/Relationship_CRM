package com.eko.rcrm.dc.domain.model

/** A CSP (Customer Service Point) the logged-in RM is responsible for calling. */
data class Csp(
    val id: Int,
    val cspId: String,
    val name: String,
    val mobile: String?,
    val alternateMobile: String?,
    val category: String?,
    val branchName: String?,
    val district: String?,
    val state: String?
)
