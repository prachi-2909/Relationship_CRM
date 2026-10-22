package com.eko.rcrm.dc.data.remote.dto

import kotlinx.serialization.Serializable

@Serializable
data class AttestChallengeDto(val challenge: String)

@Serializable
data class AttestVerifyRequestDto(
    val challenge: String,
    val certificates: List<String>
)

@Serializable
data class AttestVerifyResponseDto(
    val attested: Boolean = false,
    val enforced: Boolean = false,
    val reason: String = ""
)
