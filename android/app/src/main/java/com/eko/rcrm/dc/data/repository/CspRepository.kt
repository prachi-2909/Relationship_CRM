package com.eko.rcrm.dc.data.repository

import com.eko.rcrm.dc.data.remote.ApiService
import com.eko.rcrm.dc.data.remote.dto.CspDto
import com.eko.rcrm.dc.domain.model.Csp
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
