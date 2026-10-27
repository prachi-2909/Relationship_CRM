package com.eko.rcrm.dc.data.remote.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** One tracked commitment (GET /csps/{id}/pre-call, POST /csps/commitments/{id}/status). */
@Serializable
data class CommitmentDto(
    val id: Int,
    val text: String,
    val party: String = "mutual",
    val due_date: String? = null,
    val status: String = "open"
)

@Serializable
data class PreCallLastCallDto(
    val call_id: Int = 0,
    @SerialName("when") val whenIso: String = "",
    val direction: String = "",
    val summary: String = "",
    val highlights: List<String> = emptyList()
)

@Serializable
data class OpenCommitmentsDto(
    val ours: List<CommitmentDto> = emptyList(),
    val theirs: List<CommitmentDto> = emptyList(),
    val mutual: List<CommitmentDto> = emptyList(),
    val total: Int = 0
)

@Serializable
data class MemoryFactDto(
    val fact: String,
    val kind: String = ""
)

/** The same pre-call briefing the web CRM shows - one backend source of truth. */
@Serializable
data class PreCallDto(
    val csp_id: String,
    val name: String,
    val category: String? = null,
    val branch: String? = null,
    val rm_name: String = "",
    val mobile: String? = null,
    val alternate_mobile: String? = null,
    val calls_count: Int = 0,
    val last_call: PreCallLastCallDto? = null,
    val open_commitments: OpenCommitmentsDto = OpenCommitmentsDto(),
    val proposed_commitments: List<CommitmentDto> = emptyList(),
    val slab_status: List<String> = emptyList(),
    val memory: List<MemoryFactDto> = emptyList(),
    val talking_points: List<String> = emptyList()
)

@Serializable
data class CommitmentStatusRequestDto(val status: String)
