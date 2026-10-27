package com.eko.rcrm.dc.data.repository

import com.eko.rcrm.dc.data.remote.ApiService
import com.eko.rcrm.dc.data.remote.dto.CommitmentStatusRequestDto
import com.eko.rcrm.dc.data.remote.dto.DuplicateDecisionRequestDto
import com.eko.rcrm.dc.data.remote.dto.FeedbackRequestDto
import com.eko.rcrm.dc.data.remote.dto.OfficialCreateRequestDto
import com.eko.rcrm.dc.data.remote.dto.OfficialUpdateRequestDto
import com.eko.rcrm.dc.domain.model.Commitment
import com.eko.rcrm.dc.domain.model.Official
import com.eko.rcrm.dc.domain.model.OfficialBriefing
import com.eko.rcrm.dc.util.Result
import com.eko.rcrm.dc.util.safeApiCall
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class OfficialRepository @Inject constructor(
    private val apiService: ApiService
) {
    suspend fun search(query: String, limit: Int = 100): Result<List<Official>> = safeApiCall {
        apiService.searchOfficials(query = query.ifBlank { null }, limit = limit)
            .items.map { it.toDomain() }
    }

    /** All officials in the DC's territory (or, with unitId, just that one territory unit). */
    suspend fun list(unitId: Int? = null, limit: Int = 100): Result<List<Official>> = safeApiCall {
        apiService.searchOfficials(query = null, limit = limit, unitId = unitId)
            .items.map { it.toDomain() }
    }

    suspend fun getOfficial(id: Int): Result<Official> = safeApiCall {
        apiService.getOfficial(id).toDomain()
    }

    /** The DC's relationship briefing on one official. The server answers 404 for an official outside
     * the DC's territory. Built from interactions, tasks and memory - never from call audio. */
    suspend fun getBriefing(officialId: Int): Result<OfficialBriefing> = safeApiCall {
        apiService.getOfficialIntelligence(officialId).toDomain()
    }

    suspend fun setCommitmentStatus(
        commitmentId: Int,
        status: String,
        outcome: String? = null
    ): Result<Commitment> = safeApiCall {
        apiService.setOfficialCommitmentStatus(commitmentId, CommitmentStatusRequestDto(status, outcome)).toDomain()
    }

    suspend fun reviewDuplicate(commitmentId: Int, decision: String): Result<Commitment> = safeApiCall {
        apiService.reviewOfficialCommitmentDuplicate(commitmentId, DuplicateDecisionRequestDto(decision)).toDomain()
    }

    /** Rate a suggestion: [targetType] "talking_point" | "followup"; [verdict] useful / not_useful /
     * relevant / not_relevant. */
    suspend fun sendFeedback(
        officialId: Int,
        targetType: String,
        key: String,
        verdict: String
    ): Result<Unit> = safeApiCall {
        apiService.sendOfficialFeedback(officialId, FeedbackRequestDto(targetType, key, verdict))
    }

    /** organizationUnitId is required - the server 422s a DC-authored create without one. */
    suspend fun createOfficial(
        name: String,
        phone: String?,
        email: String?,
        designation: String?,
        department: String?,
        level: String?,
        location: String?,
        organizationUnitId: Int
    ): Result<Official> = safeApiCall {
        apiService.createOfficial(
            OfficialCreateRequestDto(
                name = name,
                phone = phone,
                email = email,
                designation = designation,
                department = department,
                level = level,
                location = location,
                organization_unit_id = organizationUnitId
            )
        ).toDomain()
    }

    /** All fields optional - only pass what changed. */
    suspend fun updateOfficial(
        id: Int,
        name: String?,
        phone: String?,
        email: String?,
        designation: String?,
        department: String?,
        level: String?,
        location: String?,
        organizationUnitId: Int?
    ): Result<Official> = safeApiCall {
        apiService.updateOfficial(
            id,
            OfficialUpdateRequestDto(
                name = name,
                phone = phone,
                email = email,
                designation = designation,
                department = department,
                level = level,
                location = location,
                organization_unit_id = organizationUnitId
            )
        ).toDomain()
    }
}
