package com.eko.rcrm.dc.data.repository

import com.eko.rcrm.dc.data.remote.ApiService
import com.eko.rcrm.dc.data.remote.dto.CommitmentStatusRequestDto
import com.eko.rcrm.dc.data.remote.dto.CspDto
import com.eko.rcrm.dc.data.remote.dto.DuplicateDecisionRequestDto
import com.eko.rcrm.dc.data.remote.dto.FeedbackRequestDto
import com.eko.rcrm.dc.domain.model.Commitment
import com.eko.rcrm.dc.domain.model.Csp
import com.eko.rcrm.dc.domain.model.PreCall
import com.eko.rcrm.dc.util.Result
import com.eko.rcrm.dc.util.safeApiCall
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class CspRepository @Inject constructor(
    private val apiService: ApiService
) {
    /** The logged-in RM's own active CSPs - their calling list. */
    suspend fun getMyCsps(): Result<List<Csp>> = safeApiCall {
        apiService.getMyCsps().map { it.toDomain() }
    }

    /** The pre-call briefing for one CSP (by its primary key). The server enforces that it is the
     * caller's own CSP; anything else comes back as a 404 error. */
    suspend fun getPreCall(cspPk: Int): Result<PreCall> = safeApiCall {
        apiService.getCspPreCall(cspPk).toDomain()
    }

    /** Accept ("open"), dismiss ("cancelled") or complete ("done") a commitment; [outcome] says whether
     * a finished one was "fulfilled" or "not_fulfilled". */
    suspend fun setCommitmentStatus(
        commitmentId: Int,
        status: String,
        outcome: String? = null
    ): Result<Commitment> = safeApiCall {
        apiService.setCommitmentStatus(commitmentId, CommitmentStatusRequestDto(status, outcome)).toDomain()
    }

    /** Rule on a flagged near-duplicate: "merge" (same commitment) or "separate" (keep both). */
    suspend fun reviewDuplicate(commitmentId: Int, decision: String): Result<Commitment> = safeApiCall {
        apiService.reviewCspCommitmentDuplicate(commitmentId, DuplicateDecisionRequestDto(decision)).toDomain()
    }

    /** Rate a talking point: "useful" / "not_useful". */
    suspend fun sendFeedback(cspPk: Int, key: String, verdict: String): Result<Unit> = safeApiCall {
        apiService.sendCspFeedback(cspPk, FeedbackRequestDto("talking_point", key, verdict))
    }
}

private fun CspDto.toDomain() = Csp(
    id = id,
    cspId = csp_id,
    name = name,
    mobile = mobile,
    alternateMobile = alternate_mobile,
    category = category,
    branchName = branch_name,
    district = district,
    state = state
)
