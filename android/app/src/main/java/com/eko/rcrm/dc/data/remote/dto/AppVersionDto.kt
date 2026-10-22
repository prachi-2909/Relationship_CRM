package com.eko.rcrm.dc.data.remote.dto

import kotlinx.serialization.Serializable

@Serializable
data class AppVersionDto(
    val version_code: Int,
    val version_name: String,
    val download_url: String
)
