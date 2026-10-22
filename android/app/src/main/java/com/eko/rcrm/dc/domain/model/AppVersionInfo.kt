package com.eko.rcrm.dc.domain.model

/** Result of GET app/version - used to decide whether to show the in-app update banner. */
data class AppVersionInfo(
    val versionCode: Int,
    val versionName: String,
    val downloadUrl: String
)
