package com.eko.rcrm.dc.data.repository

import com.eko.rcrm.dc.data.remote.ApiService
import com.eko.rcrm.dc.domain.model.DcProfile
import com.eko.rcrm.dc.domain.model.DcTerritory
import com.eko.rcrm.dc.util.Result
import com.eko.rcrm.dc.util.safeApiCall
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class DcProfileRepository @Inject constructor(
    private val apiService: ApiService
) {
    /** dc/profile - implicitly scoped to the calling DC by the bearer token, no id needed. */
    suspend fun getProfile(): Result<DcProfile> = safeApiCall {
        apiService.getDcProfile().toDomain()
    }

    /** The DC's own directly-assigned territory units - typically 1-3, used for the org-unit picker. */
    suspend fun getTerritories(): Result<List<DcTerritory>> = safeApiCall {
        apiService.getDcTerritories().map { it.toDomain() }
    }
}
