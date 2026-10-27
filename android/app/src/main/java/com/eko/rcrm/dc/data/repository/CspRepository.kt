package com.eko.rcrm.dc.data.repository

import com.eko.rcrm.dc.data.remote.ApiService
import com.eko.rcrm.dc.data.remote.dto.CommitmentDto
import com.eko.rcrm.dc.data.remote.dto.CommitmentStatusRequestDto
import com.eko.rcrm.dc.data.remote.dto.CspDto
import com.eko.rcrm.dc.data.remote.dto.PreCallDto
import com.eko.rcrm.dc.domain.model.Commitment
import com.eko.rcrm.dc.domain.model.Csp
import com.eko.rcrm.dc.domain.model.PreCall
import com.eko.rcrm.dc.domain.model.PreCallLastCall
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

    /** Accept ("open"), dismiss ("cancelled") or complete ("done") a commitment. */
    suspend fun setCommitmentStatus(commitmentId: Int, status: String): Result<Commitment> = safeApiCall {
        apiService.setCommitmentStatus(commitmentId, CommitmentStatusRequestDto(status)).toDomain()
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

private fun CommitmentDto.toDomain() = Commitment(
    id = id,
    text = text,
    party = party,
    dueDate = due_date,
    status = status
)

private fun PreCallDto.toDomain() = PreCall(
    cspId = csp_id,
    name = name,
    category = category,
    branch = branch,
    mobile = mobile,
    alternateMobile = alternate_mobile,
    callsCount = calls_count,
    lastCall = last_call?.let {
        PreCallLastCall(
            whenIso = it.whenIso,
            direction = it.direction,
            summary = it.summary,
            highlights = it.highlights
        )
    },
    // Commitments both sides made that the RM still has to track: "you" also carries the joint ones.
    youCommitted = (open_commitments.ours + open_commitments.mutual).map { it.toDomain() },
    theyCommitted = open_commitments.theirs.map { it.toDomain() },
    suggested = proposed_commitments.map { it.toDomain() },
    slabStatus = slab_status,
    memory = memory.map { it.fact },
    talkingPoints = talking_points
)
